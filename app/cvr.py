"""Contingent value rights (CVRs): find what a CVR pays on, then alert only on news about those assets.

discover(sym) starts from the ticker of the company that issued the CVR (often delisted or renamed):
  ticker -> SEC CIK -> the CVR agreement -> who owes the payments (the obligor), the companies the
  assets were sold or licensed to, the drug/program names, and the payment/milestone definitions.
  Drug names come from the merger prospectus and are kept only when they're discussed next to the CVR,
  its counterparties or "Legacy Assets"; the acquirer's own pipeline is left out.

check_cvrs() alerts on:
  - the obligor's SEC filings, but only those that mention an asset or a CVR payment,
  - any company's SEC filings that mention an asset (licensees, buyers, spin-out IPOs),
  - Google News stories that mention an asset.
"""
import hashlib
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from . import config as c
from .clients import http
from .notify import notify
from .store import state

log = logging.getLogger("cvr")
SEC = "https://www.sec.gov"
FTS = "https://efts.sec.gov/LATEST/search-index"
MAX_ALERTS_PER_SOURCE = 5

DRUG_RE = re.compile(
    r"\b([a-z]{3,}(?:ciguat|mab|tinib|lisib|ciclib|parib|rafenib|stat|parin|rsen|siran|cept|leucel|tocel|"
    r"glutide|gliflozin|gliptin|sartan|platin|taxel|mycin|floxacin|prazole|dipine|olol|vec|tide|nib))\b", re.I)
CODE_RE = re.compile(r"\b([A-Z]{2,5}-?\d{3,5}[A-Z]?)\b")
NOT_DRUGS = {"peptide", "polypeptide", "nucleotide", "oligonucleotide", "statute", "ecstat", "thermostat",
             "rheostat", "biostat", "tide", "olol", "glutide"}
NOT_CODES = {"EX", "ASC", "ASU", "CIK", "SEC", "ISO", "ICD", "FY", "USD", "CFR", "IRS", "HSR", "SAB", "FAS",
             "CVR", "NASDAQ", "NYSE", "GAAP", "DGCL", "MBCA", "RULE", "ITEM", "FORM", "PART", "NOTE", "SFAS", "TSR"}
COMPANY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&\-]+(?:\s+[A-Z][A-Za-z0-9&\-]+){0,3}\s+(?:Therapeutics|Pharmaceuticals|Pharma|"
    r"Biosciences|Biotherapeutics|Biopharma|Biotech|Biologics|Oncology|Sciences|Medical|Holdings|Laboratories))\b")
RIGHTS_AGENTS = ("computershare", "broadridge", "equiniti", "american stock transfer", "continental stock",
                 "colonial stock", "vstock", "issuer direct", "west coast stock")
DEF_RE = re.compile(r'"\s?([A-Z][A-Za-z0-9 .,\'/&()\-]{1,60}?)\s?"\s+(?:shall\s+)?(?:means|has the meaning|'
                    r'shall have the meaning|have the meaning)\b')
KEY_DEF_RE = re.compile(r"milestone|product|asset|compound|program|licens|royalt|proceeds|indication|approval|"
                        r"sale of|transaction|payment amount|regulatory|net sales|disposition", re.I)
BORING_DEFS = {"holder", "holders", "rights agent", "business day", "code", "notice", "party", "parties", "person",
               "loss", "losses", "assignee", "cvr register", "acting holders", "permitted transfer", "affiliate",
               "governmental authority", "law", "tax", "taxes", "agreement", "merger agreement", "effective time",
               "closing", "closing date", "officer's certificate", "board of directors", "company shares"}
CVR_WORDS = re.compile(r"\bCVRs?\b|contingent value rights?", re.I)
PAYMENT_RE = re.compile(r"(?:\bCVRs?\b|contingent value rights?)\W+(?:\w+\W+){0,25}?"
                        r"(?:payment|paid|payable|distribut|milestone|proceeds)", re.I)
CVR_ANCHORS = re.compile(r"\bCVRs?\b|contingent value|legacy assets?", re.I)
OBLIGOR_FORMS = {"8-K", "8-K/A", "10-Q", "10-K", "10-K/A", "6-K", "20-F", "40-F", "425", "SC TO-T", "SC TO-T/A", "SC 14D9"}
SEARCH_FORMS = "8-K,8-K/A,10-Q,10-K,6-K,20-F,40-F,S-1,S-1/A,F-1,F-1/A,424B4,424B1,425,DEF 14A,SC TO-T,SC 14D9"
PROSPECTUS_ORDER = ["424B3", "DEFM14A", "SC 14D9", "SC TO-T", "S-4/A", "S-4", "PREM14A", "DEFA14A", "8-K"]


# ------------------------------------------------------------ fetching
def _sec(url, timeout=30, **params):
    r = http.get(url, params=params or None, headers={"User-Agent": c.SEC_UA}, timeout=timeout)
    time.sleep(0.15)  # SEC fair access: <= 10 requests/second
    r.raise_for_status()
    return r


def _sec_text(url, limit=15_000_000):
    r = http.get(url, headers={"User-Agent": c.SEC_UA}, timeout=60, stream=True)
    time.sleep(0.15)
    r.raise_for_status()
    buf = b""
    for chunk in r.iter_content(262144):
        buf += chunk
        if len(buf) > limit:
            break
    r.close()
    return html_to_text(buf.decode(r.encoding or "utf-8", errors="replace"))


def html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    t = html.unescape(raw)
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("\xa0", " "), ("–", "-"),
                 ("—", "-")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def fts(q, ciks=None, forms=None, start=None):
    """SEC full-text search (filings since 2001). One page (up to 100 hits)."""
    params = {"q": q}
    if ciks:
        params["ciks"] = ciks
    if forms:
        params["forms"] = forms
    if start:
        params.update(dateRange="custom", startdt=start, enddt=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    data = _sec(FTS, **params).json()
    out = []
    for h in (data.get("hits") or {}).get("hits") or []:
        src = h.get("_source") or {}
        adsh, _, fname = h.get("_id", "").partition(":")
        adsh = src.get("adsh") or adsh
        ciks_ = src.get("ciks") or []
        if not (adsh and fname and ciks_):
            continue
        out.append({"adsh": adsh, "file": fname, "form": src.get("form") or "", "type": src.get("file_type") or "",
                    "date": src.get("file_date") or "", "ciks": ciks_, "names": src.get("display_names") or [],
                    "url": f"{SEC}/Archives/edgar/data/{int(ciks_[0])}/{adsh.replace('-', '')}/{fname}"})
    return out


def parse_display_name(dn):
    """'Akebia Therapeutics, Inc.  (AKBA)  (CIK 0001517022)' -> (name, ticker, cik)"""
    m = re.match(r"^(.*?)\s*(?:\(([^)]*)\))?\s*\(CIK (\d+)\)\s*$", dn or "")
    if not m:
        return dn, "", ""
    tick = (m.group(2) or "").split(",")[0].strip()
    return m.group(1).strip(), tick, m.group(3).zfill(10)


# ------------------------------------------------------------ names
def core(name):
    """'Akebia Therapeutics, Inc.' -> 'Akebia Therapeutics'"""
    n = re.sub(r"\([^)]*\)", " ", name or "")
    n = re.sub(r",?\s*\b(Inc|Corp|Corporation|Ltd|Limited|LLC|L\.L\.C|plc|AG|S\.A|SA|N\.V|NV|Co|Company|GmbH)\b\.?",
               " ", n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" ,.")


def short(name):
    """First distinctive word: 'Akebia Therapeutics, Inc.' -> 'Akebia'"""
    words = core(name).split()
    return words[0] if words else ""


def same_company(a, b):
    return bool(short(a)) and short(a).lower() == short(b).lower()


# ------------------------------------------------------------ parsing
def definitions(text):
    ms = list(DEF_RE.finditer(text))
    out = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out.setdefault(m.group(1).strip(), text[m.end():min(end, m.end() + 1200)].strip())
    return out


def key_definitions(defs):
    return [(t, d) for t, d in defs.items() if KEY_DEF_RE.search(t) and t.lower() not in BORING_DEFS]


def parse_obligor(text):
    m = re.search(r"by and (?:between|among)\s+(.{3,140}?),\s+(?:a|an)\s", text[:8000])
    return m.group(1).strip() if m else ""


def counterparties(text, defs, exclude):
    """Companies named in the asset/milestone definitions or the schedules, minus the deal parties."""
    scope = " ".join(d for _, d in key_definitions(defs))
    sched = text.rfind("Schedule 1")
    if sched >= 0:
        scope += " " + text[sched:sched + 4000]
    names = [m.group(1).strip() for m in COMPANY_RE.finditer(scope)]
    # companies given a short defined name ("Tisento" means Tisento Therapeutics Holdings Inc.)
    names += [m.group(1).strip() for m in (COMPANY_RE.match(d) for d in defs.values()) if m]
    found = []
    for name in names:
        low = name.lower()
        if any(same_company(name, x) for x in exclude if x) or any(r in low for r in RIGHTS_AGENTS) or \
                "merger sub" in low or low.startswith(("the ", "such ", "any ", "each ")):
            continue
        if not any(same_company(name, f) for f in found):
            found.append(name)
    # defined short names for those companies ("Tisento" means Tisento Therapeutics Holdings Inc.)
    aliases = [t for t, d in defs.items() if len(t.split()) == 1 and any(d.startswith(f) for f in found)
               and t.lower() not in BORING_DEFS]
    return found, aliases


def drug_candidates(text):
    names = {}
    for m in DRUG_RE.finditer(text):
        w = m.group(1).lower()
        if w not in NOT_DRUGS:
            names[w] = names.get(w, 0) + 1
    for m in CODE_RE.finditer(text):
        w = m.group(1)
        prefix = re.match(r"[A-Z]+", w).group(0)
        if prefix not in NOT_CODES:  # no year filter: real codes look like years too (IW-1973 = praliciguat)
            names[w] = names.get(w, 0) + 1
    return {k: v for k, v in names.items() if v >= 2}


def score_assets(text, candidates, anchor_names, other_names, window=400):
    """Keep drugs discussed next to the CVR/counterparties, not next to the acquirer's own pipeline."""
    anchors = [a.lower() for a in anchor_names if a]
    others = [o.lower() for o in other_names if o]
    low = text.lower()
    scored = []
    for name in candidates:
        near_cvr = near_other = 0
        for m in re.finditer(r"\b" + re.escape(name.lower()) + r"\b", low):
            w = low[max(0, m.start() - window):m.end() + window]
            if any(a in w for a in anchors) or CVR_ANCHORS.search(w):
                near_cvr += 1
            if any(o in w for o in others):
                near_other += 1
        if near_cvr >= 3 and near_cvr >= near_other * 0.5:
            scored.append((near_cvr, name))
    scored.sort(reverse=True)
    return [n for _, n in scored[:8]]


def cvr_summary(text):
    for sent in re.split(r"(?<=[.;])\s+", text):
        if 60 < len(sent) < 700 and CVR_WORDS.search(sent) and re.search(r"receive|entitle", sent, re.I) and \
                re.search(r"proceeds|milestone|payment|cash", sent, re.I):
            return sent.strip()
    return ""


def display_asset(name):
    return name if any(ch.isupper() for ch in name) else name[:1].upper() + name[1:]


# ------------------------------------------------------------ discovery
def resolve(sym):
    """Ticker (current or former) -> (cik, submissions json)."""
    cik = None
    try:
        r = _sec(f"{SEC}/cgi-bin/browse-edgar", action="getcompany", CIK=sym, type="", dateb="", owner="include",
                 count="1", output="atom")
        m = re.search(r"<cik>(\d+)</cik>", r.text)
        cik = m.group(1).zfill(10) if m else None
    except requests.RequestException as e:
        log.warning("EDGAR ticker lookup failed for %s: %s", sym, e)
    if not cik:
        from .jobs import cik_for
        cik = cik_for(sym)
    if not cik:
        return None, None
    return cik, _sec(f"https://data.sec.gov/submissions/CIK{cik}.json").json()


def target_name(sub):
    """The company's name while it had the CVR-era ticker: its latest former name, if it was renamed."""
    former = sorted(sub.get("formerNames") or [], key=lambda f: f.get("to") or "", reverse=True)
    return former[0]["name"] if former else sub.get("name", "")


def find_agreement(cik, name):
    hits = fts('"contingent value rights agreement"', ciks=cik)
    if not hits and name:
        hits = fts(f'"contingent value rights agreement" "{core(name)}"')
    # exhibits (the agreement itself) first, newest first
    hits.sort(key=lambda h: (not h["type"].upper().startswith("EX-"), -int((h["date"] or "0").replace("-", "") or 0)))
    fallback = None
    for h in hits[:8]:
        try:
            text = _sec_text(h["url"], limit=3_000_000)
        except requests.RequestException:
            continue
        head = text[:5000].upper()
        if "CONTINGENT VALUE RIGHTS AGREEMENT" not in head:
            continue
        executed = "FORM OF" not in head[:2500]
        if executed:
            return h, text, True
        fallback = fallback or (h, text, False)
    return fallback or (None, "", False)


def find_prospectus(cik):
    hits = fts('"contingent value"', ciks=cik, forms="424B3,DEFM14A,SC 14D9,SC TO-T,S-4,S-4/A,PREM14A,DEFA14A")
    rank = {f: i for i, f in enumerate(PROSPECTUS_ORDER)}
    hits.sort(key=lambda h: (rank.get(h["form"], 99), -int((h["date"] or "0").replace("-", "") or 0)))
    return hits[0] if hits else None


def discover(sym):
    """Everything needed to track a CVR. Raises LookupError if the ticker isn't found at the SEC."""
    sym = c.norm(sym)
    cik, sub = resolve(sym)
    if not cik:
        raise LookupError(f"{sym} not found at the SEC (current or former ticker)")
    tname, current = target_name(sub), sub.get("name", "")
    info = {"name": tname, "cik": cik, "current_name": current if current != tname else "",
            "current_tickers": sub.get("tickers") or [], "notes": [], "discovered_ts": int(time.time())}

    hit, text, executed = find_agreement(cik, tname)
    if not hit:
        info.update(obligor={"name": current or tname, "cik": cik, "ticker": (sub.get("tickers") or [""])[0]},
                    agreement=None, prospectus=None, counterparties=[], assets=[], companies=[],
                    key_terms=[], summary="")
        info["notes"].append("No CVR agreement found in SEC full-text search. Add the asset names yourself.")
        return info
    # the issuer's name in the deal: whichever of its names (current or former) the agreement uses most
    names = [current] + [f.get("name", "") for f in sub.get("formerNames") or []]
    best = max((n for n in names if short(n)), key=lambda n: text.lower().count(short(n).lower()), default=tname)
    if text.lower().count(short(best).lower()) > text.lower().count(short(tname).lower()):
        tname = best
    info["name"], info["current_name"] = tname, current if current != tname else ""
    info["agreement"] = {"url": hit["url"], "date": hit["date"], "form": hit["form"], "executed": executed}
    if not executed:
        info["notes"].append("Only a 'form of' CVR agreement was found; terms may differ slightly from the final one.")

    # who owes the CVR payments
    oname = parse_obligor(text) or tname
    obligor = {"name": oname, "cik": "", "ticker": ""}
    if same_company(oname, tname) or same_company(oname, current):
        obligor.update(cik=cik, ticker=(sub.get("tickers") or [""])[0])
        if current and current != tname:
            obligor["name"] = f"{current} (formerly {tname})"
    else:
        for dn in hit["names"]:
            n, t, k = parse_display_name(dn)
            if same_company(n, oname):
                obligor.update(cik=k, ticker=t)
        if not obligor["cik"]:
            try:
                r = _sec(f"{SEC}/cgi-bin/browse-edgar", action="getcompany", company=core(oname), type="",
                         dateb="", owner="include", count="1", output="atom")
                m = re.search(r"<cik>(\d+)</cik>", r.text)
                obligor["cik"] = m.group(1).zfill(10) if m else ""
            except requests.RequestException:
                pass
        if obligor["cik"] and not obligor["ticker"]:
            try:
                obligor["ticker"] = (_sec(f"https://data.sec.gov/submissions/CIK{obligor['cik']}.json").json()
                                     .get("tickers") or [""])[0]
            except requests.RequestException:
                pass
    info["obligor"] = obligor

    defs = definitions(text)
    cps, aliases = counterparties(text, defs, [tname, current, oname])
    info["counterparties"] = cps
    info["key_terms"] = [{"term": t, "text": d[:500] + ("..." if len(d) > 500 else "")}
                         for t, d in key_definitions(defs)[:12]]

    # drug/program names: from the prospectus if there is one, else from the agreement itself
    pro = find_prospectus(cik)
    ptext = ""
    if pro:
        info["prospectus"] = {"url": pro["url"], "date": pro["date"], "form": pro["form"]}
        try:
            ptext = _sec_text(pro["url"])
        except requests.RequestException as e:
            info["notes"].append(f"Couldn't read the merger prospectus ({e}).")
    else:
        info["prospectus"] = None
    body = ptext or text
    anchors = cps + aliases + [short(x) for x in cps]
    others = [short(current)] if current and not same_company(current, tname) else []
    if not same_company(oname, tname):
        others.append(short(oname))
    info["assets"] = [display_asset(a) for a in score_assets(body, drug_candidates(body), anchors, others)]
    info["summary"] = cvr_summary(ptext) or cvr_summary(text)
    info["companies"] = list(dict.fromkeys(aliases + [short(x) for x in cps if short(x)]))
    if not info["assets"]:
        info["notes"].append("No drug or program names found; alerts will use the counterparty names only.")
    return info


def add(sym, who="web"):
    sym = c.norm(sym)
    info = discover(sym)
    state.cvr_put(sym, info, who)
    return state.cvr_get(sym)


# ------------------------------------------------------------ tracking
def terms(cvr):
    """Assets are searched on their own; companies only together with the CVR issuer's name."""
    return list(dict.fromkeys((cvr.get("assets") or []) + (cvr.get("companies") or [])))


def _key(*parts):
    return ":".join(str(p) for p in parts)


def _h(s):
    return hashlib.md5(s.lower().encode()).hexdigest()[:12]


def find_terms(text, terms):
    """[(term, count)] for terms present in text (whole word, case-insensitive)."""
    out = []
    for t in terms:
        n = len(re.findall(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", text, re.I))
        if n:
            out.append((t, n))
    return out


def snippet(text, word, width=220):
    m = re.search(re.escape(word), text, re.I)
    if not m:
        return ""
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("..." if a else "") + text[a:b].strip() + ("..." if b < len(text) else "")


def relevance(text, terms):
    """(is_relevant, matched words, is_payment_news, snippet) for a filing's text."""
    found = find_terms(text, terms)
    pay = PAYMENT_RE.search(text)
    if not found and not pay:
        return False, [], False, ""
    focus = pay.group(0) if pay and not found else found[0][0]
    return True, [t for t, _ in found] or ["CVR payment"], bool(pay), snippet(text, focus)


def filing_docs(cik, acc, primary):
    """Primary document plus any press-release exhibits (EX-99.x)."""
    base = f"{SEC}/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
    docs = [base + primary]
    try:
        items = _sec(base + "index.json").json().get("directory", {}).get("item", [])
        docs += [base + i["name"] for i in items if re.search(r"ex-?_?99", i.get("name", ""), re.I)
                 and i["name"].lower().endswith((".htm", ".html", ".txt"))][:3]
    except (requests.RequestException, ValueError):
        pass
    return docs


def _seen_or_seed(key, first):
    """True if this item should be skipped: already handled, or recorded silently on a source's first run."""
    if state.has(key):
        return True
    if first:
        state.mark(key)
        return True
    return False


def check_obligor(cvr):
    sym, ob = cvr["sym"], cvr.get("obligor") or {}
    if not ob.get("cik"):
        return
    rec = _sec(f"https://data.sec.gov/submissions/CIK{ob['cik']}.json").json()["filings"]["recent"]
    seed = _key("seeded:cvr", sym, "obligor", ob["cik"])
    first = not state.has(seed)
    sent = 0
    for form, acc, fdate, doc in zip(rec["form"], rec["accessionNumber"], rec["filingDate"], rec["primaryDocument"]):
        if form.upper() not in OBLIGOR_FORMS:
            continue
        key = _key("cvrfile", sym, acc)
        if _seen_or_seed(key, first) or sent >= MAX_ALERTS_PER_SOURCE:
            continue
        text = ""
        for url in filing_docs(ob["cik"], acc, doc):
            try:
                text += " " + _sec_text(url, limit=8_000_000)
            except requests.RequestException as e:
                log.warning("CVR %s: couldn't read %s: %s", sym, url, e)
        if not text.strip():
            continue  # try again next cycle
        ok, words, pay, snip = relevance(text, terms(cvr))
        if not ok:
            state.mark(key)  # an obligor filing about something else: ignored on purpose
            continue
        who = short(ob["name"]) or ob["name"]
        is_8k = form.upper().startswith(("8-K", "6-K"))
        title = f"{sym} CVR: {who} {form}" + (" (CVR payment news)" if pay and is_8k else "")
        msg = f"{who} filed {form} on {fdate} mentioning {', '.join(words)}. {snip}"
        link = f"{SEC}/Archives/edgar/data/{int(ob['cik'])}/{acc.replace('-', '')}/{doc}"
        if notify(title, msg, url=link, url_title="View filing", kind="cvr", sym=sym, priority=1 if pay and is_8k else 0):
            state.mark(key)
            sent += 1
    state.mark(seed)


def search_queries(cvr):
    """(query, word that must appear) for SEC full-text search."""
    target = short(cvr.get("name", ""))
    q = [(f'"{a}"', a) for a in cvr.get("assets") or []]
    q += [(f'"{n}" "{target}"', n) for n in cvr.get("companies") or [] if target and n.lower() != target.lower()]
    return q


def check_sec_search(cvr):
    sym = cvr["sym"]
    ob_cik = (cvr.get("obligor") or {}).get("cik")
    known_names = {short(x).lower() for x in cvr.get("counterparties") or []} | \
                  {x.lower() for x in cvr.get("companies") or []}
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    sent = 0
    for q, term in search_queries(cvr):
        seed = _key("seeded:cvr", sym, "fts", _h(q))
        first = not state.has(seed)
        try:
            hits = fts(q, forms=SEARCH_FORMS, start=start)
        except (requests.RequestException, ValueError) as e:
            log.warning("CVR %s: SEC search failed for %s: %s", sym, q, e)
            continue
        seen_adsh = set()
        for h in hits:
            if h["adsh"] in seen_adsh:
                continue  # one alert per filing, even if several of its documents match
            seen_adsh.add(h["adsh"])
            key = _key("cvrfile", sym, h["adsh"])
            if _seen_or_seed(key, first) or sent >= MAX_ALERTS_PER_SOURCE:
                continue
            name, tick, fcik = parse_display_name(h["names"][0] if h["names"] else "")
            known = (fcik and fcik == ob_cik) or short(name).lower() in known_names
            try:
                text = _sec_text(h["url"], limit=8_000_000)
            except requests.RequestException:
                continue
            count = dict(find_terms(text, [term])).get(term, 0)
            if not known and count < 2:  # a passing mention, e.g. in an executive's bio
                state.mark(key)
                continue
            title = f"{sym} CVR asset: {short(name) or name} {h['form']} mentions {term}"
            msg = f"{name}{f' ({tick})' if tick else ''} filed {h['form']} on {h['date']}. {snippet(text, term)}"
            if notify(title, msg, url=h["url"], url_title="View filing", kind="cvr", sym=sym):
                state.mark(key)
                sent += 1
        state.mark(seed)


def news_queries(cvr):
    """(query, words of which one must appear in the story) for Google News."""
    target = short(cvr.get("name", ""))
    q = [(f'"{a}"', [a]) for a in cvr.get("assets") or []]
    q += [(f'"{n}" "{target}"', [n]) for n in cvr.get("companies") or [] if target and n.lower() != target.lower()]
    if target:
        q.append((f'"{target}" CVR', ["CVR", "contingent value"]))
    return q


def google_news(q):
    url = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
    r = http.get(url, headers={"User-Agent": c.SITE_UA}, timeout=20)
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        d = {ch.tag: (ch.text or "").strip() for ch in it}
        try:
            ts = parsedate_to_datetime(d.get("pubDate", "")).timestamp()
        except (TypeError, ValueError):
            ts = 0
        out.append({"title": html.unescape(d.get("title", "")), "link": d.get("link", ""), "ts": ts,
                    "source": d.get("source", ""), "desc": html_to_text(d.get("description", ""))})
    return out


def check_news(cvr):
    sym = cvr["sym"]
    cutoff = time.time() - c.CVR_NEWS_MAX_AGE_H * 3600
    sent = 0
    for q, need in news_queries(cvr):
        seed = _key("seeded:cvr", sym, "news", _h(q))
        first = not state.has(seed)
        try:
            items = google_news(q)
        except (requests.RequestException, ET.ParseError) as e:
            log.warning("CVR %s: news search failed for %s: %s", sym, q, e)
            continue
        for it in sorted(items, key=lambda i: i["ts"]):
            key = _key("cvrnews", sym, _h(re.sub(r"[^a-z0-9]", "", it["title"].lower())[:120]))
            if _seen_or_seed(key, first) or sent >= MAX_ALERTS_PER_SOURCE:
                continue
            if it["ts"] < cutoff or not find_terms(it["title"] + " " + it["desc"], need):
                state.mark(key)
                continue
            if notify(f"{sym} CVR news: {it['title'][:200]}", f"{it['source']} · about {need[0]}",
                      url=it["link"], url_title="Read", kind="cvr", sym=sym):
                state.mark(key)
                sent += 1
        state.mark(seed)


def check_cvrs():
    for cvr in state.cvr_list():
        for fn, on in ((check_obligor, True), (check_sec_search, c.CVR_SEC_SEARCH), (check_news, c.CVR_NEWS)):
            if not on:
                continue
            try:
                fn(cvr)
            except Exception:
                log.exception("CVR %s: %s failed", cvr["sym"], fn.__name__)
