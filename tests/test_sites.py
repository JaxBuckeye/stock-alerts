"""Company website monitoring: hidden feeds, several sources per ticker, blocked sites, press-wire fallback."""
import time
import unittest
from unittest import mock

from app import config as c
from app import cvr, jobs
from app.store import state

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>Longeveron Press Releases</title>
{items}</channel></rss>"""
ITEM = "<item><title>{t}</title><link>https://investors.longeveron.com/news/{n}</link><guid>{n}</guid></item>"
NEWSROOM_JS = "<html><body><div id='q4-news'></div><a href='/'>Home</a></body></html>"  # list built by JavaScript
HOMEPAGE = """<html><body><a href="https://investors.longeveron.com/news/default.aspx">View All News</a>
{links}<a href="/about">Learn more about our science and our mission today</a></body></html>"""
HLINK = '<a href="https://investors.longeveron.com/news/news-details/2026/{n}/default.aspx">{t}</a>'


def blocked(url):
    resp = mock.Mock(status_code=403)
    raise jobs.requests.HTTPError("403 Client Error: Forbidden", response=resp)


class Web:
    """Fake internet for fetch_text: url -> text, or a callable that raises."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url):
        self.calls.append(url)
        page = self.pages.get(url)
        if callable(page):
            return page(url)
        if page is None:
            resp = mock.Mock(status_code=404)
            raise jobs.requests.HTTPError("404", response=resp)
        return page


def slug(title):
    return "-".join(title.split())


def feed(*titles):
    return FEED.format(items="".join(ITEM.format(t=t, n=slug(t)) for t in titles))


def homepage(*titles):
    return HOMEPAGE.format(links="".join(HLINK.format(t=t, n=slug(t)) for t in titles))


class SiteTests(unittest.TestCase):
    def setUp(self):
        state.db.execute("DELETE FROM seen")
        state.db.execute("DELETE FROM watchlist")
        state.db.execute("DELETE FROM sites")
        state.db.commit()
        jobs._blocked.clear()
        state.add_ticker("LGVN", "Longeveron Inc", "test")
        self.sent = []
        for p in (mock.patch.object(jobs, "notify", side_effect=lambda t, m, **k: self.sent.append((t, m, k)) or True),
                  mock.patch.object(jobs.time, "sleep"), mock.patch.object(jobs, "robots_ok", return_value=True),
                  mock.patch.object(c, "PRESS_WIRE_NEWS", False)):
            p.start()
            self.addCleanup(p.stop)

    def run_sites(self, pages):
        web = Web(pages)
        with mock.patch.object(jobs, "fetch_text", web):
            jobs.check_sites()
        return web

    def test_finds_hidden_q4_feed_for_javascript_newsroom(self):
        web = Web({"https://longeveron.com": homepage("Longeveron Announces Updated Results from ELPIS II Trial"),
                   "https://investors.longeveron.com/news/default.aspx": NEWSROOM_JS,
                   "https://investors.longeveron.com/rss/pressrelease.aspx": feed("Release one is here today")})
        with mock.patch.object(jobs, "fetch_text", web):
            news, found = jobs.discover("https://longeveron.com", "LGVN")
        self.assertEqual(news, "https://investors.longeveron.com/news/default.aspx")
        self.assertEqual(found, "https://investors.longeveron.com/rss/pressrelease.aspx")

    def test_existing_site_without_feed_gets_probed_once(self):
        state.upsert_site("LGVN", homepage="https://longeveron.com",
                          news_url="https://investors.longeveron.com/news/default.aspx", checked_ts=int(time.time()))
        pages = {"https://longeveron.com": homepage(),
                 "https://investors.longeveron.com/news/default.aspx": NEWSROOM_JS,
                 "https://investors.longeveron.com/rss/pressrelease.aspx": feed("Old release from last week here")}
        self.run_sites(pages)
        self.assertEqual(state.get_site("LGVN")["feed_url"], "https://investors.longeveron.com/rss/pressrelease.aspx")

    def test_new_release_alerts_once_across_feed_and_homepage(self):
        state.upsert_site("LGVN", homepage="https://longeveron.com",
                          news_url="https://investors.longeveron.com/news/default.aspx",
                          feed_url="https://investors.longeveron.com/rss/pressrelease.aspx", checked_ts=int(time.time()))
        old = "Longeveron Announces Updated Results from ELPIS II Trial"
        new = "Longeveron Announces Engagement of Lucid Capital Markets"
        pages = {"https://longeveron.com": homepage(old),
                 "https://investors.longeveron.com/news/default.aspx": NEWSROOM_JS,
                 "https://investors.longeveron.com/rss/pressrelease.aspx": feed(old)}
        self.run_sites(pages)
        self.assertEqual(self.sent, [])  # first look: quiet
        pages["https://longeveron.com"] = homepage(new, old)
        pages["https://investors.longeveron.com/rss/pressrelease.aspx"] = feed(new, old)
        self.run_sites(pages)
        self.assertEqual([t for t, _, _ in self.sent], ["LGVN website: new release"])
        self.assertEqual(self.sent[0][1], new)
        self.run_sites(pages)
        self.assertEqual(len(self.sent), 1)

    def test_homepage_only_counts_news_links(self):
        state.upsert_site("LGVN", homepage="https://longeveron.com", checked_ts=int(time.time()), manual=1)
        self.run_sites({"https://longeveron.com": homepage()})
        pages = {"https://longeveron.com": homepage("Longeveron Announces Engagement of Lucid Capital Markets")
                 .replace("our science and our mission today", "our science and our new mission today")}
        self.run_sites(pages)
        self.assertEqual([m for _, m, _ in self.sent], ["Longeveron Announces Engagement of Lucid Capital Markets"])

    def test_blocked_site_logs_once_and_is_skipped(self):
        state.upsert_site("LGVN", homepage="https://www.neuphoriatx.com", manual=1,
                          news_url="https://ir.neuphoriatx.com/news-events/news-releases", checked_ts=int(time.time()))
        pages = {"https://ir.neuphoriatx.com/news-events/news-releases": blocked,
                 "https://www.neuphoriatx.com": "<html></html>"}
        with self.assertLogs("jobs", "WARNING") as logs:
            self.run_sites(pages)
            web = self.run_sites(pages)
        self.assertEqual(sum("refuses automated access (HTTP 403)" in m for m in logs.output), 1)
        self.assertNotIn("https://ir.neuphoriatx.com/news-events/news-releases", web.calls)  # skipped while blocked
        self.assertFalse(any("Traceback" in m for m in logs.output))


class CallLabel(unittest.TestCase):
    def test_results_announcements_are_not_calls(self):
        self.assertEqual(jobs.classify("Longeveron Announces Updated Results from ELPIS II Phase 2b", "site"), "site")
        self.assertEqual(jobs.classify("Acme to Report Third Quarter 2026 Results on November 5", "news"), "call")
        self.assertEqual(jobs.classify("Acme Will Host Conference Call and Webcast", "news"), "call")


class PressWireTests(unittest.TestCase):
    def setUp(self):
        state.db.execute("DELETE FROM seen")
        state.db.execute("DELETE FROM watchlist")
        state.db.commit()
        state.add_ticker("LGVN", "Longeveron Inc", "test")
        self.sent = []
        p = mock.patch.object(jobs, "notify", side_effect=lambda t, m, **k: self.sent.append((t, m, k)) or True)
        p.start()
        self.addCleanup(p.stop)

    def items(self, *titles, age_h=0.5):
        return [{"title": t, "link": f"https://news.google.com/{i}", "ts": time.time() - age_h * 3600,
                 "source": "GlobeNewswire", "desc": ""} for i, t in enumerate(titles)]

    def run_wire(self, items):
        with mock.patch.object(cvr, "google_news", return_value=items) as gn:
            jobs.check_press_wires("LGVN")
        return gn

    def test_query_and_filters(self):
        gn = self.run_wire(self.items("Longeveron to Present at Conference - GlobeNewswire"))
        q = gn.call_args[0][0]
        self.assertTrue(q.startswith('"Longeveron" ('), q)
        self.assertIn("site:globenewswire.com", q)
        self.assertEqual(self.sent, [])  # first look: quiet
        self.run_wire(self.items(
            "Longeveron to Present at Conference - GlobeNewswire",
            "Longeveron Announces Engagement of Lucid Capital Markets - GlobeNewswire",
            "SHAREHOLDER ALERT: Pomerantz Law Firm Investigates Claims On Behalf of Longeveron Investors - PR Newswire",
            "Some Other Biotech Raises $50 Million - Business Wire"))
        self.assertEqual([m for _, m, _ in self.sent], ["Longeveron Announces Engagement of Lucid Capital Markets"])
        self.assertEqual(self.sent[0][0], "LGVN press release (GlobeNewswire)")

    def test_old_stories_and_already_seen_headlines_skip(self):
        self.run_wire([])
        state.mark(jobs._tkey("LGVN", "Longeveron Announces Engagement of Lucid Capital Markets"))  # site alerted it
        self.run_wire(self.items("Longeveron Announces Engagement of Lucid Capital Markets - GlobeNewswire") +
                      self.items("Longeveron Reports Second Quarter Results - GlobeNewswire", age_h=48))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
