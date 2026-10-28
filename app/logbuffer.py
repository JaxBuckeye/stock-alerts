"""Keeps the most recent log lines in memory for the web page's System > Logs."""
import collections
import logging

_buf = collections.deque(maxlen=1000)


class _Ring(logging.Handler):
    def emit(self, record):
        try:
            _buf.append({"ts": record.created, "level": record.levelname, "name": record.name,
                         "msg": self.format(record)})
        except Exception:  # never let logging break the app
            pass


def install(level=logging.INFO):
    root = logging.getLogger()
    if not any(isinstance(h, _Ring) for h in root.handlers):
        h = _Ring(level)
        h.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(h)


def entries(min_level="INFO"):
    floor = logging.getLevelName(min_level) if isinstance(logging.getLevelName(min_level), int) else 0
    return [e for e in reversed(_buf) if logging.getLevelName(e["level"]) >= floor]
