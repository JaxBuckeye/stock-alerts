"""SQLite state: dedupe keys, the watchlist, and monitored company websites."""
import os
import sqlite3
import threading
import time

from .config import DATA_DIR


class State:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript("""
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, ts INTEGER);
CREATE TABLE IF NOT EXISTS watchlist (sym TEXT PRIMARY KEY, name TEXT, added_by TEXT, added_ts INTEGER);
CREATE TABLE IF NOT EXISTS sites (sym TEXT PRIMARY KEY, homepage TEXT, news_url TEXT,
                                  feed_url TEXT, manual INTEGER DEFAULT 0, checked_ts INTEGER DEFAULT 0);
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
        self._run("DELETE FROM seen WHERE ts < ? AND key NOT LIKE 'seeded:%'", (int(time.time()) - days * 86400,))

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


state = State(os.path.join(DATA_DIR, "state.db"))
