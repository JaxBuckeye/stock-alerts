"""Is the app working? Each check's last run and result, plus one overall verdict.

Used by the Discord bot's status (green/yellow/red dot and status line), /status, the optional daily
heartbeat message, and the web page's System > Status.
"""
import time

STARTED = time.time()
_jobs = {}  # name -> {"last_run", "last_ok", "last_error", "fails"}


def record(name, ok, error=None):
    j = _jobs.setdefault(name, {"last_run": 0.0, "last_ok": 0.0, "last_error": None, "fails": 0})
    j["last_run"] = time.time()
    if ok:
        j.update(last_ok=j["last_run"], last_error=None, fails=0)
    else:
        j.update(last_error=(str(error) or type(error).__name__)[:300], fails=j["fails"] + 1)


def jobs():
    return {k: dict(v) for k, v in _jobs.items()}


def ago(ts, now=None):
    if not ts:
        return "never"
    d = max(0, int((now or time.time()) - ts))
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if d >= size:
            return f"{d // size}{unit} ago"
    return "just now" if d < 10 else f"{d}s ago"


def problems(intervals, enabled, errors=(), now=None):
    """Plain-language problems; empty means healthy."""
    now = now or time.time()
    out = [f"Setup needed: {e}" for e in errors]
    if errors:
        return out
    for name, every in intervals.items():
        if not enabled.get(name):
            continue
        j = _jobs.get(name)
        late_after = max(3 * every, every + 300)
        if j is None:
            if now - STARTED > late_after:
                out.append(f"{name} check hasn't run yet")
        elif j["fails"] >= 3:
            out.append(f"{name} check failing: {j['last_error']}")
        elif now - j["last_run"] > late_after:
            out.append(f"{name} check last ran {ago(j['last_run'], now)}")
    return out


def verdict(intervals, enabled, errors=(), now=None):
    """('ok' | 'warn' | 'error', problems)"""
    p = problems(intervals, enabled, errors, now)
    return ("error" if errors else "warn" if p else "ok"), p


def last_check(now=None):
    runs = [j["last_run"] for j in _jobs.values() if j["last_run"]]
    return max(runs) if runs else 0.0


def report():
    """Everything /status, the bot's status line, the daily heartbeat and the web page show."""
    from . import config as c
    from . import version
    from .jobs import _blocked
    from .store import state
    now = time.time()
    status, probs = verdict(c.INTERVALS, c.ENABLED, c.ERRORS, now)
    last = state.alerts(limit=1)
    return {
        "status": status, "problems": probs, "uptime": ago(STARTED, now).replace(" ago", ""),
        "version": version.short(), "tickers": len(state.tickers()), "cvrs": len(state.cvr_list()),
        "alerts_24h": state.alert_count_since(now - 86400),
        "last_alert": ago(last[0]["ts"], now) if last else "none yet",
        "last_check": ago(last_check(), now),
        "jobs": [{"name": n, "every": every, "on": bool(c.ENABLED.get(n)), "last_run": ago(_jobs.get(n, {}).get("last_run"), now),
                  "error": _jobs.get(n, {}).get("last_error")} for n, every in c.INTERVALS.items()],
        "channels": [("Discord webhook", c.DISCORD_ON), ("Discord bot", bool(c.DISCORD_BOT_TOKEN)),
                     ("Pushover", c.PUSHOVER_ON), ("SMS", c.SMS_ON)],
        "blocked": sorted(h for h, (until, _) in _blocked.items() if until > now),
    }


def status_line(r):
    """Short line for the bot's Discord status (max 128 characters)."""
    if r["status"] == "error":
        text = "🔴 Setup needed: open the web page"
    elif r["status"] == "warn":
        text = f"🟡 {r['problems'][0]}"
    else:
        text = f"🟢 Watching {r['tickers']} tickers · {r['cvrs']} CVRs · checked {r['last_check']}"
    return text[:128]
