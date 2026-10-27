"""Stock alerts -> Pushover.

Alerts on: company news, trading halts/resumes, moves >= MOVE_PCT, and 10-Q filings.
Sources: Finnhub (quotes + news), Nasdaq Trader halts RSS, SEC EDGAR (filings).
"""
import logging
import os
import signal
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ----------------------------------------------------------------- config
def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Missing required environment variable: {name}")
    return val


PUSHOVER_TOKEN = env("PUSHOVER_APP_TOKEN", required=True)
PUSHOVER_USER = env("PUSHOVER_USER_KEY", required=True)
FINNHUB_KEY = env("FINNHUB_API_KEY", required=True)
SEC_UA = env("SEC_USER_AGENT", required=True)  # e.g. "Jane Doe jane@example.com"

def norm(sym):
    return sym.strip().upper().replace("-", ".")

WATCHLIST = [norm(s) for s in env("WATCHLIST", required=True).split(",") if s.strip()]
MOVE_PCT = float(env("MOVE_THRESHOLD_PCT", "5"))
FORMS = {f.strip().upper() for f in env("SEC_FORMS", "10-Q").split(",") if f.strip()}
NEWS_MAX_AGE_H = float(env("NEWS_MAX_AGE_HOURS", "6"))
NEWS_MAX_PER_CYCLE = int(env("NEWS_MAX_PER_CYCLE", "3"))
DRY_RUN = env("DRY_RUN", "false").lower() in ("1", "true", "yes")

INTERVALS = {
    "halts": int(env("HALT_INTERVAL", "30")),
    "prices": int(env("PRICE_INTERVAL", "60")),
    "news": int(env("NEWS_INTERVAL", "300")),
    "filings": int(env("FILING_INTERVAL", "300")),
}
ENABLED = {
    "halts": env("ENABLE_HALTS", "true").lower() == "true",
    "prices": env("ENABLE_PRICES", "true").lower() == "true",
    "news": env("ENABLE_NEWS", "true").lower() == "true",
    "filings": env("ENABLE_FILINGS", "true").lower() == "true",
}

DATA_DIR = env("DATA_DIR", "/data")
HEARTBEAT = os.path.join(DATA_DIR, "heartbeat")
ET_TZ = ZoneInfo("America/New_York")

logging.basicConfig(
    level=env("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("stock-alerts")

HALT_REASONS = {
    "T1": "News pending", "T2": "News released", "T5": "Volatility trading pause",
    "T6": "Extraordinary market activity", "T8": "ETF halt", "T12": "Additional info requested by Nasdaq",
    "H4": "Non-compliance", "H9": "Not current in filings", "H10": "SEC trading suspension",
    "H11": "Regulatory concern", "O1": "Operations halt", "M": "LULD pause",
    "LUDP": "Volatility trading pause", "LUDS": "Volatility pause (straddle)", "MWC1": "Market-wide circuit breaker L1",
    "MWC2": "Market-wide circuit breaker L2", "MWC3": "Market-wide circuit breaker L3", "IPO1": "IPO not yet trading",
}

# ------------------------------------------------------------------ state
class State:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, ts INTEGER)")
        self.db.commit()

    def has(self, key):
        return self.db.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone() is not None

    def mark(self, key):
        self.db.execute("INSERT OR IGNORE INTO seen VALUES (?,?)", (key, int(time.time())))
        self.db.commit()

    def prune(self, days=30):
        self.db.execute("DELETE FROM seen WHERE ts < ? AND key NOT LIKE 'seeded:%'",
                        (int(time.time()) - days * 86400,))
        self.db.commit()


state = State(os.path.join(DATA_DIR, "state.db"))
http = requests.Session()

# --------------------------------------------------------------- pushover
def notify(title, message, url=None, url_title=None, priority=0, sound=None):
    if DRY_RUN:
        log.info("[DRY RUN] %s | %s | %s", title, message, url)
        return True
    payload = {
        "token": PUSHOVER_TOKEN, "user": PUSHOVER_USER,
        "title": title[:250], "message": message[:1024], "priority": priority,
    }
    if url:
        payload["url"] = url[:512]
        payload["url_title"] = (url_title or "Open")[:100]
    if sound:
        payload["sound"] = sound
    for attempt in range(3):
        try:
            r = http.post("https://api.pushover.net/1/messages.json", data=payload, timeout=15)
            if r.status_code == 200:
                return True
            if 400 <= r.status_code < 500:
                log.error("Pushover rejected message: %s %s", r.status_code, r.text)
                return False
            log.warning("Pushover %s, retrying", r.status_code)
        except requests.RequestException as e:
            log.warning("Pushover error: %s", e)
        time.sleep(2 ** attempt)
    return False

# ---------------------------------------------------------------- finnhub
class Finnhub:
    base = "https://finnhub.io/api/v1"
    min_gap = 1.05  # free tier: 60 calls/min

    def __init__(self, key):
        self.key, self.last = key, 0.0

    def get(self, path, **params):
        wait = self.min_gap - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        r = http.get(self.base + path, params={**params, "token": self.key}, timeout=15)
        self.last = time.monotonic()
        if r.status_code == 429:
            log.warning("Finnhub rate limited; backing off 30s")
            time.sleep(30)
            return None
        r.raise_for_status()
        return r.json()


fh = Finnhub(FINNHUB_KEY)

# ------------------------------------------------------------------- jobs
def check_prices():
    today = datetime.now(ET_TZ).date()
    for sym in WATCHLIST:
        try:
            q = fh.get("/quote", symbol=sym)
            if not q or not q.get("c") or not q.get("pc") or not q.get("t"):
                continue
            if datetime.fromtimestamp(q["t"], ET_TZ).date() != today:
                continue  # stale (weekend / holiday / no trades yet)
            dp = q.get("dp")
            if dp is None:
                dp = (q["c"] - q["pc"]) / q["pc"] * 100
            if abs(dp) < MOVE_PCT:
                continue
            # one alert per direction per day, plus another each time it crosses the next multiple
            bucket = int(abs(dp) // MOVE_PCT)
            key = f"move:{sym}:{today}:{'up' if dp > 0 else 'down'}:{bucket}"
            if state.has(key):
                continue
            arrow = "▲" if dp > 0 else "▼"
            ok = notify(
                f"{sym} {arrow} {dp:+.1f}%",
                f"{sym} is {q['c']:.2f} ({dp:+.2f}%) vs prev close {q['pc']:.2f}. "
                f"Day range {q['l']:.2f}-{q['h']:.2f}.",
                url=f"https://finance.yahoo.com/quote/{sym}", url_title="Quote",
                sound="cashregister" if dp > 0 else "falling",
            )
            if ok:
                state.mark(key)
        except Exception:
            log.exception("price check failed for %s", sym)


def check_news():
    now = datetime.now(timezone.utc)
    frm = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    to = now.strftime("%Y-%m-%d")
    cutoff = now.timestamp() - NEWS_MAX_AGE_H * 3600
    for sym in WATCHLIST:
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
                    state.mark(key)  # don't alert on backlog
                    continue
                fresh.append((key, it))
            for key, it in fresh[-NEWS_MAX_PER_CYCLE:]:
                ok = notify(
                    f"{sym} news ({it.get('source', '')})",
                    it.get("headline", "(no headline)"),
                    url=it.get("url"), url_title="Read",
                )
                if ok:
                    state.mark(key)
            extra = fresh[:-NEWS_MAX_PER_CYCLE]
            if extra:
                notify(f"{sym}: +{len(extra)} more headlines",
                       "Additional news items were released; see your news feed.")
                for key, _ in extra:
                    state.mark(key)
            state.mark(seed_key)
        except Exception:
            log.exception("news check failed for %s", sym)


def check_halts():
    r = http.get("https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts",
                 headers={"User-Agent": SEC_UA}, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    first_run = not state.has("seeded:halts")
    watch = set(WATCHLIST)
    for item in root.iter("item"):
        d = {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
        sym = norm(d.get("IssueSymbol", ""))
        if not sym:
            continue
        halt_id = f"{sym}:{d.get('HaltDate')}:{d.get('HaltTime')}"
        code = d.get("ReasonCode", "")
        reason = HALT_REASONS.get(code, code or "unspecified")
        events = [(f"halt:{halt_id}", "HALTED",
                   f"{d.get('IssueName', sym)} halted at {d.get('HaltTime')} ET on "
                   f"{d.get('Market', '')}. Reason: {reason} ({code}).")]
        if d.get("ResumptionTradeTime"):
            events.append((f"resume:{halt_id}", "RESUMING",
                           f"{d.get('IssueName', sym)} resumes trading at "
                           f"{d.get('ResumptionTradeTime')} ET (quotes {d.get('ResumptionQuoteTime')}). "
                           f"Halt reason: {reason} ({code})."))
        for key, label, msg in events:
            if state.has(key):
                continue
            if first_run or sym not in watch:
                state.mark(key)
                continue
            if notify(f"{sym} {label}", msg,
                      url=f"https://www.nasdaqtrader.com/trader.aspx?id=TradeHalts",
                      url_title="Halt list", priority=1, sound="siren"):
                state.mark(key)
    state.mark("seeded:halts")


_cik_map, _cik_loaded = {}, 0.0

def cik_for(sym):
    global _cik_map, _cik_loaded
    if not _cik_map or time.time() - _cik_loaded > 86400:
        r = http.get("https://www.sec.gov/files/company_tickers.json",
                     headers={"User-Agent": SEC_UA}, timeout=30)
        r.raise_for_status()
        _cik_map = {norm(v["ticker"]): str(v["cik_str"]).zfill(10) for v in r.json().values()}
        _cik_loaded = time.time()
    return _cik_map.get(sym)


def check_filings():
    for sym in WATCHLIST:
        try:
            cik = cik_for(sym)
            if not cik:
                log.warning("No CIK found for %s (ETF/foreign?)", sym)
                continue
            r = http.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                         headers={"User-Agent": SEC_UA}, timeout=20)
            r.raise_for_status()
            rec = r.json()["filings"]["recent"]
            seed_key = f"seeded:filings:{sym}"
            first_run = not state.has(seed_key)
            for form, acc, fdate, doc, period in zip(
                rec["form"], rec["accessionNumber"], rec["filingDate"],
                rec["primaryDocument"], rec["reportDate"],
            ):
                if form.upper() not in FORMS:
                    continue
                key = f"filing:{sym}:{acc}"
                if state.has(key):
                    continue
                if first_run:
                    state.mark(key)
                    continue
                link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"
                if notify(f"{sym} filed {form}",
                          f"{sym} filed a {form} on {fdate}" + (f" for period ending {period}." if period else "."),
                          url=link, url_title="View filing", priority=0):
                    state.mark(key)
            state.mark(seed_key)
            time.sleep(0.2)  # SEC fair-access limit: 10 req/s
        except Exception:
            log.exception("filing check failed for %s", sym)

# ------------------------------------------------------------------- loop
running = True

def stop(*_):
    global running
    running = False

def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    jobs = {"halts": check_halts, "prices": check_prices, "news": check_news, "filings": check_filings}
    schedule = {n: 0.0 for n, on in ENABLED.items() if on}
    log.info("Watching %d tickers: %s", len(WATCHLIST), ", ".join(WATCHLIST))
    log.info("Jobs: %s | move threshold %.1f%% | forms %s | dry_run=%s",
             {n: INTERVALS[n] for n in schedule}, MOVE_PCT, sorted(FORMS), DRY_RUN)
    if not DRY_RUN:
        notify("Stock alerts started", f"Monitoring {len(WATCHLIST)} tickers.", priority=-1)
    last_prune = 0.0
    while running:
        now = time.monotonic()
        for name, due in schedule.items():
            if now >= due:
                try:
                    jobs[name]()
                except Exception:
                    log.exception("job %s failed", name)
                schedule[name] = time.monotonic() + INTERVALS[name]
        if time.time() - last_prune > 86400:
            state.prune()
            last_prune = time.time()
        try:
            with open(HEARTBEAT, "w") as f:
                f.write(str(time.time()))
        except OSError:
            pass
        time.sleep(1)
    log.info("Shutting down")


if __name__ == "__main__":
    main()
