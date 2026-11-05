"""Premarket / after-hours price moves from Yahoo chart data (shape copied from a real response)."""
import unittest
from unittest import mock

from app import jobs
from app.store import state

# One trading day: pre 4:00-9:30, regular 9:30-16:00, post 16:00-20:00 ET (2026-11-04)
PRE, REG, POST, END = 1793782800, 1793802600, 1793826000, 1793840400


def chart(close=100.0, bars=()):
    return {"meta": {"regularMarketPrice": close, "currentTradingPeriod": {
                "pre": {"start": PRE, "end": REG}, "regular": {"start": REG, "end": POST},
                "post": {"start": POST, "end": END}}},
            "timestamp": [t for t, _ in bars], "indicators": {"quote": [{"close": [p for _, p in bars]}]}}


class ExtendedMove(unittest.TestCase):
    def test_after_hours_vs_todays_close(self):
        m = jobs.extended_move(chart(100.0, [(REG + 60, 101.0), (POST + 600, 112.0)]), POST + 900)
        self.assertEqual(m[:3], ("post", 112.0, 100.0))
        self.assertAlmostEqual(m[3], 12.0)

    def test_premarket_vs_yesterdays_close(self):
        # in premarket, regularMarketPrice is still yesterday's close
        m = jobs.extended_move(chart(50.0, [(PRE + 60, 50.0), (REG - 300, 45.0)]), REG - 120)
        self.assertEqual(m[0], "pre")
        self.assertAlmostEqual(m[3], -10.0)

    def test_regular_session_and_weekend_are_skipped(self):
        c = chart(100.0, [(REG + 60, 120.0)])
        self.assertIsNone(jobs.extended_move(c, REG + 120))  # regular hours: the Finnhub check covers it
        self.assertIsNone(jobs.extended_move(c, END + 86400))  # after 8 pm / weekend

    def test_stale_or_missing_prices_are_skipped(self):
        self.assertIsNone(jobs.extended_move(chart(100.0, [(POST + 60, 120.0)]), POST + 60 + 3600))
        self.assertIsNone(jobs.extended_move(chart(100.0, [(POST + 60, None)]), POST + 120))
        self.assertIsNone(jobs.extended_move(chart(100.0, [(REG + 60, 120.0)]), POST + 120))  # no post bars yet


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise jobs.requests.HTTPError(str(self.status_code))


class CheckExtended(unittest.TestCase):
    def setUp(self):
        state.db.execute("DELETE FROM seen")
        state.db.commit()
        self.sent, self.calls = [], []
        self.resp = Resp({"chart": {"result": [chart(100.0, [(POST + 600, 112.0)])]}})
        for p in (mock.patch.object(jobs, "notify", side_effect=lambda t, m, **k: self.sent.append((t, m, k)) or True),
                  mock.patch.object(jobs.state, "tickers", return_value=["AAA", "BBB"]),
                  mock.patch.object(jobs.http, "get", side_effect=self.get),
                  mock.patch.object(jobs.time, "time", return_value=POST + 900)):
            p.start()
            self.addCleanup(p.stop)

    def get(self, url, **kw):
        self.calls.append(url)
        return self.resp

    def test_alerts_once_per_threshold(self):
        jobs.check_extended()
        self.assertEqual(len(self.sent), 2)
        title, msg, kw = self.sent[0]
        self.assertEqual(title, "AAA after hours ▲ +12.0%")
        self.assertIn("vs the last close 100.00", msg)
        self.assertEqual(kw["kind"], "move")
        self.assertNotIn("Mozilla", jobs.YAHOO_UA)  # honest app name, not a browser
        jobs.check_extended()
        self.assertEqual(len(self.sent), 2)  # no repeats at the same level

    def test_small_move_is_quiet(self):
        self.resp = Resp({"chart": {"result": [chart(100.0, [(POST + 600, 101.0)])]}})
        jobs.check_extended()
        self.assertEqual(self.sent, [])

    def test_refusal_stops_the_cycle(self):
        self.resp = Resp({}, status=429)
        with self.assertLogs("jobs", "WARNING"):
            jobs.check_extended()
        self.assertEqual((self.sent, len(self.calls)), ([], 1))


if __name__ == "__main__":
    unittest.main()
