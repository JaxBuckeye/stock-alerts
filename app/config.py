"""Effective configuration, read once at startup from app.settings (web page > .env > default).

Problems are collected in ERRORS instead of exiting, so the web page can still start and fix them.
"""
import logging
import os
import re

from . import settings as s

ERRORS = []      # blocking problems: alerts don't run until these are fixed
WARNINGS = []
_saved = s.stored()


def env(name, default=None, required=False):
    """Current value of a setting ("" counts as unset for required ones)."""
    val = s.get(name, _saved) if name in s.SPEC else os.environ.get(name, default)
    if val is None:
        val = default
    if required and not (val or "").strip():
        ERRORS.append(f"{name} is required")
    return val


def flag(name, default="true"):
    return (env(name, default) or "").strip().lower() in s.TRUE


def csv(name, default=""):
    return [x.strip() for x in (env(name, default) or "").split(",") if x.strip()]


def number(name, cast):
    raw = (env(name) or "").strip() or s.SPEC[name]["default"]
    try:
        return cast(raw)
    except ValueError:
        ERRORS.append(f"{name} must be a number (got {raw!r})")
        return cast(s.SPEC[name]["default"])


def norm(sym):
    return sym.strip().upper().lstrip("$").replace("-", ".")


KINDS = {"news", "move", "halt", "filing", "insider", "stake", "cvr", "earnings", "call", "site", "system"}


def event_filter(name, default):
    raw = (env(name, default) or "").strip().lower()
    return set(KINDS) if raw == "all" else {e.strip() for e in raw.split(",") if e.strip()}


# ---- required data sources
FINNHUB_KEY = env("FINNHUB_API_KEY", required=True)
SEC_UA = env("SEC_USER_AGENT", required=True)  # "Name email@example.com"
SITE_UA = f"Mozilla/5.0 (compatible; StockAlertsBot/1.0; +{SEC_UA})"

# ---- notification channels
PUSHOVER_TOKEN = env("PUSHOVER_APP_TOKEN")
PUSHOVER_USER = env("PUSHOVER_USER_KEY")
DISCORD_URL = env("DISCORD_WEBHOOK_URL")
DISCORD_MENTION = env("DISCORD_MENTION", "")
TWILIO_SID = env("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = env("TWILIO_AUTH_TOKEN")
TWILIO_FROM = env("TWILIO_FROM_NUMBER")
TWILIO_MSG_SID = env("TWILIO_MESSAGING_SERVICE_SID")
TWILIO_TO = csv("TWILIO_TO_NUMBERS")

PUSHOVER_ON = bool(PUSHOVER_TOKEN and PUSHOVER_USER)
DISCORD_ON = bool(DISCORD_URL)
SMS_ON = bool(TWILIO_SID and TWILIO_TOKEN and (TWILIO_FROM or TWILIO_MSG_SID) and TWILIO_TO)

PUSHOVER_EVENTS = event_filter("PUSHOVER_EVENTS", "all")
DISCORD_EVENTS = event_filter("DISCORD_EVENTS", "all")
SMS_EVENTS = event_filter("SMS_EVENTS", "halt,move,filing,earnings,call")

# ---- discord bot (slash commands to manage the watchlist and CVRs)
DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID")
DISCORD_ROLE_ID = env("DISCORD_ALLOWED_ROLE_ID")        # optional: only this role may add/remove
DISCORD_CHANNEL_ID = env("DISCORD_COMMAND_CHANNEL_ID")  # optional: only this channel may add/remove
DISCORD_TICKER_CHANNELS = flag("DISCORD_TICKER_CHANNELS", "true")
DISCORD_TICKER_ONLY = flag("DISCORD_TICKER_ONLY", "false")
TICKER_CHANNEL_EVENTS = event_filter("TICKER_CHANNEL_EVENTS", "all")

# ---- watchlist and behavior
INITIAL_WATCHLIST = [norm(x) for x in csv("WATCHLIST")]
MAX_TICKERS = number("MAX_TICKERS", int)
MOVE_PCT = number("MOVE_THRESHOLD_PCT", float)
FORMS = {f.upper() for f in csv("SEC_FORMS", "10-K,10-K/A,10-Q,10-Q/A,8-K,8-K/A")}
# Ownership filings, tracked separately from SEC_FORMS. EDGAR renamed "SC 13D" to "SCHEDULE 13D" in Dec 2024.
FORMS_13D = {"SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A"}
FORMS_13G = {"SC 13G", "SC 13G/A", "SCHEDULE 13G", "SCHEDULE 13G/A"}
FORMS_4 = {"4", "4/A"}
TRACK_13D = flag("TRACK_13D", "true")
TRACK_13G = flag("TRACK_13G", "false")
TRACK_FORM4 = flag("TRACK_FORM4", "true")
OWNERSHIP_FORMS = (FORMS_13D if TRACK_13D else set()) | (FORMS_13G if TRACK_13G else set()) | \
                  (FORMS_4 if TRACK_FORM4 else set())
_f4 = (env("FORM4_CODES", "all") or "").strip().upper()
FORM4_CODES = None if _f4 in ("", "ALL") else {x.strip() for x in _f4.split(",") if x.strip()}
NEWS_MAX_AGE_H = number("NEWS_MAX_AGE_HOURS", float)
NEWS_MAX_PER_CYCLE = number("NEWS_MAX_PER_CYCLE", int)
SITE_MAX_PER_CYCLE = number("SITE_MAX_PER_CYCLE", int)
PRESS_WIRE_NEWS = flag("PRESS_WIRE_NEWS", "true")
EARNINGS_REMINDERS = sorted({int(x) for x in re.findall(r"\d+", env("EARNINGS_REMINDERS", "1d,0d") or "")}, reverse=True)
EARNINGS_REMIND_HOUR_ET = number("EARNINGS_REMIND_HOUR_ET", int)
DRY_RUN = flag("DRY_RUN", "false")
_hb = (env("HEARTBEAT_HOUR_ET", "") or "").strip()
HEARTBEAT_HOUR = int(_hb) if _hb.isdigit() and 0 <= int(_hb) <= 23 else None
if _hb and HEARTBEAT_HOUR is None:
    WARNINGS.append(f"HEARTBEAT_HOUR_ET must be 0-23 (got {_hb!r}); the daily heartbeat is off.")

# ---- CVRs
CVR_NEWS = flag("CVR_NEWS", "true")
CVR_SEC_SEARCH = flag("CVR_SEC_SEARCH", "true")
CVR_NEWS_MAX_AGE_H = number("CVR_NEWS_MAX_AGE_HOURS", float)

INTERVALS = {
    "halts": number("HALT_INTERVAL", int),
    "prices": number("PRICE_INTERVAL", int),
    "news": number("NEWS_INTERVAL", int),
    "filings": number("FILING_INTERVAL", int),
    "earnings": number("EARNINGS_INTERVAL", int),
    "sites": number("SITE_INTERVAL", int),
    "cvr": number("CVR_INTERVAL", int),
}
ENABLED = {k: flag(f"ENABLE_{k.upper()}", "true") for k in INTERVALS}

DATA_DIR = s.DATA_DIR
HEARTBEAT = os.path.join(DATA_DIR, "heartbeat")
WEB_PORT = s.WEB_PORT

_level = (env("LOG_LEVEL", "INFO") or "INFO").strip().upper()
logging.basicConfig(level=_level if _level in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO",
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
from . import logbuffer  # noqa: E402  (recent log lines for the web page)
logbuffer.install()

if not (PUSHOVER_ON or DISCORD_ON or SMS_ON):
    ERRORS.append("No alert channel set up. Set a Discord webhook, Pushover, and/or Twilio.")
if not INITIAL_WATCHLIST and not DISCORD_BOT_TOKEN:
    WARNINGS.append("No WATCHLIST and no Discord bot: only CVRs added on the web page will be tracked.")
