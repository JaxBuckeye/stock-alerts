"""Health tracking behind the bot's status dot, /status, and the optional daily heartbeat."""
import time
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from app import config as c
from app import health
from app import main
from app.store import state

INTERVALS = {"news": 300, "prices": 60}
ENABLED = {"news": True, "prices": True}


class Verdicts(unittest.TestCase):
    def setUp(self):
        health._jobs.clear()

    def test_healthy_when_every_check_ran_recently(self):
        health.record("news", True)
        health.record("prices", True)
        self.assertEqual(health.verdict(INTERVALS, ENABLED), ("ok", []))

    def test_overdue_and_failing_checks_warn(self):
        health.record("news", True)
        health._jobs["news"]["last_run"] -= 3600          # an hour late for a 5-minute check
        for _ in range(3):
            health.record("prices", False, ValueError("Finnhub 401"))
        status, problems = health.verdict(INTERVALS, ENABLED)
        self.assertEqual(status, "warn")
        self.assertTrue(any(p.startswith("news check last ran 1h ago") for p in problems), problems)
        self.assertIn("prices check failing: Finnhub 401", problems)

    def test_one_failure_is_not_a_problem_yet(self):
        health.record("news", True)
        health.record("prices", False, ValueError("timeout"))
        self.assertEqual(health.verdict(INTERVALS, ENABLED)[0], "ok")

    def test_setup_errors_are_red(self):
        self.assertEqual(health.verdict(INTERVALS, ENABLED, ["FINNHUB_API_KEY is required"]),
                         ("error", ["Setup needed: FINNHUB_API_KEY is required"]))

    def test_status_line(self):
        base = {"tickers": 23, "cvrs": 2, "last_check": "1m ago", "problems": []}
        self.assertEqual(health.status_line(dict(base, status="ok")), "🟢 Watching 23 tickers · 2 CVRs · checked 1m ago")
        self.assertTrue(health.status_line(dict(base, status="warn", problems=["news check failing: x"])).startswith("🟡 news"))
        self.assertTrue(health.status_line(dict(base, status="error")).startswith("🔴"))
        self.assertLessEqual(len(health.status_line(dict(base, status="warn", problems=["x" * 500]))), 128)

    def test_report_has_everything_the_bot_shows(self):
        r = health.report()
        for k in ("status", "problems", "uptime", "tickers", "cvrs", "alerts_24h", "last_alert", "jobs", "channels"):
            self.assertIn(k, r)


class DailyHeartbeat(unittest.TestCase):
    def setUp(self):
        state.db.execute("DELETE FROM seen WHERE key LIKE 'heartbeat:%'")
        state.db.commit()
        health._jobs.clear()
        self.sent = []
        p = mock.patch.object(main, "notify", side_effect=lambda t, m, **k: self.sent.append((t, m, k)) or True)
        p.start()
        self.addCleanup(p.stop)

    def at(self, hour):
        return datetime(2026, 10, 29, hour, 5, tzinfo=ZoneInfo("America/New_York"))

    def test_off_by_default(self):
        with mock.patch.object(c, "HEARTBEAT_HOUR", None):
            self.assertFalse(main.daily_heartbeat(self.at(12)))
        self.assertEqual(self.sent, [])

    def test_once_a_day_at_the_chosen_hour(self):
        with mock.patch.object(c, "HEARTBEAT_HOUR", 8):
            main.daily_heartbeat(self.at(7))
            self.assertEqual(self.sent, [])
            main.daily_heartbeat(self.at(8))
            main.daily_heartbeat(self.at(15))  # e.g. after a restart later that day
        self.assertEqual(len(self.sent), 1)
        title, msg, kw = self.sent[0]
        self.assertIn("Watching", msg)
        self.assertEqual(kw["kind"], "system")

    def test_problems_are_called_out(self):
        for _ in range(3):
            health.record("news", False, RuntimeError("boom"))
        with mock.patch.object(c, "HEARTBEAT_HOUR", 8), mock.patch.object(c, "ENABLED", {"news": True}), \
                mock.patch.object(c, "INTERVALS", {"news": 300}):
            main.daily_heartbeat(self.at(9))
        title, msg, kw = self.sent[0]
        self.assertTrue(title.startswith("⚠️"))
        self.assertIn("news check failing: boom", msg)
        self.assertEqual(kw["priority"], 1)


class StatusEmbed(unittest.TestCase):
    def test_embed_builds(self):
        from app import bot
        health._jobs.clear()
        health.record("news", True)
        e = bot.status_embed(health.report())
        self.assertTrue(e.title.startswith(("🟢", "🟡", "🔴")))
        self.assertTrue(any(f.name == "Checks" for f in e.fields))


if __name__ == "__main__":
    unittest.main()
