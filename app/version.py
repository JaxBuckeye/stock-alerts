"""Which build is running, its changelog, and what's newer on GitHub (for System > Updates)."""
import os
import pathlib
import time

VERSION = os.environ.get("APP_VERSION", "dev")
BUILD_DATE = os.environ.get("BUILD_DATE", "")
REPO = os.environ.get("GITHUB_REPO", "JaxBuckeye/stock-alerts")
STARTED = time.time()
_cache = {"ts": 0.0, "commits": None, "error": None}


def short():
    return VERSION[:7] if VERSION != "dev" else "dev"


def changelog():
    """[(sha, date, subject)] written into the image at build time (newest first)."""
    path = pathlib.Path(__file__).with_name("CHANGELOG.txt")
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            out.append(tuple(p.strip() for p in parts))
    return out


def latest(force=False):
    """(commits, error): the newest commits on GitHub's main branch, cached for 30 minutes."""
    if not force and _cache["commits"] is not None and time.time() - _cache["ts"] < 1800:
        return _cache["commits"], _cache["error"]
    from .clients import http
    try:
        r = http.get(f"https://api.github.com/repos/{REPO}/commits", params={"per_page": 20},
                     headers={"Accept": "application/vnd.github+json", "User-Agent": "stock-alerts"}, timeout=10)
        r.raise_for_status()
        commits = [{"sha": x["sha"], "date": x["commit"]["author"]["date"][:10],
                    "msg": x["commit"]["message"].splitlines()[0]} for x in r.json()]
        _cache.update(ts=time.time(), commits=commits, error=None)
    except Exception as e:
        _cache.update(ts=time.time(), commits=_cache["commits"] or [], error=str(e))
    return _cache["commits"], _cache["error"]


def updates(force=False):
    """(commits marked new/installed, number of newer commits, error)."""
    commits, err = latest(force)
    rows, newer, seen_current = [], 0, False
    for cm in commits:
        installed = VERSION != "dev" and cm["sha"].startswith(VERSION[:7])
        seen_current = seen_current or installed
        is_new = not seen_current and VERSION != "dev"
        newer += is_new
        rows.append(dict(cm, short=cm["sha"][:7], installed=installed, new=is_new))
    return rows, newer, err
