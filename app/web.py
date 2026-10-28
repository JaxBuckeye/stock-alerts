"""Web page: first-run account setup, login, every setting, and the CVR list.

The first visit asks for a one-time setup code printed in the container logs, so nobody else on the
network can claim the admin account first. Saving settings restarts the app so they take effect.
"""
import hmac
import logging
import os
import secrets
import threading
import time
from datetime import timedelta

from flask import Flask, flash, redirect, render_template, request, session, url_for
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

from . import config as c
from . import settings as s
from .store import state
from .web_templates import TEMPLATES

log = logging.getLogger("web")
MAX_FAILS, LOCK_SECONDS = 5, 300
_fails = {}  # ip -> [failures, locked_until]


def setup_code():
    code = s.meta_get("web_setup_code")
    if not code:
        code = secrets.token_hex(4).upper()
        s.meta_set("web_setup_code", code)
    return code


def has_user():
    return bool(s.meta_get("web_user") and s.meta_get("web_pw_hash"))


def create_app(restart=None):
    app = Flask(__name__)
    key = s.meta_get("web_secret")
    if not key:
        key = secrets.token_hex(32)
        s.meta_set("web_secret", key)
    app.config.update(SECRET_KEY=key, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=timedelta(days=7), RESTART=restart or s.restart)
    app.jinja_loader = DictLoader(TEMPLATES)

    def schedule_restart():
        threading.Timer(1.5, app.config["RESTART"]).start()

    @app.before_request
    def guard():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        if request.method == "POST" and not hmac.compare_digest(request.form.get("csrf", ""), session["csrf"]):
            return "Form expired. Go back, reload the page and try again.", 400
        if request.endpoint in ("setup", "login", "static", "health"):
            return None
        if not has_user():
            return redirect(url_for("setup"))
        if session.get("user") != s.meta_get("web_user"):
            return redirect(url_for("login", next=request.path))
        return None

    @app.context_processor
    def common():
        return {"csrf": session.get("csrf", ""), "user": session.get("user"), "errors": c.ERRORS,
                "warnings": c.WARNINGS}

    @app.get("/health")
    def health():
        return "ok"

    # ------------------------------------------------------------ account
    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if has_user():
            return redirect(url_for("index"))
        if request.method == "POST":
            f = request.form
            user, pw = f.get("username", "").strip(), f.get("password", "")
            if not hmac.compare_digest(f.get("code", "").strip().upper(), setup_code()):
                flash("That setup code is wrong. It's printed in the container logs.", "error")
            elif len(user) < 3:
                flash("Pick a username of at least 3 characters.", "error")
            elif len(pw) < 8:
                flash("Use a password of at least 8 characters.", "error")
            elif pw != f.get("confirm", ""):
                flash("The two passwords don't match.", "error")
            else:
                s.meta_set("web_user", user)
                s.meta_set("web_pw_hash", generate_password_hash(pw))
                s.meta_set("web_setup_code", None)
                session.clear()
                session.permanent = True
                session.update(user=user, csrf=secrets.token_urlsafe(24))
                log.info("Web admin account created for %s", user)
                return redirect(url_for("index"))
        return render_template("setup.html", port=c.WEB_PORT)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not has_user():
            return redirect(url_for("setup"))
        ip = request.remote_addr or "?"
        rec = _fails.get(ip, [0, 0.0])
        if request.method == "POST":
            if rec[1] > time.time():
                flash(f"Too many wrong passwords. Try again in {int(rec[1] - time.time()) // 60 + 1} min.", "error")
            elif request.form.get("username", "") == s.meta_get("web_user") and \
                    check_password_hash(s.meta_get("web_pw_hash"), request.form.get("password", "")):
                _fails.pop(ip, None)
                session.clear()
                session.permanent = True
                session.update(user=s.meta_get("web_user"), csrf=secrets.token_urlsafe(24))
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("index"))
            else:
                rec[0] += 1
                if rec[0] >= MAX_FAILS:
                    rec[:] = [0, time.time() + LOCK_SECONDS]
                    log.warning("Web login locked for %s after %d failures", ip, MAX_FAILS)
                _fails[ip] = rec
                flash("Wrong username or password.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/password", methods=["GET", "POST"])
    def password():
        if request.method == "POST":
            f = request.form
            if not check_password_hash(s.meta_get("web_pw_hash"), f.get("current", "")):
                flash("Current password is wrong.", "error")
            elif len(f.get("password", "")) < 8:
                flash("Use a password of at least 8 characters.", "error")
            elif f.get("password") != f.get("confirm"):
                flash("The two passwords don't match.", "error")
            else:
                s.meta_set("web_pw_hash", generate_password_hash(f["password"]))
                flash("Password changed.", "ok")
                return redirect(url_for("index"))
        return render_template("password.html")

    # ------------------------------------------------------------ settings
    def rows():
        saved = s.stored()
        groups = {}
        for k, g, t, d, h in s.SCHEMA:
            val = s.get(k, saved)
            groups.setdefault(g, []).append({
                "key": k, "type": t, "help": h, "default": d, "source": s.source(k, saved),
                "value": "" if t == "secret" else val, "is_set": bool((val or "").strip()),
                "choices": t[7:].split(",") if t.startswith("choice:") else None})
        return groups

    @app.get("/")
    def index():
        saved = s.stored()
        env_count = sum(1 for k in s.SPEC if s.source(k, saved) == "env")
        env_keys = {k for k in s.SPEC if os.environ.get(k) is not None}
        return render_template("settings.html", groups=rows(), env_count=env_count, env_keys=env_keys)

    @app.post("/settings")
    def save_settings():
        f, saved = request.form, s.stored()
        updates, reset, problems = {}, [], []
        for k, spec in s.SPEC.items():
            if f.get(f"reset_{k}"):
                if k in saved:
                    reset.append(k)
                continue
            if k not in f:
                continue
            val = f.get(k, "").strip()
            if spec["type"] == "secret" and val == "":
                continue  # blank = keep the current secret
            if val == (s.get(k, saved) or "").strip() and k not in saved:
                continue  # unchanged and still coming from .env/default
            if val == saved.get(k):
                continue
            err = s.validate(k, val)
            if err:
                problems.append(err)
            updates[k] = val
        if problems:
            for p in problems:
                flash(p, "error")
            return redirect(url_for("index"))
        if not updates and not reset:
            flash("Nothing changed.", "ok")
            return redirect(url_for("index"))
        s.save(updates, reset)
        log.info("Settings changed on the web page: %s", ", ".join(sorted(updates) + [f"{k} (reset)" for k in reset]))
        schedule_restart()
        return render_template("restarting.html", changed=sorted(updates) + reset)

    @app.post("/settings/import-env")
    def import_env():
        saved = s.stored()
        moved = {k: s.get(k, saved) for k in s.SPEC if s.source(k, saved) == "env"}
        if not moved:
            flash("Nothing to copy: no settings are coming from .env.", "ok")
            return redirect(url_for("index"))
        s.save(moved)
        log.info("Copied %d settings from .env to the web page", len(moved))
        flash(f"Copied {len(moved)} settings from .env. They're now stored here, so you can clear them out of .env.", "ok")
        return redirect(url_for("index"))

    # ------------------------------------------------------------ CVRs
    @app.get("/cvrs")
    def cvrs():
        return render_template("cvrs.html", cvrs=state.cvr_list(), ready=not c.ERRORS)

    @app.post("/cvrs/add")
    def cvr_add():
        from . import cvr
        sym = c.norm(request.form.get("ticker", ""))
        if not sym:
            flash("Enter the ticker of the company that issued the CVR.", "error")
        elif state.cvr_get(sym):
            flash(f"{sym} is already tracked.", "ok")
        else:
            try:
                info = cvr.add(sym, f"web:{session.get('user')}")
                flash(f"Added {sym}: {len(info.get('assets') or [])} assets, "
                      f"{len(info.get('companies') or [])} companies found. Check them below.", "ok")
            except LookupError as e:
                flash(str(e), "error")
            except Exception as e:  # network or parsing trouble: show it, keep the page usable
                log.exception("CVR discovery failed for %s", sym)
                flash(f"Couldn't look up {sym}: {e}", "error")
        return redirect(url_for("cvrs") + (f"#{sym}" if sym else ""))

    @app.post("/cvrs/<sym>/edit")
    def cvr_edit(sym):
        data = state.cvr_get(sym)
        if data:
            split = lambda name: list(dict.fromkeys(x.strip() for x in request.form.get(name, "").replace(",", "\n")
                                                    .splitlines() if x.strip()))
            data["assets"], data["companies"] = split("assets"), split("companies")
            state.cvr_put(sym, data)
            flash(f"Saved {sym}. New search terms start quietly: only news from now on will alert.", "ok")
        return redirect(url_for("cvrs") + f"#{sym}")

    @app.post("/cvrs/<sym>/rediscover")
    def cvr_rediscover(sym):
        from . import cvr
        try:
            cvr.add(sym, f"web:{session.get('user')}")
            flash(f"Looked up {sym} again.", "ok")
        except Exception as e:
            flash(f"Couldn't look up {sym}: {e}", "error")
        return redirect(url_for("cvrs") + f"#{sym}")

    @app.post("/cvrs/<sym>/remove")
    def cvr_remove(sym):
        state.cvr_remove(sym)
        flash(f"Stopped tracking {sym}.", "ok")
        return redirect(url_for("cvrs"))

    return app


def start():
    from waitress import serve

    if not has_user():
        log.warning("First-time setup: open http://<this-server>:%d and enter setup code %s", c.WEB_PORT, setup_code())

    def run():
        for _ in range(15):
            try:
                serve(create_app(), host="0.0.0.0", port=c.WEB_PORT, threads=4, ident=None)
                return
            except OSError as e:  # port still held by the previous process right after a restart
                log.warning("Web page couldn't start on port %d (%s); retrying", c.WEB_PORT, e)
                time.sleep(2)
        log.error("Web page failed to start on port %d", c.WEB_PORT)

    threading.Thread(target=run, name="web", daemon=True).start()
