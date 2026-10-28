import logging
import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config as c
from . import cvr
from . import health
from . import jobs
from . import web
from .notify import notify
from .store import state

log = logging.getLogger("main")
running = True


def stop(*_):
    global running
    running = False


def init_watchlist():
    if not c.DISCORD_BOT_TOKEN:
        # No Discord control: the WATCHLIST setting is the source of truth on every start.
        wanted = set(c.INITIAL_WATCHLIST)
        for sym in set(state.tickers()) - wanted:
            state.remove_ticker(sym)
        for sym in wanted:
            state.add_ticker(sym, None, "env")
    elif not state.has("seeded:watchlist"):
        # With the Discord bot: WATCHLIST only seeds the very first start; after that Discord is in charge.
        for sym in c.INITIAL_WATCHLIST:
            state.add_ticker(sym, None, "env")
        state.mark("seeded:watchlist")


def heartbeat():
    try:
        with open(c.HEARTBEAT, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def daily_heartbeat(now=None):
    """Optional once-a-day "still running" message at HEARTBEAT_HOUR_ET (off when not set)."""
    if c.HEARTBEAT_HOUR is None:
        return False
    now = now or datetime.now(ZoneInfo("America/New_York"))
    key = f"heartbeat:{now.date()}"
    if now.hour < c.HEARTBEAT_HOUR or state.has(key):
        return False
    r = health.report()
    ok = r["status"] == "ok"
    lines = [f"Up {r['uptime']} · build {r['version']}",
             f"Watching {r['tickers']} tickers and {r['cvrs']} CVRs · {r['alerts_24h']} alerts in the last 24h",
             "All checks on schedule." if ok else "Needs attention: " + "; ".join(r["problems"][:4])]
    if notify("💚 Stock alerts is running" if ok else "⚠️ Stock alerts needs attention", "\n".join(lines),
              kind="system", priority=0 if ok else 1):
        state.mark(key)
    return True


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    web.start()
    for w in c.WARNINGS:
        log.warning(w)
    if c.ERRORS:
        for e in c.ERRORS:
            log.error("Setup needed: %s", e)
        log.error("Alerts are paused until this is fixed on the web page (port %d) or in .env", c.WEB_PORT)
        if c.DISCORD_BOT_TOKEN:  # so Discord shows the bot as "setup needed" instead of just offline
            try:
                from . import bot
                bot.start()
            except Exception:
                log.exception("Discord bot couldn't start")
        while running:
            heartbeat()
            time.sleep(5)
        return
    init_watchlist()
    table = {"halts": jobs.check_halts, "prices": jobs.check_prices, "news": jobs.check_news,
             "filings": jobs.check_filings, "earnings": jobs.check_earnings, "sites": jobs.check_sites,
             "cvr": cvr.check_cvrs}
    schedule = {n: 0.0 for n, on in c.ENABLED.items() if on}
    tickers = state.tickers()
    log.info("Watching %d tickers: %s", len(tickers), ", ".join(tickers) or "(none yet)")
    log.info("Tracking %d CVRs: %s", len(state.cvr_list()), ", ".join(x["sym"] for x in state.cvr_list()) or "(none)")
    log.info("Jobs: %s | move %.1f%% | forms %s | dry_run=%s", {n: c.INTERVALS[n] for n in schedule},
             c.MOVE_PCT, sorted(c.FORMS), c.DRY_RUN)
    log.info("Channels: pushover=%s discord=%s sms=%s (%d recipients) | discord bot=%s",
             c.PUSHOVER_ON, c.DISCORD_ON, c.SMS_ON, len(c.TWILIO_TO), bool(c.DISCORD_BOT_TOKEN))
    if c.DISCORD_BOT_TOKEN:
        from . import bot  # imported lazily so discord.py is only needed when the bot is enabled
        bot.start()
    # Restarts show in the web page's Activity feed only; Discord gets the bot's live status instead.
    state.alert_add("system", None, "Stock alerts started",
                    f"Monitoring {len(tickers)} tickers: {', '.join(tickers)[:800] or 'none yet'}", None, -1,
                    ["not sent (restart)"])
    last_prune = 0.0
    while running:
        now = time.monotonic()
        for name, due in schedule.items():
            if now >= due:
                try:
                    table[name]()
                    health.record(name, True)
                except Exception as e:
                    log.exception("job %s failed", name)
                    health.record(name, False, e)
                schedule[name] = time.monotonic() + c.INTERVALS[name]
        if time.time() - last_prune > 86400:
            state.prune()
            last_prune = time.time()
        try:
            daily_heartbeat()
        except Exception:
            log.exception("daily heartbeat failed")
        heartbeat()
        time.sleep(1)
    log.info("Shutting down")


if __name__ == "__main__":
    main()
