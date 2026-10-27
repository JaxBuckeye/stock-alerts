"""Polling jobs: prices, news, halts, SEC filings, earnings reminders, company websites."""
import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests

from . import config as c
from .clients import fh, http
from .notify import notify
from .store import state

log = logging.getLogger("jobs")
ET_TZ = ZoneInfo("America/New_York")

HALT_REASONS = {
    "T1": "News pending", "T2": "News released", "T5": "Volatility trading pause",
    "T6": "Extraordinary market activity", "T8": "ETF halt", "T12": "Additional info requested by Nasdaq",
    "H4": "Non-compliance", "H9": "Not current in filings", "H10": "SEC trading suspension",
    "H11": "Regulatory concern", "O1": "Operations halt", "M": "LULD pause", "LUDP": "Volatility trading pause",
    "LUDS": "Volatility pause (straddle)", "MWC1": "Market-wide circuit breaker L1",
    "MWC2": "Market-wide circuit breaker L2", "MWC3": "Market-wide circuit breaker L3", "IPO1": "IPO not yet trading",
}
ITEMS_8K = {
    "1.01": "Material Definitive Agreement", "1.02": "Termination of Material Agreement", "1.03": "Bankruptcy/Receivership",
    "2.01": "Acquisition/Disposition Completed", "2.02": "Results of Operations (earnings)",
    "2.03": "New Financial Obligation", "2.04": "Obligation Acceleration", "2.05": "Exit/Restructuring Costs",
    "2.06": "Material Impairments", "3.01": "Delisting/Listing Standard Notice", "3.02": "Unregistered Equity Sales",
    "3.03": "Change to Shareholder Rights", "4.01": "Change in Auditor", "4.02": "Non-Reliance on Prior Financials",
    "5.01": "Change in Control", "5.02": "Officer/Director Change", "5.03": "Bylaw/Fiscal Year Change",
    "5.07": "Shareholder Vote Results", "7.01": "Regulation FD Disclosure", "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}
URGENT_8K_ITEMS = {"1.03", "3.01", "4.02"}
CALL_RE = re.compile(
    r"(conference call|earnings call|webcast|investor day|analyst day|investor conference|fireside chat|"
    r"to host|will host|(announce|report|release)s?\b.{0,50}\b(results|earnings)|schedules?\b.{0,40}\b(call|results|earnings))",
    re.I)


def classify(text, default):
    return "call" if CALL_RE.search(text or "") else default


def _tkey(sym, text):
    """Shared across news + website monitor so the same headline isn't alerted twice."""
    t = re.sub(r"[^a-z0-9]", "", (text or "").lower())[:120]
    return f"title:{sym}:{hashlib.md5(t.encode()).hexdigest()[:16]}"


def _overflow(sym, count, label):
    notify(f"{sym}: +{count} more {label}", "More items were published; check the source.", kind="news", sym=sym)


# ------------------------------------------------------------ profiles
def lookup_profile(sym):
    prof = fh.get("/stock/profile2", symbol=sym)
    return prof if prof and prof.get("ticker") else None


# ---------------------------------------------------------------- prices
def check_prices():
    today = datetime.now(ET_TZ).date()
    for sym in state.tickers():
        try:
            q = fh.get("/quote", symbol=sym)
            if not q or not q.get("c") or not q.get("pc") or not q.get("t"):
                continue
            if datetime.fromtimestamp(q["t"], ET_TZ).date() != today:
                continue
            dp = q.get("dp")
            if dp is None:
                dp = (q["c"] - q["pc"]) / q["pc"] * 100
            if abs(dp) < c.MOVE_PCT:
                continue
            bucket = int(abs(dp) // c.MOVE_PCT)
            key = f"move:{sym}:{today}:{'up' if dp > 0 else 'down'}:{bucket}"
            if state.has(key):
                continue
            ok = notify(f"{sym} {'▲' if dp > 0 else '▼'} {dp:+.1f}%",
                        f"{sym} is {q['c']:.2f} ({dp:+.2f}%) vs prev close {q['pc']:.2f}. "
                        f"Day range {q['l']:.2f}-{q['h']:.2f}.",
                        url=f"https://finance.yahoo.com/quote/{sym}", url_title="Quote",
                        sound="cashregister" if dp > 0 else "falling", kind="move", sym=sym)
            if ok:
                state.mark(key)
        except Exception:
            log.exception("price check failed for %s", sym)


# ------------------------------------------------------------------ news
def check_news():
    now = datetime.now(timezone.utc)
    frm, to = (now - timedelta(days=1)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    cutoff = now.timestamp() - c.NEWS_MAX_AGE_H * 3600
    for sym in state.tickers():
        try:
            items = fh.get("/company-news", symbol=sym, **{"from": frm, "to": to}) or []
            seed_key = f"seeded:news:{sym}"
            first_run = not state.has(seed_key)
            items.sort(key=lambda i: i.get("datetime", 0))
            fresh = []
            for it in items:
                key = f"news:{sym}:{it.get('id')}"
                if state.has(key):
                    continue
                if first_run or it.get("datetime", 0) < cutoff:
                    state.mark(key)
                    continue
                fresh.append((key, it))
            send, extra = (fresh[-c.NEWS_MAX_PER_CYCLE:], fresh[:-c.NEWS_MAX_PER_CYCLE]) if fresh else ([], [])
            for key, it in send:
                head = it.get("headline", "(no headline)")
                tk = _tkey(sym, head)
                if state.has(tk):
                    state.mark(key)
                    continue
                kind = classify(head, "news")
                title = f"{sym} investor call/event" if kind == "call" else f"{sym} news ({it.get('source', '')})"
                if notify(title, head, url=it.get("url"), url_title="Read", kind=kind, sym=sym):
                    state.mark(key)
                    state.mark(tk)
            if extra:
                _overflow(sym, len(extra), "headlines")
                for key, _ in extra:
                    state.mark(key)
            state.mark(seed_key)
        except Exception:
            log.exception("news check failed for %s", sym)


# ----------------------------------------------------------------- halts
def check_halts():
    r = http.get("https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts", headers={"User-Agent": c.SEC_UA}, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    first_run = not state.has("seeded:halts")
    watch = set(state.tickers())
    for item in root.iter("item"):
        d = {ch.tag.split("}")[-1]: (ch.text or "").strip() for ch in item}
        sym = c.norm(d.get("IssueSymbol", ""))
        if not sym:
            continue
        halt_id = f"{sym}:{d.get('HaltDate')}:{d.get('HaltTime')}"
        code = d.get("ReasonCode", "")
        reason = HALT_REASONS.get(code, code or "unspecified")
        name = d.get("IssueName", sym)
        events = [(f"halt:{halt_id}", "HALTED",
                   f"{name} halted at {d.get('HaltTime')} ET on {d.get('Market', '')}. Reason: {reason} ({code}).")]
        if d.get("ResumptionTradeTime"):
            events.append((f"resume:{halt_id}", "RESUMING",
                           f"{name} resumes trading at {d.get('ResumptionTradeTime')} ET "
                           f"(quotes {d.get('ResumptionQuoteTime')}). Halt reason: {reason} ({code})."))
        for key, label, msg in events:
            if state.has(key):
                continue
            if first_run or sym not in watch:
                state.mark(key)
                continue
            if notify(f"{sym} {label}", msg, url="https://www.nasdaqtrader.com/trader.aspx?id=TradeHalts",
                      url_title="Halt list", priority=1, sound="siren", kind="halt", sym=sym):
                state.mark(key)
    state.mark("seeded:halts")


# -------------------------------------------------------------- filings
_cik_map, _cik_loaded = {}, 0.0


def cik_for(sym):
    global _cik_map, _cik_loaded
    if not _cik_map or time.time() - _cik_loaded > 86400:
        r = http.get("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": c.SEC_UA}, timeout=30)
        r.raise_for_status()
        _cik_map = {c.norm(v["ticker"]): str(v["cik_str"]).zfill(10) for v in r.json().values()}
        _cik_loaded = time.time()
    return _cik_map.get(sym)


def check_filings():
    forms_sig = hashlib.md5(",".join(sorted(c.FORMS)).encode()).hexdigest()[:6]
    for sym in state.tickers():
        try:
            cik = cik_for(sym)
            if not cik:
                log.warning("No CIK found for %s (ETF/foreign?)", sym)
                continue
            r = http.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers={"User-Agent": c.SEC_UA}, timeout=20)
            r.raise_for_status()
            rec = r.json()["filings"]["recent"]
            n = len(rec["form"])
            # seed key includes the form list: changing SEC_FORMS re-seeds silently instead of flooding
            seed_key = f"seeded:filings:{sym}:{forms_sig}"
            first_run = not state.has(seed_key)
            for form, acc, fdate, doc, period, items in zip(
                rec["form"], rec["accessionNumber"], rec["filingDate"], rec["primaryDocument"],
                rec.get("reportDate") or [""] * n, rec.get("items") or [""] * n,
            ):
                if form.upper() not in c.FORMS:
                    continue
                key = f"filing:{sym}:{acc}"
                if state.has(key):
                    continue
                if first_run:
                    state.mark(key)
                    continue
                codes = [x.strip() for x in (items or "").split(",") if x.strip()]
                detail = "; ".join(f"{x} {ITEMS_8K.get(x, '')}".strip() for x in codes)
                msg = f"{sym} filed {form} on {fdate}."
                if form.upper().startswith("10-") and period:
                    msg += f" Period ending {period}."
                if detail:
                    msg += f" Items: {detail}"
                link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"
                urgent = bool(URGENT_8K_ITEMS & set(codes))
                if notify(f"{sym} filed {form}", msg, url=link, url_title="View filing",
                          priority=1 if urgent else 0, kind="filing", sym=sym):
                    state.mark(key)
            state.mark(seed_key)
            time.sleep(0.2)  # SEC fair access: <= 10 req/s
        except Exception:
            log.exception("filing check failed for %s", sym)


# ------------------------------------------------------------- earnings
_earn_cache = {}
_earn_warned = False


def _money(x):
    if x is None:
        return "n/a"
    for div, suf in ((1e9, "B"), (1e6, "M")):
        if abs(x) >= div:
            return f"${x / div:.2f}{suf}"
    return f"${x:,.0f}"


def check_earnings():
    global _earn_warned
    now_et = datetime.now(ET_TZ)
    if now_et.hour < c.EARNINGS_REMIND_HOUR_ET:
        return
    today = now_et.date()
    hours = {"bmo": "before market open", "amc": "after market close", "dmh": "during market hours"}
    for sym in state.tickers():
        try:
            cached = _earn_cache.get(sym)
            if not cached or time.time() - cached[0] > 6 * 3600:
                try:
                    data = fh.get("/calendar/earnings", symbol=sym,
                                  **{"from": today.isoformat(), "to": (today + timedelta(days=21)).isoformat()})
                except requests.HTTPError as e:
                    if not _earn_warned:
                        log.warning("Earnings calendar unavailable (%s); reminders disabled until it works", e)
                        _earn_warned = True
                    data = None
                cached = _earn_cache[sym] = (time.time(), (data or {}).get("earningsCalendar") or [])
            for ev in cached[1]:
                days = (date.fromisoformat(ev["date"]) - today).days
                if days not in c.EARNINGS_REMINDERS:
                    continue
                key = f"earn:{sym}:{ev['date']}:{days}d"
                if state.has(key):
                    continue
                when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
                d = date.fromisoformat(ev["date"])
                q = f" (Q{ev['quarter']} {ev['year']})" if ev.get("quarter") and ev.get("year") else ""
                site = state.get_site(sym) or {}
                msg = (f"{state.get_name(sym) or sym} reports earnings{q} {when}, {d:%a %b %d}, "
                       f"{hours.get(ev.get('hour'), 'time TBD')}. "
                       f"EPS est {ev.get('epsEstimate') if ev.get('epsEstimate') is not None else 'n/a'}, "
                       f"revenue est {_money(ev.get('revenueEstimate'))}. "
                       f"Call/webcast details are usually on the investor relations page.")
                if notify(f"📅 {sym} earnings {when}", msg,
                          url=site.get("news_url") or f"https://finance.yahoo.com/quote/{sym}",
                          url_title="Details", kind="earnings", sym=sym):
                    state.mark(key)
        except Exception:
            log.exception("earnings check failed for %s", sym)


# -------------------------------------------------------- company sites
class _Links(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.feeds, self._href, self._text = base, [], [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and "alternate" in (a.get("rel") or "").lower() and a.get("href") and \
                any(t in (a.get("type") or "").lower() for t in ("rss", "atom")):
            self.feeds.append(urljoin(self.base, a["href"]))
        elif tag == "a" and a.get("href"):
            self._href, self._text = urljoin(self.base, a["href"]), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


_robots = {}


def robots_ok(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    ent = _robots.get(base)
    if not ent or time.time() - ent[0] > 86400:
        rp = RobotFileParser()
        try:
            r = http.get(base + "/robots.txt", headers={"User-Agent": c.SITE_UA}, timeout=10)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        rp.modified()
        ent = _robots[base] = (time.time(), rp)
    return ent[1].can_fetch(c.SITE_UA, url)


def fetch_text(url):
    if not robots_ok(url):
        log.info("robots.txt disallows %s; skipping", url)
        return None
    r = http.get(url, headers={"User-Agent": c.SITE_UA,
                               "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml"},
                 timeout=20, stream=True)
    r.raise_for_status()
    buf = b""
    for chunk in r.iter_content(65536):
        buf += chunk
        if len(buf) > 2_000_000:
            break
    r.close()
    return buf.decode(r.encoding or "utf-8", errors="replace")


def _local(tag):
    return tag.split("}")[-1]


def parse_feed(text):
    root = ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", text).encode("utf-8"))
    out = []
    for it in root.iter():
        if _local(it.tag) not in ("item", "entry"):
            continue
        d = {_local(ch.tag): ch for ch in it}
        title = (d["title"].text or "").strip() if "title" in d else ""
        link = ""
        if "link" in d:
            link = (d["link"].get("href") or d["link"].text or "").strip()
        iid = ((d["guid"].text if "guid" in d else None) or (d["id"].text if "id" in d else None) or link or title).strip()
        if title:
            out.append((iid, title, link))
    return out


def _clean(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def page_items(base, html):
    p = _Links(base)
    p.feed(html)
    out, seen = [], set()
    for href, text in p.links:
        if urlparse(href).scheme not in ("http", "https") or len(text.split()) < 5 or len(text) > 300:
            continue
        cl = _clean(href)
        if cl == _clean(base) or cl in seen:
            continue
        seen.add(cl)
        out.append((cl, text, href))
    return out


def parse_items(src, text):
    head = text.lstrip()[:300].lower()
    if "<rss" in head or "<feed" in head or head.startswith("<?xml"):
        return parse_feed(text)
    return page_items(src, text)


def discover(homepage):
    """Find a newsroom page and, if one exists, its RSS/Atom feed."""
    html = fetch_text(homepage)
    if not html:
        return None, None
    p = _Links(homepage)
    p.feed(html)
    root = ".".join(urlparse(homepage).netloc.split(".")[-2:])
    best, best_score = None, 0
    for href, text in p.links:
        if urlparse(href).scheme not in ("http", "https") or not urlparse(href).netloc.endswith(root):
            continue
        h, t = href.lower(), text.lower()
        blob = h + " " + t
        if any(k in blob for k in ("press-release", "press release", "pressrelease", "news-release", "newsroom", "news room")):
            score = 5
        elif "news" in blob:
            score = 3
        elif "investor" in blob or "//ir." in h:
            score = 2
        else:
            continue
        if score > best_score:
            best, best_score = href.split("#")[0], score
    if not best:
        return None, None
    feed = None
    try:
        page = fetch_text(best)
        if page:
            p2 = _Links(best)
            p2.feed(page)
            feed = next((f for f in p2.feeds if any(k in f.lower() for k in ("press", "news", "release"))),
                        p2.feeds[0] if p2.feeds else None)
    except requests.RequestException:
        pass
    return best, feed


def ensure_site(sym):
    if state.get_name(sym) is None:
        prof = fh.get("/stock/profile2", symbol=sym) or {}
        state.set_name(sym, prof.get("name") or sym)
        if prof.get("weburl"):
            state.upsert_site(sym, homepage=prof["weburl"])
    row = state.get_site(sym)
    if row and row["homepage"] and not row["manual"] and not (row["news_url"] or row["feed_url"]) \
            and time.time() - (row["checked_ts"] or 0) > 7 * 86400:
        news_url, feed = discover(row["homepage"])
        state.upsert_site(sym, news_url=news_url, feed_url=feed, checked_ts=int(time.time()))
        log.info("Site discovery %s: newsroom=%s feed=%s", sym, news_url, feed)


def check_sites():
    for sym in state.tickers():
        try:
            ensure_site(sym)
            row = state.get_site(sym)
            src = row and (row["feed_url"] or row["news_url"])
            if not src:
                continue
            text = fetch_text(src)
            if not text:
                continue
            seed_key = f"seeded:site:{sym}:{hashlib.md5(src.encode()).hexdigest()[:8]}"
            first_run = not state.has(seed_key)
            fresh = []
            for iid, title, link in ((i[0], i[1], i[2] if len(i) > 2 else i[0]) for i in parse_items(src, text)):
                key = f"site:{sym}:{hashlib.md5(iid.encode()).hexdigest()[:16]}"
                if state.has(key):
                    continue
                if first_run:
                    state.mark(key)
                    continue
                fresh.append((key, title, link))
            for key, title, link in fresh[:c.SITE_MAX_PER_CYCLE]:
                tk = _tkey(sym, title)
                if state.has(tk):
                    state.mark(key)
                    continue
                kind = classify(title, "site")
                label = f"{sym} investor call/event" if kind == "call" else f"{sym} website: new release"
                if notify(label, title, url=link, url_title="Read", kind=kind, sym=sym):
                    state.mark(key)
                    state.mark(tk)
            extra = fresh[c.SITE_MAX_PER_CYCLE:]
            if extra:
                _overflow(sym, len(extra), "website items")
                for key, _, _ in extra:
                    state.mark(key)
            state.mark(seed_key)
        except Exception:
            log.exception("site check failed for %s", sym)
        time.sleep(1)  # be polite between company sites
