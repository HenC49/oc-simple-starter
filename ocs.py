#!/usr/bin/env python3
"""oc-simple (ocs) — OpenCode 简易启动器.

功能:
  1. 新建 session: 调起系统文件选择器选择工作目录, 然后在该目录启动 opencode
  2. 恢复 session: 加载 OpenCode 留存的全部 session (跨项目), 支持实时搜索, 选中后恢复

数据来源: 只读查询 OpenCode v2 的 SQLite 库 (~/.local/share/opencode/opencode.db),
不写入任何数据; 启动会话通过 `opencode -s <id> <dir>` 完成。

仅依赖 Python 3 标准库。macOS 文件选择器用 osascript, Linux 回退 zenity。
"""

__version__ = "0.1.0"

import argparse
import curses
import json
import locale
import os

os.environ.setdefault("ESCDELAY", "30")  # 缩短裸 ESC 键的判定等待 (默认 1000ms)

import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
from datetime import datetime

DEFAULT_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")
STATE_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                         "oc-simple")
DRY_RUN = bool(os.environ.get("OC_SIMPLE_DRY_RUN"))
# None=未设置; ""=模拟用户取消; 非空=模拟选择该目录
FAKE_PICKER = os.environ.get("OC_SIMPLE_FAKE_PICKER")


# ---------------------------------------------------------------- 基础工具

def dw(s):
    """字符串的终端显示宽度 (中文等全角字符按 2 计)。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def fit(s, width):
    """按显示宽度截断字符串, 超出部分以 … 结尾。"""
    if dw(s) <= width:
        return s
    out, w = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in "WF" else 1
        if w + cw > width - 1:
            return out + "…"
        out += c
        w += cw
    return out


def pad(s, width):
    return s + " " * max(0, width - dw(s))


def rel_time(ms):
    """毫秒时间戳 → 相对时间描述。"""
    if not ms:
        return "?"
    delta = time.time() * 1000 - ms
    if delta < 60_000:
        return "刚刚"
    if delta < 3_600_000:
        return "%d分钟前" % (delta // 60_000)
    if delta < 86_400_000:
        return "%d小时前" % (delta // 3_600_000)
    if delta < 7 * 86_400_000:
        return "%d天前" % (delta // 86_400_000)
    dt = datetime.fromtimestamp(ms / 1000)
    return dt.strftime("%Y-%m-%d" if dt.year != datetime.now().year else "%m-%d")


def load_state():
    try:
        with open(os.path.join(STATE_DIR, "state.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "state.json"), "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def run_cmd(cmd):
    """dry-run 模式只打印将要执行的命令 (供测试), 否则替换当前进程。"""
    if DRY_RUN:
        print("DRY-RUN CMD: " + " ".join(cmd), file=sys.stderr)
        sys.exit(0)
    os.execvp(cmd[0], cmd)


def _set_locale():
    """优先用户环境 locale, 缺失时回退, 保证 curses 宽字符可用。"""
    for name in ("", "C.UTF-8", "en_US.UTF-8"):
        try:
            locale.setlocale(locale.LC_ALL, name)
            return
        except locale.Error:
            continue


# ---------------------------------------------------------------- session 读取

def load_sessions(db_path=DEFAULT_DB):
    """读取全部顶层 session, 按 time_updated 倒序。session_v2 优先, 遗留 session 表补充。"""
    if not os.path.exists(db_path):
        return None
    uri = "file:%s?mode=ro" % db_path.replace("?", "%3f").replace("#", "%23")
    con = sqlite3.connect(uri, uri=True)
    try:
        cols = "id, parent_id, directory, title, model, time_created, time_updated"
        v2 = {(r[0]): r for r in con.execute(
            "SELECT %s FROM session_v2 WHERE parent_id IS NULL AND time_archived IS NULL" % cols)}
        rows = dict(v2)
        for r in con.execute(
                "SELECT %s FROM session WHERE parent_id IS NULL AND time_archived IS NULL" % cols):
            rows.setdefault(r[0], r)
    finally:
        con.close()
    sessions = []
    for sid, parent, directory, title, model, tc, tu in rows.values():
        model_id, provider = "", ""
        if model:
            try:
                m = json.loads(model)
                model_id, provider = m.get("id", ""), m.get("providerID", "")
            except ValueError:
                model_id = str(model)
        sessions.append({"id": sid, "title": title or "(无标题)", "directory": directory or "",
                         "model": model_id, "provider": provider,
                         "created": tc or 0, "updated": tu or 0})
    sessions.sort(key=lambda s: s["updated"], reverse=True)
    return sessions


def filter_sessions(sessions, query):
    """空格分词, 每个词都须命中 标题/目录/id/model (不区分大小写)。"""
    tokens = query.lower().split()
    if not tokens:
        return sessions
    out = []
    for s in sessions:
        hay = " ".join([s["title"], s["directory"], s["id"], s["model"], s["provider"]]).lower()
        if all(t in hay for t in tokens):
            out.append(s)
    return out


def match_session(sessions, prefix):
    """按 id 前缀匹配, 返回 (session, 候选列表)。"""
    exact = [s for s in sessions if s["id"] == prefix]
    if exact:
        return exact[0], []
    cands = [s for s in sessions if s["id"].startswith(prefix)]
    if len(cands) == 1:
        return cands[0], []
    return None, cands


# ---------------------------------------------------------------- 系统文件选择器

def choose_dir_dialog(prompt="选择 OpenCode 工作目录"):
    """调起系统目录选择器; 用户取消返回 None。"""
    if FAKE_PICKER is not None:  # 测试钩子
        return FAKE_PICKER or None
    if sys.platform == "darwin":
        script = ('POSIX path of (choose folder with prompt "%s"'
                  ' default location POSIX file "%s")') % (prompt, os.path.expanduser("~/"))
        state = load_state()
        if state.get("last_dir") and os.path.isdir(state["last_dir"]):
            script = script.replace('POSIX file "%s"' % os.path.expanduser("~/"),
                                    'POSIX file "%s"' % state["last_dir"])
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            return None
        return r.stdout.strip().rstrip("/") or "/"
    if shutil.which("zenity"):
        r = subprocess.run(["zenity", "--file-selection", "--directory", "--title", prompt],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
        return r.stdout.strip().rstrip("/") or "/"
    print("未找到系统文件选择器 (macOS 需要 osascript, Linux 需要 zenity)。", file=sys.stderr)
    return None


# ---------------------------------------------------------------- 启动 opencode

def require_opencode():
    if not shutil.which("opencode"):
        sys.exit("错误: 未找到 opencode 命令, 请先安装 OpenCode。")


def launch_new(directory):
    require_opencode()
    try:
        os.chdir(directory)
    except OSError as e:
        sys.exit("无法进入目录 %s: %s" % (directory, e))
    run_cmd(["opencode", directory])


def launch_resume(sess):
    require_opencode()
    try:
        os.chdir(sess["directory"])
    except OSError as e:
        print("警告: 无法进入原目录 (%s), 将在当前位置启动: %s" % (sess["directory"], e),
              file=sys.stderr)
    run_cmd(["opencode", "-s", sess["id"], sess["directory"] or "."])


def do_new(directory=None):
    if not directory:
        directory = choose_dir_dialog()
    if not directory:
        print("已取消。")
        return
    if not os.path.isdir(directory):
        sys.exit("目录不存在: %s" % directory)
    state = load_state()
    state["last_dir"] = directory
    save_state(state)
    launch_new(directory)


def do_resume(prefix, db_path=DEFAULT_DB):
    sessions = load_sessions(db_path)
    if sessions is None:
        sys.exit("未找到 OpenCode 数据库: %s" % db_path)
    sess, cands = match_session(sessions, prefix)
    if sess:
        launch_resume(sess)
    elif cands:
        sys.exit("id 前缀不唯一, 候选:\n" +
                 "\n".join("  %s  %s" % (s["id"], fit(s["title"], 40)) for s in cands[:10]))
    else:
        sys.exit("没有匹配的 session: %s" % prefix)


# ---------------------------------------------------------------- curses 界面

C_TITLE, C_SEL, C_DIM, C_QUERY = 1, 2, 3, 4


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(C_SEL, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_DIM, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_QUERY, curses.COLOR_GREEN, -1)


def render_list(scr, y0, height, rows, sel, render_row):
    """绘制 rows[sel] 高亮的滚动列表, 返回实际绘制行数。"""
    if not rows:
        scr.addstr(y0, 2, fit("(无匹配结果)", curses.COLS - 3), curses.color_pair(C_DIM))
        return 0
    offset = max(0, min(sel - height + 1, sel)) if height > 0 else 0
    offset = max(0, min(offset, max(0, len(rows) - height)))
    for i in range(offset, min(offset + height, len(rows))):
        # 行宽最宽写到倒数第 2 列, 避免触碰右下角单元导致 addstr 报错
        text = render_row(rows[i], i == sel)
        line = " " + pad(fit(text, curses.COLS - 3), curses.COLS - 3)
        style = curses.color_pair(C_SEL) if i == sel else curses.A_NORMAL
        scr.addstr(y0 + (i - offset), 0, line, style)
    return min(height, len(rows))


def get_key(scr):
    """读取并归一化按键。自带转义序列解码, 规避部分 curses 构建不解析方向键的问题。
    返回 'up'/'down'/'pgup'/'pgdn'/'esc'/'enter'/'bs'/'home'/'end' 或原字符。"""
    ch = scr.get_wch()
    if isinstance(ch, int):
        return {curses.KEY_UP: "up", curses.KEY_DOWN: "down", curses.KEY_PPAGE: "pgup",
                curses.KEY_NPAGE: "pgdn", curses.KEY_BACKSPACE: "bs", curses.KEY_HOME: "home",
                curses.KEY_END: "end"}.get(ch, "")
    if ch in ("\r", "\n"):
        return "enter"
    if ch in ("\x7f", "\b"):
        return "bs"
    if ch != "\x1b":
        return ch
    # ESC: 短超时窗口内收集后续字节, 判断是否方向键序列
    scr.timeout(40)
    try:
        nxt = scr.get_wch()
    except curses.error:
        nxt = -1
    scr.timeout(-1)
    if nxt == -1:
        return "esc"
    if isinstance(nxt, str) and nxt in ("[", "O"):
        try:
            c = scr.get_wch()
        except curses.error:
            c = ""
        if c == "5":
            scr.timeout(40)
            try:
                scr.get_wch()
            except curses.error:
                pass
            scr.timeout(-1)
            return "pgup"
        if c == "6":
            scr.timeout(40)
            try:
                scr.get_wch()
            except curses.error:
                pass
            scr.timeout(-1)
            return "pgdn"
        return {"A": "up", "B": "down", "C": "right", "D": "left",
                "H": "home", "F": "end"}.get(c, "esc")
    return "esc"


def pick(scr, title, options, render_row, search=False, footer_hint=""):
    """通用列表选择器。search=True 时支持输入实时过滤。
    返回 (选中的原始 option, 取消标记); options 元素为 (可过滤文本, 展示数据)。"""
    query, sel = "", 0
    while True:
        rows = options if not query else \
            [o for o in options if all(t in o[0].lower() for t in query.lower().split())]
        if sel >= len(rows):
            sel = max(0, len(rows) - 1)
        scr.erase()
        scr.addstr(0, 1, fit(title, curses.COLS - 1), curses.color_pair(C_TITLE) | curses.A_BOLD)
        header_h = 2
        hint_y = max(header_h + 1, curses.LINES - 2 if not search else curses.LINES - 3)
        list_h = max(1, hint_y - header_h - (1 if search else 0))
        render_list(scr, header_h, list_h, rows, sel, render_row)
        if search:
            scr.addstr(hint_y + 1, 0, " 搜索: ", curses.color_pair(C_QUERY) | curses.A_BOLD)
            scr.addstr(fit(query, curses.COLS - 8) + "_")
        scr.addstr(hint_y, 0, fit(" " + footer_hint, curses.COLS - 1), curses.color_pair(C_DIM))
        scr.refresh()

        try:
            key = get_key(scr)
        except KeyboardInterrupt:
            return None, True
        if key in ("esc", "\x03"):  # Esc / Ctrl-C: 有搜索词先清空, 否则取消
            if search and query:
                query, sel = "", 0
                continue
            return None, True
        if key == "enter":
            if rows:
                return rows[sel][1], False
            curses.beep()
        elif key in ("up", "k") or key == "\x10":
            sel = max(0, sel - 1)
        elif key in ("down", "j") or key == "\x0e":
            sel = min(len(rows) - 1, sel + 1)
        elif key == "pgup":
            sel = max(0, sel - (curses.LINES - 5))
        elif key == "pgdn":
            sel = min(max(0, len(rows) - 1), sel + (curses.LINES - 5))
        elif key == "home":
            sel = 0
        elif key == "end":
            sel = max(0, len(rows) - 1)
        elif key == "bs" and search:
            query = query[:-1]
        elif search and isinstance(key, str) and (key.isprintable() or key == "\t"):
            if len(query) < 200:
                query += key
        # 无搜索模式的其余按键忽略; "q" 由调用方在 options 里自行处理


def main_menu(scr, sessions):
    init_colors()
    while True:
        count = len(sessions) if sessions is not None else 0
        options = [
            ("new session 新建", "new"),
            ("resume 恢复 session", "resume"),
        ]
        footer = "↑↓/jk 选择  Enter 确认  Esc 退出   |   共 %d 个 session   |   新建: oc-simple" % count
        choice, cancelled = pick(
            scr, "OpenCode 启动器 (oc-simple)", options,
            lambda o, s: ("  ◆ 新建 session  — 选择工作目录开始" if o[1] == "new"
                          else "  ↺ 恢复 session  — 搜索并进入历史会话"),
            footer_hint=footer)
        if cancelled or choice is None:
            return None
        return choice  # pick 返回的已是 options 的 payload ("new"/"resume")


def browse_sessions(scr, sessions):
    init_colors()
    options = [(s["title"] + " " + s["directory"] + " " + s["id"], s) for s in sessions]
    footer = ("输入关键词过滤 (空格分隔多词, 命中标题/目录/id)  "
              "↑↓/jk 选择  Enter 恢复  Esc 返回")
    sess, cancelled = pick(
        scr, "恢复 session — 共 %d 个 (跨项目, 按最近更新排序)" % len(sessions), options,
        session_row, search=True, footer_hint=footer)
    return None if cancelled else sess


def session_row(option, _):
    s = option[1]
    t = rel_time(s["updated"])
    dt = datetime.fromtimestamp(s["updated"] / 1000).strftime("%m-%d %H:%M") \
        if s["updated"] else "?"
    model = (" · " + s["model"]) if s["model"] else ""
    return "%s %s  %s   %s%s" % (pad(t, 7), dt, s["title"], s["directory"], model)


# ---------------------------------------------------------------- 命令行入口

def cmd_list(query, db_path):
    sessions = load_sessions(db_path)
    if sessions is None:
        sys.exit("未找到 OpenCode 数据库: %s (需要 OpenCode v2)" % db_path)
    sessions = filter_sessions(sessions, query or "")
    if not sessions:
        print("(无 session)")
        return
    for s in sessions:
        print("%s  %s  %s\n    %s" % (fit(s["id"], 12), pad(rel_time(s["updated"]), 7),
                                      s["title"], s["directory"]))


def cmd_tui(db_path):
    sessions = load_sessions(db_path)
    if sessions is None:
        sys.exit("未找到 OpenCode 数据库: %s (需要 OpenCode v2)" % db_path)

    def run(scr):
        while True:
            act = main_menu(scr, sessions)
            if act is None:
                return None
            if act == "new":
                return ("new", None)
            sess = browse_sessions(scr, sessions)
            if sess:
                return ("resume", sess)
            # 取消浏览则回到主菜单
    action = curses.wrapper(run)
    if action is None:
        print("再见。")
        return
    if action[0] == "new":
        do_new()
    else:
        launch_resume(action[1])


def main():
    _set_locale()
    ap = argparse.ArgumentParser(prog="ocs", description="OpenCode 简易启动器 (oc-simple)")
    ap.add_argument("--version", action="version", version="ocs %s" % __version__)
    ap.add_argument("--db", default=os.environ.get("OC_SIMPLE_DB", DEFAULT_DB),
                    help="opencode.db 路径 (默认 ~/.local/share/opencode/opencode.db)")
    sub = ap.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="列出 session (可带搜索词)")
    p_list.add_argument("query", nargs="?", default="")
    p_new = sub.add_parser("new", help="新建 session (可指定目录, 否则弹系统文件选择器)")
    p_new.add_argument("directory", nargs="?")
    p_res = sub.add_parser("resume", help="按 id 前缀恢复 session")
    p_res.add_argument("id_prefix")
    args = ap.parse_args()

    if args.cmd == "list":
        cmd_list(args.query, args.db)
    elif args.cmd == "new":
        do_new(args.directory)
    elif args.cmd == "resume":
        do_resume(args.id_prefix, args.db)
    else:
        cmd_tui(args.db)


if __name__ == "__main__":
    main()
