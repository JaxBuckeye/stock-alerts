"""All configuration comes from environment variables."""
import logging
import os
import sys


def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Missing required environment variable: {name}")
    return val


def flag(name, default="true"):
    return env(name, default).strip().lower() in ("1", "true", "yes")


def csv(name, default=""):
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


def norm(sym):
    return sym.strip().upper().lstrip("$").replace("-", ".")


KINDS = {"news", "move", "halt", "filing", "insider", "stake", "earnings", "call", "site", "system"}


def event_filter(name, default):
    raw = env(name, default).strip().lower()
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

# ---- discord bot (slash commands to manage the watchlist)
DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID")
DISCORD_ROLE_ID = env("DISCORD_ALLOWED_ROLE_ID")        # optional: only this role may add/remove
DISCORD_CHANNEL_ID = env("DISCORD_COMMAND_CHANNEL_ID")  # optional: only this channel may add/remove
# Post each ticker's alerts into a channel named after it (e.g. #bolt for BOLT), if such a channel exists
DISCORD_TICKER_CHANNELS = flag("DISCORD_TICKER_CHANNELS", "true")
# true = tickers with their own channel are NOT also posted to the general webhook channel
DISCORD_TICKER_ONLY = flag("DISCORD_TICKER_ONLY", "false")
TICKER_CHANNEL_EVENTS = event_filter("TICKER_CHANNEL_EVENTS", "all")

# ---- watchlist and behavior
INITIAL_WATCHLIST = [norm(s) for s in csv("WATCHLIST")]
MAX_TICKERS = int(env("MAX_TICKERS", "50"))
MOVE_PCT = float(env("MOVE_THRESHOLD_PCT", "5"))
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
# Form 4 transaction codes to alert on (P = open-market buy, S = open-market sale, ...), or "all"
_f4 = env("FORM4_CODES", "all").strip().upper()
FORM4_CODES = None if _f4 in ("", "ALL") else {x.strip() for x in _f4.split(",") if x.strip()}
NEWS_MAX_AGE_H = float(env("NEWS_MAX_AGE_HOURS", "6"))
NEWS_MAX_PER_CYCLE = int(env("NEWS_MAX_PER_CYCLE", "3"))
SITE_MAX_PER_CYCLE = int(env("SITE_MAX_PER_CYCLE", "3"))
EARNINGS_REMINDERS = sorted({int(x) for x in __import__("re").findall(r"\d+", env("EARNINGS_REMINDERS", "1d,0d"))}, reverse=True)
EARNINGS_REMIND_HOUR_ET = int(env("EARNINGS_REMIND_HOUR_ET", "6"))
DRY_RUN = flag("DRY_RUN", "false")

INTERVALS = {
    "halts": int(env("HALT_INTERVAL", "30")),
    "prices": int(env("PRICE_INTERVAL", "60")),
    "news": int(env("NEWS_INTERVAL", "300")),
    "filings": int(env("FILING_INTERVAL", "300")),
    "earnings": int(env("EARNINGS_INTERVAL", "1800")),
    "sites": int(env("SITE_INTERVAL", "900")),
}
ENABLED = {k: flag(f"ENABLE_{k.upper()}", "true") for k in INTERVALS}

DATA_DIR = env("DATA_DIR", "/data")
HEARTBEAT = os.path.join(DATA_DIR, "heartbeat")

logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")

if not (PUSHOVER_ON or DISCORD_ON or SMS_ON):
    sys.exit("No notification channel configured. Set Pushover, Discord webhook, and/or Twilio variables.")
if not INITIAL_WATCHLIST and not DISCORD_BOT_TOKEN:
    sys.exit("Set WATCHLIST, or set DISCORD_BOT_TOKEN so tickers can be added from Discord.")
