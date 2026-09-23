#!/usr/bin/env python3
"""TUI 冒烟测试: 用 pty 驱动 ocs.py 交互界面, 通过自制的简易终端仿真器断言最终画面。

自带会话数据夹具 (tests/fixture.py), 不依赖本机真实 opencode 数据, 可在 CI 运行。
直接运行: python3 tests/test_tui_smoke.py
"""

import os
import pty
import select
import sys
import tempfile
import termios
import time
import fcntl
import struct
import unicodedata
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixture  # noqa: E402

COLS, LINES = 110, 30
CONT = "\x00"  # 宽字符占位格标记


def render(raw):
    """终端仿真: 单元格网格存储 (宽字符占 2 格), 输出最终屏幕内容。"""
    rows, cur_row, col = [[]], 0, 0
    txt = raw.decode("utf-8", "replace")

    def ensure(r):
        while len(rows) <= r:
            rows.append([])

    i, n = 0, len(txt)
    while i < n:
        c = txt[i]
        if c == "\x1b" and i + 1 < n and txt[i + 1] == "[":
            j = i + 2
            while j < n and not txt[j].isalpha() and txt[j] != "~":
                j += 1
            if j < n:
                params, cmd = txt[i + 2:j], txt[j]
                nums = [int(x) if x else 0
                        for x in params.replace("?", "").split(";") if x != ""] if params else []
                g1 = lambda k: nums[k] if k < len(nums) and nums[k] \
                    else (1 if cmd in "HfdGCXA" else 0)
                if cmd in ("H", "f"):
                    cur_row, col = g1(0) - 1, g1(1) - 1
                    ensure(cur_row)
                elif cmd == "d":
                    cur_row = g1(0) - 1
                    ensure(cur_row)
                elif cmd == "A":
                    cur_row = max(0, cur_row - g1(0))
                elif cmd == "G":
                    col = g1(0) - 1
                elif cmd == "C":
                    col += g1(0)
                elif cmd == "J":
                    if params in ("2", ""):
                        rows, cur_row, col = [[]], 0, 0
                elif cmd == "K":
                    del rows[cur_row][col:]
                elif cmd == "X":
                    w = g1(0) or 1
                    cells = rows[cur_row]
                    while len(cells) < col + w:
                        cells.append(" ")
                    for k in range(col, col + w):
                        cells[k] = " "
            i = j + 1
            continue
        if c == "\x1b" and i + 1 < n and txt[i + 1] in "(){]0":  # 字符集/ keypad 等杂项
            i += 3 if txt[i + 1] in "()" else 2
            continue
        if c in "\x0e\x0f":
            i += 1
            continue
        if c == "\r":
            col = 0
        elif c == "\n":
            cur_row += 1
            col = 0
            ensure(cur_row)
        elif c == "\x08":
            col = max(0, col - 1)
        elif c >= " ":
            w = 2 if unicodedata.east_asian_width(c) in "WF" else 1
            cells = rows[cur_row]
            while len(cells) <= col:
                cells.append(" ")
            cells[col] = c
            if w == 2:
                while len(cells) <= col + 1:
                    cells.append(CONT)
                cells[col + 1] = CONT
            col += w
        i += 1
    return "\n".join("".join(x for x in cells if x != CONT).rstrip() for cells in rows)


class TuiSession:
    """一个 ocs.py 的 pty 会话, 按键并断言累计画面。"""

    def __init__(self, extra_env=None):
        self.buf = b""
        env = dict(os.environ, TERM="xterm-256color",
                   OC_SIMPLE_DRY_RUN="1", ESCDELAY="30")
        env.update(extra_env or {})
        self.db_path = os.environ["_OCS_TEST_DB"]
        self.pid, fd = pty.fork()
        if self.pid == 0:
            os.execvpe("python3", ["python3", os.path.join(BASE, "ocs.py"),
                                   "--db", self.db_path], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", LINES, COLS, 0, 0))
        self.fd = fd
        self.wait()

    def wait(self, settle=0.4, timeout=4.0):
        end = time.time() + timeout
        last = time.time()
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    chunk = os.read(self.fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.buf += chunk
                last = time.time()
            elif time.time() - last > settle:
                break
        return self

    def send(self, keys, delay=0.35):
        os.write(self.fd, keys.encode() if isinstance(keys, str) else keys)
        time.sleep(delay)
        return self.wait()

    def screen(self):
        return render(self.buf)

    def assert_screen(self, expected, note=""):
        got = self.screen()
        for text in (expected if isinstance(expected, list) else [expected]):
            if text not in got:
                raise AssertionError("画面缺少 %r%s\n--- 当前画面 ---\n%s" % (text, note, got))

    def close(self):
        try:
            os.write(self.fd, b"\x03")
            time.sleep(0.15)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = os.path.join(tempfile.mkdtemp(), "opencode.db")
        fixture.build_db(cls.db)
        os.environ["_OCS_TEST_DB"] = cls.db
        cls.pick_dir = "/tmp/proj-beta"

    def make(self, **env):
        s = TuiSession(env)
        self.addCleanup(s.close)
        s.wait()
        return s

    def test_menu_screen(self):
        s = self.make()
        s.assert_screen(["OpenCode 启动器 (oc-simple)", "新建 session", "恢复 session",
                         "共 2 个 session", "Esc 退出"])

    def test_new_session_flow(self):
        s = self.make(OC_SIMPLE_FAKE_PICKER=self.pick_dir)
        s.send("\r")  # 默认选中"新建"
        s.assert_screen("DRY-RUN CMD: opencode %s" % self.pick_dir)

    def test_browse_search_and_resume(self):
        s = self.make()
        s.send("\x1b[B")   # 选中"恢复"
        s.send("\r")       # 进浏览器
        s.assert_screen(["恢复 session — 共 2 个", "fix alpha 解析逻辑",
                         "second beta session", "搜索: "])
        s.send("zzzz")     # 无匹配
        s.assert_screen("(无匹配结果)")
        s.send("\x1b")     # Esc 清空搜索词
        s.assert_screen("second beta session")
        s.send("\x7f\x7f\x7f\x7f")  # 保险: 再清一次
        s.send("alpha")    # 过滤出 1 条
        got = s.screen()
        self.assertIn("fix alpha 解析逻辑", got)
        self.assertNotIn("second beta session", got, "过滤后不应再显示未命中会话")
        s.send("\r")       # 恢复
        s.assert_screen("DRY-RUN CMD: opencode -s %s /tmp/proj-alpha"
                        % fixture.SESSIONS["aa"]["id"])

    def test_esc_navigation_and_quit(self):
        s = self.make()
        s.send("\x1b[B")
        s.send("\r")       # 进浏览器
        s.send("\x1b")     # 返回主菜单
        s.assert_screen("OpenCode 启动器 (oc-simple)")
        s.send("\x1b")     # 退出
        s.assert_screen("再见。")


if __name__ == "__main__":
    unittest.main(verbosity=2)
