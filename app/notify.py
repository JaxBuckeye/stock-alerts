"""Fan-out to Pushover, Discord (webhook), and SMS (Twilio)."""
import logging
import time
from datetime import datetime, timezone

import requests

from . import config as c
from .clients import http

log = logging.getLogger("notify")
ticker_poster = None  # installed by app.bot.start(): fn(sym, title, message, url, kind, priority) -> True/False/None
COLORS = {"halt": 0xE74C3C, "move": 0xF39C12, "news": 0x3498DB, "filing": 0x9B59B6,
          "insider": 0xE67E22, "stake": 0x8E44AD, "cvr": 0x16A085,
          "earnings": 0x2ECC71, "call": 0xF1C40F, "site": 0x1ABC9C, "system": 0x95A5A6}


def _post(name, url, ok_codes=(200, 201, 204), **kw):
    for attempt in range(3):
        try:
            r = http.post(url, timeout=15, **kw)
            if r.status_code in ok_codes:
                return True
            if r.status_code == 429:
                try:
                    wait = float(r.json().get("retry_after", 2))
                except Exception:
                    wait = 2
                log.warning("%s rate limited; waiting %.1fs", name, wait)
                time.sleep(min(wait, 10))
                continue
            if 400 <= r.status_code < 500:
                log.error("%s rejected message: %s %s", name, r.status_code, r.text[:300])
                return False
            log.warning("%s returned %s, retrying", name, r.status_code)
        except requests.RequestException as e:
            log.warning("%s error: %s", name, e)
        time.sleep(2 ** attempt)
    return False


def _pushover(title, message, url, url_title, priority, sound):
    payload = {"token": c.PUSHOVER_TOKEN, "user": c.PUSHOVER_USER,
               "title": title[:250], "message": message[:1024], "priority": priority}
    if url:
        payload["url"], payload["url_title"] = url[:512], (url_title or "Open")[:100]
    if sound:
        payload["sound"] = sound
    return _post("Pushover", "https://api.pushover.net/1/messages.json", data=payload)


def _discord(title, message, url, kind, priority):
    embed = {"title": title[:256], "description": message[:4000], "color": COLORS.get(kind, 0x95A5A6),
             "timestamp": datetime.now(timezone.utc).isoformat()}
    if url and url.startswith(("http://", "https://")):
        embed["url"] = url
    payload = {"username": "Stock Alerts", "embeds": [embed]}
    if c.DISCORD_MENTION and priority >= 1:
        payload["content"] = c.DISCORD_MENTION
    return _post("Discord", c.DISCORD_URL, json=payload)


def _sms(title, message, url):
    body = f"{title}\n{message}" + (f"\n{url}" if url else "")
    sent = []
    for to in c.TWILIO_TO:
        data = {"To": to, "Body": body[:1500]}
        if c.TWILIO_MSG_SID:
            data["MessagingServiceSid"] = c.TWILIO_MSG_SID
        else:
            data["From"] = c.TWILIO_FROM
        sent.append(_post("Twilio SMS", f"https://api.twilio.com/2010-04-01/Accounts/{c.TWILIO_SID}/Messages.json",
                          auth=(c.TWILIO_SID, c.TWILIO_TOKEN), data=data))
    return any(sent)


def notify(title, message, url=None, url_title=None, priority=0, sound=None, kind="news", sym=None):
    """True if at least one channel delivered (or no channel wants this kind of event)."""
    if c.DRY_RUN:
        log.info("[DRY RUN] (%s) %s | %s | %s", kind, title, message, url)
        return True
    results = []
    if c.PUSHOVER_ON and kind in c.PUSHOVER_EVENTS:
        results.append(_pushover(title, message, url, url_title, priority, sound))
    routed = False
    if sym and ticker_poster and kind in c.TICKER_CHANNEL_EVENTS:
        r = ticker_poster(sym, title, message, url, kind, priority)  # None = no channel for this ticker
        if r is not None:
            results.append(r)
            routed = r
    if c.DISCORD_ON and kind in c.DISCORD_EVENTS and not (routed and c.DISCORD_TICKER_ONLY):
        results.append(_discord(title, message, url, kind, priority))
    if c.SMS_ON and kind in c.SMS_EVENTS:
        results.append(_sms(title, message, url))
    return any(results) if results else True
