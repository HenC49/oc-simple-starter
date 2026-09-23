#!/usr/bin/env python3
"""单元测试: 纯函数 + 数据读取 + 非交互子命令。直接运行: python3 tests/test_units.py"""

import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ocs  # noqa: E402
import fixture  # noqa: E402


class DisplayHelpers(unittest.TestCase):
    def test_dw_widths(self):
        self.assertEqual(ocs.dw("ab"), 2)
        self.assertEqual(ocs.dw("中文"), 4)
        self.assertEqual(ocs.dw("a中b"), 4)

    def test_fit_truncates_by_display_width(self):
        self.assertEqual(ocs.fit("中文abc", 5), "中文…")  # 4列中文 + 1列省略号
        self.assertEqual(ocs.fit("short", 10), "short")
        self.assertLessEqual(ocs.dw(ocs.fit("很长的中文标题哦哦哦", 6)), 6)
        self.assertTrue(ocs.fit("很长的中文标题哦哦哦", 6).endswith("…"))

    def test_pad(self):
        self.assertEqual(ocs.pad("a", 3), "a  ")
        self.assertEqual(ocs.dw(ocs.pad("中文", 6)), 6)


class RelativeTime(unittest.TestCase):
    def test_recent(self):
        now = time.time() * 1000
        self.assertEqual(ocs.rel_time(now - 30_000), "刚刚")
        self.assertEqual(ocs.rel_time(now - 5 * 60_000), "5分钟前")
        self.assertEqual(ocs.rel_time(now - 3 * 3_600_000), "3小时前")
        self.assertEqual(ocs.rel_time(now - 2 * 86_400_000), "2天前")

    def test_old_uses_date(self):
        ms = time.time() * 1000 - 400 * 86_400_000
        self.assertRegex(ocs.rel_time(ms), r"^\d{4}-\d{2}-\d{2}$")

    def test_zero(self):
        self.assertEqual(ocs.rel_time(0), "?")


class SessionData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = os.path.join(tempfile.mkdtemp(), "opencode.db")
        fixture.build_db(cls.db)
        cls.sessions = ocs.load_sessions(cls.db)

    def test_load_dedupe_and_filter(self):
        # aa 在 v2/遗留表各一条 → 去重; cc 子会话、dd 已归档 → 排除
        ids = [s["id"] for s in self.sessions]
        self.assertEqual(len(ids), 2)
        self.assertIn(fixture.SESSIONS["aa"]["id"], ids)
        self.assertIn(fixture.SESSIONS["bb"]["id"], ids)
        self.assertNotIn(fixture.SESSIONS["cc"]["id"], ids)
        self.assertNotIn(fixture.SESSIONS["dd"]["id"], ids)

    def test_sorted_by_updated_desc(self):
        updated = [s["updated"] for s in self.sessions]
        self.assertEqual(updated, sorted(updated, reverse=True))

    def test_model_parsed(self):
        aa = self.sessions[0]
        self.assertEqual(aa["model"], "test-model")
        self.assertEqual(aa["provider"], "opencode")

    def test_missing_db_returns_none(self):
        self.assertIsNone(ocs.load_sessions("/nonexistent/opencode.db"))

    def test_filter_multi_token(self):
        self.assertEqual(len(ocs.filter_sessions(self.sessions, "alpha 解析")), 1)
        self.assertEqual(len(ocs.filter_sessions(self.sessions, "")), 2)
        self.assertEqual(len(ocs.filter_sessions(self.sessions, "proj-beta beta")), 1)
        self.assertEqual(ocs.filter_sessions(self.sessions, "zzz"), [])

    def test_match_session(self):
        full = fixture.SESSIONS["aa"]["id"]
        sess, cands = ocs.match_session(self.sessions, full)
        self.assertEqual(sess["id"], full)
        sess, cands = ocs.match_session(self.sessions, "ses_test0000000001")
        self.assertIsNotNone(sess)
        self.assertEqual(cands, [])
        sess, cands = ocs.match_session(self.sessions, "ses_test")
        self.assertIsNone(sess)
        self.assertEqual(len(cands), 2)
        sess, _ = ocs.match_session(self.sessions, "nope")
        self.assertIsNone(sess)


class Cli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = os.path.join(tempfile.mkdtemp(), "opencode.db")
        fixture.build_db(cls.db)
        env = dict(os.environ, OC_SIMPLE_DRY_RUN="1", OC_SIMPLE_FAKE_PICKER="/tmp/proj-beta")
        cls.env = env

    def run_ocs(self, *args):
        return subprocess.run(
            [sys.executable, ocs.__file__.rstrip("c"), *args],
            capture_output=True, text=True, env=self.env)

    def test_version(self):
        r = self.run_ocs("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn(ocs.__version__, r.stdout)

    def test_list_and_search(self):
        r = self.run_ocs("--db", self.db, "list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("fix alpha 解析逻辑", r.stdout)
        self.assertIn("second beta session", r.stdout)
        r = self.run_ocs("--db", self.db, "list", "beta")
        self.assertNotIn("fix alpha 解析逻辑", r.stdout)
        self.assertIn("second beta session", r.stdout)

    def test_resume_unique_prefix(self):
        r = self.run_ocs("--db", self.db, "resume", "ses_test0000000001")
        self.assertEqual(r.returncode, 0)
        self.assertIn("DRY-RUN CMD: opencode -s %s /tmp/proj-alpha"
                      % fixture.SESSIONS["aa"]["id"], r.stderr)

    def test_resume_ambiguous(self):
        r = self.run_ocs("--db", self.db, "resume", "ses_test")
        self.assertEqual(r.returncode, 1)
        self.assertIn("id 前缀不唯一", r.stderr)

    def test_resume_no_match(self):
        r = self.run_ocs("--db", self.db, "resume", "ses_zzz")
        self.assertEqual(r.returncode, 1)
        self.assertIn("没有匹配", r.stderr)

    def test_new_with_dir(self):
        r = self.run_ocs("--db", self.db, "new", "/tmp/proj-beta")
        self.assertEqual(r.returncode, 0)
        self.assertIn("DRY-RUN CMD: opencode /tmp/proj-beta", r.stderr)

    def test_new_fake_picker(self):
        r = self.run_ocs("--db", self.db, "new")
        self.assertEqual(r.returncode, 0)
        self.assertIn("DRY-RUN CMD: opencode /tmp/proj-beta", r.stderr)

    def test_new_canceled(self):
        env = dict(self.env, OC_SIMPLE_FAKE_PICKER="")
        r = subprocess.run(
            [sys.executable, ocs.__file__.rstrip("c"), "--db", self.db, "new"],
            capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("已取消", r.stdout)
        self.assertNotIn("DRY-RUN", r.stderr)

    def test_missing_db(self):
        r = self.run_ocs("--db", "/nonexistent/x.db", "list")
        self.assertEqual(r.returncode, 1)
        self.assertIn("未找到 OpenCode 数据库", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
