"""测试共享夹具: 构造一个迷你 opencode.db (仅含查询所需的列).

数据形态:
  - ses_...aa  同时存在于 session_v2 与遗留 session 表 (测试去重合并)
  - ses_...bb  仅在 session_v2
  - ses_...cc  子会话 (parent_id 非空), 应被排除
  - ses_...dd  已归档 (time_archived 非空), 应被排除
"""

import json
import os
import sqlite3
import time

NOW_MS = int(time.time() * 1000)

ALPHA_DIR = "/tmp/proj-alpha"
BETA_DIR = "/tmp/proj-beta"


def ensure_dirs():
    """new 命令会校验目录存在, 测试前确保夹具目录真实存在。"""
    for d in (ALPHA_DIR, BETA_DIR):
        os.makedirs(d, exist_ok=True)

SESSIONS = {
    "aa": {
        "id": "ses_test0000000001aaaaaaaaaa", "title": "fix alpha 解析逻辑",
        "directory": ALPHA_DIR, "model": {"id": "test-model", "providerID": "opencode"},
        "created": NOW_MS - 3600_000, "updated": NOW_MS - 600_000,
    },
    "bb": {
        "id": "ses_test0000000002bbbbbbbbbb", "title": "second beta session",
        "directory": BETA_DIR, "model": {"id": "m2", "providerID": "prov"},
        "created": NOW_MS - 4 * 86_400_000, "updated": NOW_MS - 3 * 86_400_000,
    },
    "cc": {
        "id": "ses_test0000000003cccccccccc", "title": "child gamma 子会话",
        "directory": ALPHA_DIR, "model": {}, "parent_id": "ses_test0000000001aaaaaaaaaa",
        "created": NOW_MS - 500_000, "updated": NOW_MS - 400_000,
    },
    "dd": {
        "id": "ses_test0000000004dddddddddd", "title": "archived delta 已归档",
        "directory": BETA_DIR, "model": {}, "archived": NOW_MS - 100_000,
        "created": NOW_MS - 800_000, "updated": NOW_MS - 200_000,
    },
}

COLS = """id text PRIMARY KEY, parent_id text, directory text, title text,
          model text, time_created integer, time_updated integer,
          time_archived integer, version text"""


def _insert(con, table, s):
    con.execute(
        "INSERT INTO %s (id, parent_id, directory, title, model, time_created,"
        " time_updated, time_archived, version) VALUES (?,?,?,?,?,?,?,?,?)" % table,
        (s["id"], s.get("parent_id"), s["directory"], s["title"],
         json.dumps(s["model"]) if s["model"] else None,
         s["created"], s["updated"], s.get("archived"), "v2"))


def build_db(path):
    ensure_dirs()
    con = sqlite3.connect(path)
    for table in ("session_v2", "session"):
        con.execute("CREATE TABLE %s (%s)" % (table, COLS))
    for key in ("aa", "bb", "cc", "dd"):
        _insert(con, "session_v2", SESSIONS[key])
    _insert(con, "session", SESSIONS["aa"])  # 遗留表重复, 应按 id 去重
    con.commit()
    con.close()
    return path
