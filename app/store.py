"""SQLite state: dedupe keys, the watchlist, and monitored company websites."""
import json
import os
import sqlite3
import threading
import time

from .config import DATA_DIR


class State:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=15)  # web page also writes this file
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript("""
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, ts INTEGER);
CREATE TABLE IF NOT EXISTS watchlist (sym TEXT PRIMARY KEY, name TEXT, added_by TEXT, added_ts INTEGER);
CREATE TABLE IF NOT EXISTS sites (sym TEXT PRIMARY KEY, homepage TEXT, news_url TEXT,
                                  feed_url TEXT, manual INTEGER DEFAULT 0, checked_ts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS cvrs (sym TEXT PRIMARY KEY, data TEXT, added_by TEXT, added_ts INTEGER);
""")
            self.db.commit()

    def _run(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # --- dedupe
    def has(self, key):
        with self.lock:
            return self.db.execute("SELECT 1 FROM seen WHERE key=?", (key,)).fetchone() is not None

    def mark(self, key):
        self._run("INSERT OR IGNORE INTO seen VALUES (?,?)", (key, int(time.time())))

    def prune(self, days=30):
        # SEC filing lists and company sites keep old items listed for years, so their keys must never be
        # pruned or those items would alert again as "new". Everything else is dated or age-filtered.
        self._run("DELETE FROM seen WHERE ts < ? AND key NOT LIKE 'seeded:%' AND key NOT LIKE 'filing:%' "
                  "AND key NOT LIKE 'cvrfile:%' AND key NOT LIKE 'site:%'", (int(time.time()) - days * 86400,))

    # --- watchlist
    def tickers(self):
        with self.lock:
            return [r["sym"] for r in self.db.execute("SELECT sym FROM watchlist ORDER BY sym")]

    def watch_rows(self):
        with self.lock:
            return [(r["sym"], r["name"]) for r in self.db.execute("SELECT sym, name FROM watchlist ORDER BY sym")]

    def get_name(self, sym):
        with self.lock:
            r = self.db.execute("SELECT name FROM watchlist WHERE sym=?", (sym,)).fetchone()
            return r["name"] if r else None

    def add_ticker(self, sym, name=None, who="env"):
        cur = self._run("INSERT OR IGNORE INTO watchlist VALUES (?,?,?,?)", (sym, name, who, int(time.time())))
        return cur.rowcount > 0

    def set_name(self, sym, name):
        self._run("UPDATE watchlist SET name=? WHERE sym=?", (name, sym))

    def remove_ticker(self, sym):
        cur = self._run("DELETE FROM watchlist WHERE sym=?", (sym,))
        self._run("DELETE FROM sites WHERE sym=?", (sym,))
        return cur.rowcount > 0

    # --- sites
    def get_site(self, sym):
        with self.lock:
            r = self.db.execute("SELECT * FROM sites WHERE sym=?", (sym,)).fetchone()
            return dict(r) if r else None

    def upsert_site(self, sym, **fields):
        row = self.get_site(sym) or {"sym": sym, "homepage": None, "news_url": None,
                                     "feed_url": None, "manual": 0, "checked_ts": 0}
        row.update(fields)
        self._run("INSERT OR REPLACE INTO sites VALUES (:sym,:homepage,:news_url,:feed_url,:manual,:checked_ts)", row)

    # --- CVRs (data is a JSON dict built by app.cvr.discover)
    def cvr_list(self):
        with self.lock:
            rows = self.db.execute("SELECT sym, data, added_by, added_ts FROM cvrs ORDER BY sym").fetchall()
        return [dict(json.loads(r["data"]), sym=r["sym"], added_by=r["added_by"], added_ts=r["added_ts"]) for r in rows]

    def cvr_get(self, sym):
        with self.lock:
            r = self.db.execute("SELECT data, added_by, added_ts FROM cvrs WHERE sym=?", (sym,)).fetchone()
        return dict(json.loads(r["data"]), sym=sym, added_by=r["added_by"], added_ts=r["added_ts"]) if r else None

    def cvr_put(self, sym, data, who=None):
        old = self.cvr_get(sym)
        data = {k: v for k, v in data.items() if k not in ("sym", "added_by", "added_ts")}
        self._run("INSERT OR REPLACE INTO cvrs VALUES (?,?,?,?)",
                  (sym, json.dumps(data), (old or {}).get("added_by") or who, (old or {}).get("added_ts") or int(time.time())))

    def cvr_remove(self, sym):
        return self._run("DELETE FROM cvrs WHERE sym=?", (sym,)).rowcount > 0


state = State(os.path.join(DATA_DIR, "state.db"))
