import logging
import threading
import time

import requests

from .config import FINNHUB_KEY

log = logging.getLogger("clients")
http = requests.Session()


class Finnhub:
    base = "https://finnhub.io/api/v1"
    min_gap = 1.05  # free tier: 60 calls/min; shared by the scheduler and the Discord bot thread

    def __init__(self, key):
        self.key, self.last, self.lock = key, 0.0, threading.Lock()

    def get(self, path, **params):
        with self.lock:
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
