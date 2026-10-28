"""CVR discovery parsing (real Cyclerion CVR agreement) and the relevance filters used for alerts."""
import pathlib
import time
import unittest
from unittest import mock

from app import cvr
from app.store import state

FIX = pathlib.Path(__file__).parent / "fixtures"
AGREEMENT = cvr.html_to_text((FIX / "cvr_agreement_cycn.htm").read_text(encoding="utf-8", errors="replace"))

CYCN = {"sym": "CYCN", "name": "Cyclerion Therapeutics, Inc.", "cik": "0001755237",
        "obligor": {"name": "Korsana Biosciences, Inc. (formerly Cyclerion Therapeutics, Inc.)",
                    "cik": "0001755237", "ticker": "KRSA"},
        "counterparties": ["Akebia Therapeutics", "Tisento Therapeutics Holdings"],
        "assets": ["Praliciguat", "Zagociguat", "CY3018"], "companies": ["Tisento", "Akebia"]}


class AgreementParsing(unittest.TestCase):
    def test_obligor_is_first_party(self):
        self.assertEqual(cvr.parse_obligor(AGREEMENT), "Cyclerion Therapeutics, Inc.")

    def test_definitions_and_key_terms(self):
        defs = cvr.definitions(AGREEMENT)
        self.assertIn("Legacy Assets", defs)
        self.assertTrue(defs["Legacy Assets"].startswith("(i) the Tisento Shares"))
        keys = [t for t, _ in cvr.key_definitions(defs)]
        self.assertIn("Legacy Assets", keys)
        self.assertIn("CVR Proceeds", keys)
        self.assertNotIn("Business Day", keys)
        self.assertNotIn("Holder", keys)

    def test_counterparties_exclude_deal_parties(self):
        defs = cvr.definitions(AGREEMENT)
        cps, aliases = cvr.counterparties(AGREEMENT, defs, ["Cyclerion Therapeutics, Inc.", "Korsana Biosciences, Inc."])
        self.assertIn("Akebia Therapeutics", cps)
        self.assertTrue(any(x.startswith("Tisento Therapeutics") for x in cps), cps)
        self.assertIn("Tisento", aliases)
        self.assertFalse(any("Cyclerion" in x or "Korsana" in x or "Broadridge" in x for x in cps), cps)

    def test_summary_sentence(self):
        self.assertTrue(cvr.CVR_WORDS.search(cvr.cvr_summary(AGREEMENT) or "CVR"))


class AssetScoring(unittest.TestCase):
    def test_keeps_cvr_assets_drops_acquirer_pipeline(self):
        cvr_para = ("Cyclerion licensed praliciguat to Akebia under the Akebia License Agreement, and CVR holders "
                    "receive net proceeds. Cyclerion sold zagociguat and CY3018 to Tisento; proceeds from the Tisento "
                    "Shares are Legacy Assets for the CVR. ")
        own_para = ("Korsana is developing trontinemab-like antibodies; lecanemab and donanemab are approved "
                    "competitors to Korsana's lead program. ")
        text = (cvr_para + "x " * 300 + own_para + "y " * 300) * 4
        cands = cvr.drug_candidates(text)
        kept = cvr.score_assets(text, cands, ["Akebia", "Tisento"], ["Korsana"])
        self.assertIn("praliciguat", kept)
        self.assertIn("zagociguat", kept)
        self.assertIn("CY3018", kept)
        self.assertNotIn("lecanemab", kept)
        self.assertNotIn("donanemab", kept)

    def test_code_names_skip_boilerplate(self):
        cands = cvr.drug_candidates("Item 2.02 Form 8-K ASC 820 ASC 820 IRS-2023 IRS-2023 CY6463 CY6463 IW-1973 IW-1973")
        self.assertIn("CY6463", cands)
        self.assertIn("IW-1973", cands)
        self.assertFalse(any(k.startswith(("ASC", "IRS")) for k in cands), cands)


class Relevance(unittest.TestCase):
    def test_unrelated_obligor_8k_is_ignored(self):
        ok, *_ = cvr.relevance("Korsana announces Phase 1 data for its anti-amyloid antibody.", cvr.terms(CYCN))
        self.assertFalse(ok)

    def test_asset_mention_is_relevant(self):
        ok, words, pay, snip = cvr.relevance("Akebia reported topline data for praliciguat in DKD.", cvr.terms(CYCN))
        self.assertTrue(ok)
        self.assertIn("Praliciguat", words)
        self.assertFalse(pay)
        self.assertIn("praliciguat", snip)

    def test_cvr_payment_language(self):
        ok, words, pay, _ = cvr.relevance("The Company will make a payment to CVR holders of $0.12 per CVR "
                                          "following receipt of the milestone payment.", [])
        self.assertTrue(ok)
        self.assertTrue(pay)

    def test_company_terms_need_issuer_name_in_queries(self):
        q = dict(cvr.search_queries(CYCN))
        self.assertIn('"Praliciguat"', q)
        self.assertIn('"Akebia" "Cyclerion"', q)
        self.assertNotIn('"Akebia"', q)  # alone it would match every Akebia filing

    def test_display_names(self):
        self.assertEqual(cvr.parse_display_name("Akebia Therapeutics, Inc.  (AKBA)  (CIK 0001517022)"),
                         ("Akebia Therapeutics, Inc.", "AKBA", "0001517022"))
        self.assertEqual(cvr.short("Tisento Therapeutics Holdings Inc."), "Tisento")


class Resp:
    def __init__(self, data=None, content=b"", status=200):
        self._d, self.content, self.status_code, self.encoding, self.text = data, content, status, "utf-8", content.decode()

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise cvr.requests.HTTPError(str(self.status_code))

    def iter_content(self, n):
        yield self.content

    def close(self):
        pass


class ObligorFlow(unittest.TestCase):
    """Obligor filings: seeded quietly, then only CVR-relevant ones alert."""

    def setUp(self):
        state.db.execute("DELETE FROM seen")
        state.db.commit()
        self.docs = {}
        self.filings = [("8-K", "0000000000-26-000001", "2026-09-01", "old.htm")]
        self.sent = []
        for p in (mock.patch.object(cvr, "notify", side_effect=lambda t, m, **k: self.sent.append((t, m, k)) or True),
                  mock.patch.object(cvr.time, "sleep"), mock.patch.object(cvr, "http", self)):
            p.start()
            self.addCleanup(p.stop)

    def get(self, url, **kw):
        if "/submissions/" in url:
            cols = list(zip(*self.filings))
            return Resp({"filings": {"recent": {"form": list(cols[0]), "accessionNumber": list(cols[1]),
                                                "filingDate": list(cols[2]), "primaryDocument": list(cols[3])}}})
        if url.endswith("index.json"):
            return Resp({"directory": {"item": []}})
        name = url.rsplit("/", 1)[-1]
        return Resp(content=self.docs.get(name, b"").encode() if isinstance(self.docs.get(name), str) else
                    self.docs.get(name, b""), status=200 if name in self.docs else 404)

    def test_flow(self):
        self.docs["old.htm"] = "<p>CVR holders praliciguat</p>"
        cvr.check_obligor(CYCN)
        self.assertEqual(self.sent, [])  # first run: quiet
        self.filings += [("8-K", "0000000000-26-000002", "2026-10-20", "pipeline.htm"),
                         ("8-K", "0000000000-26-000003", "2026-10-27", "cvr.htm"),
                         ("4", "0000000000-26-000004", "2026-10-27", "f4.xml")]
        self.docs["pipeline.htm"] = "<p>Korsana doses first patient with its antibody.</p>"
        self.docs["cvr.htm"] = "<p>Tisento Therapeutics completed its IPO. CVR holders will receive a payment.</p>"
        cvr.check_obligor(CYCN)
        self.assertEqual(len(self.sent), 1)
        title, msg, kw = self.sent[0]
        self.assertTrue(title.startswith("CYCN CVR: Korsana 8-K"), title)
        self.assertIn("Tisento", msg)
        self.assertEqual((kw["kind"], kw["sym"], kw["priority"]), ("cvr", "CYCN", 1))
        cvr.check_obligor(CYCN)
        self.assertEqual(len(self.sent), 1)  # no repeats


class NewsFlow(unittest.TestCase):
    def setUp(self):
        state.db.execute("DELETE FROM seen")
        state.db.commit()
        self.sent = []
        p = mock.patch.object(cvr, "notify", side_effect=lambda t, m, **k: self.sent.append((t, m, k)) or True)
        p.start()
        self.addCleanup(p.stop)

    def items(self, *titles):
        now = time.time()
        return [{"title": t, "link": f"https://news.example/{i}", "ts": now - 60, "source": "Wire", "desc": ""}
                for i, t in enumerate(titles)]

    def test_news_requires_term_and_seeds_quietly(self):
        with mock.patch.object(cvr, "google_news", return_value=self.items("Old praliciguat story")):
            cvr.check_news(CYCN)
        self.assertEqual(self.sent, [])
        new = self.items("Old praliciguat story", "Akebia starts praliciguat Phase 2", "Unrelated biotech headline")
        with mock.patch.object(cvr, "google_news", return_value=new):
            cvr.check_news(CYCN)
        titles = [t for t, _, _ in self.sent]
        self.assertIn("CYCN CVR news: Akebia starts praliciguat Phase 2", titles)
        self.assertFalse(any("Unrelated" in t for t in titles))


if __name__ == "__main__":
    unittest.main()
