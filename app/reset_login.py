"""Forgot the web password? docker exec stock-alerts python -m app.reset_login

Removes the web login and prints a new setup code; open the web page to create a new login.
Settings, the watchlist and CVRs are kept.
"""
from . import settings as s
from .web import setup_code

s.meta_set("web_user", None)
s.meta_set("web_pw_hash", None)
s.meta_set("web_setup_code", None)
print(f"Web login removed. Open http://<this-server>:{s.WEB_PORT} and enter setup code {setup_code()}")
