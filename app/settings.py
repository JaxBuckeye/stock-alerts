"""Every setting in one schema. A value saved on the web page wins over the environment (.env), which wins
over the default. DATA_DIR and WEB_PORT are read from the environment only, since they are needed to start."""
import logging
import os
import sqlite3
import sys

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "state.db")
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

EVENTS = "news, move, halt, filing, insider, stake, cvr, earnings, call, site, system, or all"

# key, group, type, default, help.  Types: str, secret, bool, int, float, or "choice:A,B,C"
SCHEMA = [
    ("FINNHUB_API_KEY", "Required", "secret", "", "Free API key from finnhub.io."),
    ("SEC_USER_AGENT", "Required", "str", "", "Your name and email, e.g. 'Jane Doe jane@example.com'. The SEC requires a contact."),

    ("WATCHLIST", "Watchlist", "str", "", "Comma-separated tickers. With the Discord bot on, this only seeds the first start; "
                                           "after that use /watch in Discord."),
    ("MAX_TICKERS", "Watchlist", "int", "50", "Most tickers the watchlist can hold."),

    ("DISCORD_BOT_TOKEN", "Discord bot", "secret", "", "From discord.com/developers/applications > your app > Bot > Reset Token."),
    ("DISCORD_GUILD_ID", "Discord bot", "str", "", "Your server ID. Makes slash commands appear instantly."),
    ("DISCORD_ALLOWED_ROLE_ID", "Discord bot", "str", "", "Optional: only members with this role ID may add/remove."),
    ("DISCORD_COMMAND_CHANNEL_ID", "Discord bot", "str", "", "Optional: only allow add/remove in this channel ID."),
    ("DISCORD_TICKER_CHANNELS", "Discord bot", "bool", "true", "Also post a ticker's alerts to a channel named after it (#bolt for BOLT)."),
    ("DISCORD_TICKER_ONLY", "Discord bot", "bool", "false", "Tickers with their own channel are NOT also posted to the webhook channel."),
    ("TICKER_CHANNEL_EVENTS", "Discord bot", "str", "all", f"Alert kinds for ticker channels: {EVENTS}."),

    ("DISCORD_WEBHOOK_URL", "Discord webhook", "secret", "", "Channel > Edit > Integrations > Webhooks > Copy URL."),
    ("DISCORD_MENTION", "Discord webhook", "str", "", "Optional ping on urgent alerts, e.g. @here or <@YOUR_USER_ID>."),
    ("DISCORD_EVENTS", "Discord webhook", "str", "all", f"Alert kinds: {EVENTS}."),

    ("PUSHOVER_APP_TOKEN", "Pushover", "secret", "", "Set both Pushover values to send push alerts."),
    ("PUSHOVER_USER_KEY", "Pushover", "secret", "", ""),
    ("PUSHOVER_EVENTS", "Pushover", "str", "all", f"Alert kinds: {EVENTS}."),

    ("TWILIO_ACCOUNT_SID", "SMS (Twilio)", "str", "", ""),
    ("TWILIO_AUTH_TOKEN", "SMS (Twilio)", "secret", "", ""),
    ("TWILIO_FROM_NUMBER", "SMS (Twilio)", "str", "", "Use this or the messaging service SID."),
    ("TWILIO_MESSAGING_SERVICE_SID", "SMS (Twilio)", "str", "", ""),
    ("TWILIO_TO_NUMBERS", "SMS (Twilio)", "str", "", "Recipients in +15551234567 format, comma-separated."),
    ("SMS_EVENTS", "SMS (Twilio)", "str", "halt,move,filing,earnings,call", f"Alert kinds: {EVENTS}."),

    ("SEC_FORMS", "SEC filings", "str", "10-K,10-K/A,10-Q,10-Q/A,8-K,8-K/A", "Regular filings to alert on."),
    ("TRACK_FORM4", "SEC filings", "bool", "true", "Form 4 insider trades."),
    ("FORM4_CODES", "SEC filings", "str", "all", "Form 4 transaction codes, or all. P = open-market buy, S = sale, "
                                                  "A = grant, M = option exercise, F = tax withholding, G = gift."),
    ("TRACK_13D", "SEC filings", "bool", "true", "Schedule 13D stakes (5%+, intent to influence)."),
    ("TRACK_13G", "SEC filings", "bool", "false", "Schedule 13G stakes (passive 5%+ holders). Noisy."),

    ("ENABLE_CVR", "CVRs", "bool", "true", "Track contingent value rights added with /cvr add or on the CVRs page."),
    ("CVR_INTERVAL", "CVRs", "int", "1800", "Seconds between CVR checks."),
    ("CVR_NEWS", "CVRs", "bool", "true", "Search Google News for each CVR asset."),
    ("CVR_SEC_SEARCH", "CVRs", "bool", "true", "Search every company's SEC filings for each CVR asset (catches buyers and licensees)."),
    ("CVR_NEWS_MAX_AGE_HOURS", "CVRs", "float", "72", "Ignore CVR news older than this."),

    ("MOVE_THRESHOLD_PCT", "Alerts", "float", "5", "Price move (%) vs previous close that triggers an alert."),
    ("NEWS_MAX_AGE_HOURS", "Alerts", "float", "6", "Ignore company news older than this."),
    ("NEWS_MAX_PER_CYCLE", "Alerts", "int", "3", "Most headlines per ticker per check; the rest are summarized."),
    ("SITE_MAX_PER_CYCLE", "Alerts", "int", "3", "Most website releases per ticker per check."),
    ("PRESS_WIRE_NEWS", "Alerts", "bool", "true", "Also search GlobeNewswire, Business Wire, PR Newswire and others "
                                                  "(via Google News) for each ticker's press releases. Catches "
                                                  "companies whose website blocks the app."),
    ("EARNINGS_REMINDERS", "Alerts", "str", "1d,0d", "Days before earnings to remind. 1d,0d = day before and day of."),
    ("EARNINGS_REMIND_HOUR_ET", "Alerts", "int", "6", "Hour (Eastern) to send earnings reminders."),
    ("DRY_RUN", "Alerts", "bool", "false", "Log alerts instead of sending them."),
    ("HEARTBEAT_HOUR_ET", "Alerts", "int", "", "Optional: hour (0-23, Eastern) to post a daily \"still running\" "
                                               "message. Blank = off; the Discord bot's status already shows health live."),

    ("ENABLE_PRICES", "Jobs", "bool", "true", ""),
    ("PRICE_INTERVAL", "Jobs", "int", "60", "Seconds."),
    ("ENABLE_NEWS", "Jobs", "bool", "true", ""),
    ("NEWS_INTERVAL", "Jobs", "int", "300", "Seconds."),
    ("ENABLE_HALTS", "Jobs", "bool", "true", ""),
    ("HALT_INTERVAL", "Jobs", "int", "30", "Seconds."),
    ("ENABLE_FILINGS", "Jobs", "bool", "true", ""),
    ("FILING_INTERVAL", "Jobs", "int", "300", "Seconds."),
    ("ENABLE_EARNINGS", "Jobs", "bool", "true", ""),
    ("EARNINGS_INTERVAL", "Jobs", "int", "1800", "Seconds."),
    ("ENABLE_SITES", "Jobs", "bool", "true", ""),
    ("SITE_INTERVAL", "Jobs", "int", "900", "Seconds."),

    ("LOG_LEVEL", "Advanced", "choice:DEBUG,INFO,WARNING,ERROR", "INFO", ""),
]
SPEC = {k: {"key": k, "group": g, "type": t, "default": d, "help": h} for k, g, t, d, h in SCHEMA}
TRUE = ("1", "true", "yes", "on")


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.executescript("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);"
                     "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);")
    return db


def stored():
    db = connect()
    try:
        return dict(db.execute("SELECT key, value FROM settings"))
    finally:
        db.close()


def source(key, saved=None):
    saved = stored() if saved is None else saved
    if key in saved:
        return "web"
    return "env" if os.environ.get(key) is not None else "default"


def get(key, saved=None):
    saved = stored() if saved is None else saved
    if key in saved:
        return saved[key]
    val = os.environ.get(key)
    return val if val is not None else SPEC[key]["default"]


def validate(key, value):
    """Error message for a bad value, or None."""
    t = SPEC[key]["type"]
    v = (value or "").strip()
    try:
        if t == "int" and v:
            int(v)
        elif t == "float" and v:
            float(v)
    except ValueError:
        return f"{key} must be a {'whole number' if t == 'int' else 'number'}"
    if t.startswith("choice:") and v and v not in t[7:].split(","):
        return f"{key} must be one of {t[7:]}"
    return None


def save(updates, reset=()):
    """updates: {key: value} stored as web overrides; reset: keys to drop back to .env/default."""
    db = connect()
    try:
        with db:
            for k, v in updates.items():
                db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (k, v))
            for k in reset:
                db.execute("DELETE FROM settings WHERE key=?", (k,))
    finally:
        db.close()


def meta_get(key, default=None):
    db = connect()
    try:
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
    finally:
        db.close()


def meta_set(key, value):
    db = connect()
    try:
        with db:
            if value is None:
                db.execute("DELETE FROM meta WHERE key=?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
    finally:
        db.close()


def restart():
    """Re-run the app in the same process (same container PID), so new settings take effect."""
    logging.getLogger("settings").warning("Restarting to apply new settings")
    logging.shutdown()
    os.execv(sys.executable, [sys.executable, "-m", "app.main"])
