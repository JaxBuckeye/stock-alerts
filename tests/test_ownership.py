"""Form 4 and Schedule 13D/13G tracking. Fixtures are real EDGAR documents.

Run inside the image (CI does this):
  docker run --rm -v "$PWD/tests:/srv/tests:ro" -e ... --entrypoint python IMAGE -m unittest discover -s tests -v
"""
import json
import pathlib
import unittest
from unittest import mock

from app import config as c
from app import jobs
from app.store import state

FIX = pathlib.Path(__file__).parent / "fixtures"
TSLA_CIK = "0001318605"


def fixture(name):
    return (FIX / name).read_bytes()


class Resp:
    def __init__(self, content=b"", data=None, status=200):
        self.content, self._data, self.status_code = content, data, status

    def json(self):
        return self._data if self._data is not None else json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise jobs.requests.HTTPError(f"HTTP {self.status_code}")


class FakeSEC:
    """Serves the ticker map, one company's submissions list, and filing documents by file name."""

    def __init__(self, filings):
        self.filings = filings  # list of (form, accession, date, primaryDocument)
        self.docs = {"ownership.xml": fixture("form4_tsla.xml"),
                     "primary_doc.xml": fixture("13d_elastic.xml")}
        self.urls = []

    def get(self, url, headers=None, timeout=None, **kw):
        self.urls.append(url)
        if url.endswith("company_tickers.json"):
            return Resp(data={"0": {"cik_str": int(TSLA_CIK), "ticker": "TSLA"}})
        if "/submissions/" in url:
            cols = list(zip(*self.filings)) if self.filings else [[], [], [], []]
            n = len(self.filings)
            return Resp(data={"filings": {"recent": {
                "form": list(cols[0]), "accessionNumber": list(cols[1]), "filingDate": list(cols[2]),
                "primaryDocument": list(cols[3]), "reportDate": [""] * n, "items": [""] * n}}})
        name = url.rsplit("/", 1)[-1]
        return Resp(content=self.docs[name]) if name in self.docs else Resp(status=404)


class ParseTests(unittest.TestCase):
    def test_form4(self):
        f = jobs.parse_form4(fixture("form4_tsla.xml"))
        self.assertEqual(f["issuer"], TSLA_CIK)
        self.assertIn("Taneja Vaibhav (Chief Financial Officer)", f["owners"])
        self.assertTrue({"M", "S"} <= f["codes"])
        self.assertTrue(any(p.startswith("Open-market sale: -") for p in f["parts"]))
        self.assertIsNotNone(f["after"])

    def test_13d(self):
        s = jobs.parse_stake(fixture("13d_elastic.xml"))
        self.assertEqual(s["issuer"], "0001707753")
        self.assertEqual(s["names"], ["PICTET ASSET MANAGEMENT SA"])
        self.assertEqual(s["pct"], 4.9)
        self.assertEqual(s["shares"], 5217779)
        self.assertTrue(s["purpose"].startswith("The Reporting Person acquired"))

    def test_13g_field_names(self):
        s = jobs.parse_stake(fixture("13g_vnda.xml"))
        self.assertEqual(s["issuer"], "0001347178")
        self.assertEqual(s["pct"], 7.0)
        self.assertEqual(len(s["names"]), 3)


class FlowTests(unittest.TestCase):
    """check_filings end to end with a fake SEC: seeding, alerts, filer-side skip, code filter."""

    BASE = [("10-Q", "0000000000-26-000001", "2026-10-01", "q.htm")]
    F4 = ("4", "0001104659-26-106432", "2026-10-27", "xslF345X06/ownership.xml")
    D13 = ("SCHEDULE 13D", "0001361570-26-000023", "2026-10-27", "xslSCHEDULE_13D_X02/primary_doc.xml")

    def setUp(self):
        state.db.execute("DELETE FROM seen")
        state.db.execute("DELETE FROM watchlist")
        state.db.commit()
        state.add_ticker("TSLA")
        jobs._cik_map, jobs._cik_loaded = {}, 0.0
        self.sent = []
        patches = [mock.patch.object(jobs, "notify", side_effect=self._notify),
                   mock.patch.object(jobs.time, "sleep"),
                   mock.patch.object(c, "TRACK_13D", True), mock.patch.object(c, "TRACK_FORM4", True),
                   mock.patch.object(c, "OWNERSHIP_FORMS", c.FORMS_13D | c.FORMS_4)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _notify(self, title, message, **kw):
        self.sent.append((title, message, kw))
        return True

    def run_with(self, filings):
        fake = FakeSEC(filings)
        with mock.patch.object(jobs, "http", fake):
            jobs.check_filings()
        return fake

    def test_seed_then_alert(self):
        self.run_with(self.BASE + [self.F4])           # first run: everything recorded silently
        self.assertEqual(self.sent, [])
        new_f4 = ("4", "0001104659-26-999999", "2026-10-27", "xslF345X06/ownership.xml")
        fake = self.run_with(self.BASE + [self.F4, new_f4])
        self.assertEqual(len(self.sent), 1)
        title, msg, kw = self.sent[0]
        self.assertTrue(title.startswith("TSLA insider sale: Taneja Vaibhav"), title)
        self.assertIn("Open-market sale", msg)
        self.assertEqual(kw["kind"], "insider")
        self.assertTrue(kw["url"].endswith("xslF345X06/ownership.xml"))     # human-readable link
        self.assertTrue(any(u.endswith("/000110465926999999/ownership.xml") for u in fake.urls))  # raw XML fetched
        self.run_with(self.BASE + [self.F4, new_f4])   # no repeat
        self.assertEqual(len(self.sent), 1)

    def test_13d_where_watched_company_is_filer_is_skipped(self):
        self.run_with(self.BASE)
        self.run_with(self.BASE + [self.D13])          # fixture's subject is Elastic, not TSLA
        self.assertEqual(self.sent, [])

    def test_13d_alert_for_subject_company(self):
        self.run_with(self.BASE)
        fake = FakeSEC(self.BASE + [self.D13])
        fake.docs["primary_doc.xml"] = fixture("13d_elastic.xml").replace(b"0001707753", TSLA_CIK.encode())
        with mock.patch.object(jobs, "http", fake):
            jobs.check_filings()
        self.assertEqual(len(self.sent), 1)
        title, msg, kw = self.sent[0]
        self.assertEqual(title, "TSLA 13D: PICTET ASSET MANAGEMENT SA 4.9%")
        self.assertIn("Purpose:", msg)
        self.assertEqual((kw["kind"], kw["priority"]), ("stake", 1))

    def test_form4_code_filter(self):
        self.run_with(self.BASE)
        with mock.patch.object(c, "FORM4_CODES", {"P"}):   # buys only; fixture is an exercise + sale
            self.run_with(self.BASE + [self.F4])
        self.assertEqual(self.sent, [])

    def test_unreadable_document_still_alerts(self):
        self.run_with(self.BASE)
        missing = ("4", "0001104659-26-555555", "2026-10-27", "xslF345X06/missing.xml")
        self.run_with(self.BASE + [missing])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], "TSLA insider filing (Form 4)")


if __name__ == "__main__":
    unittest.main()
