"""Settings store precedence and the web page: first-run setup, login, CSRF, saving settings, CVR edits."""
import os
import re
import unittest
from unittest import mock

from app import settings as s
from app import web
from app.store import state


def reset_db():
    db = s.connect()
    with db:
        db.execute("DELETE FROM settings")
        db.execute("DELETE FROM meta WHERE key LIKE 'web_%' AND key != 'web_secret'")
    db.close()
    web._fails.clear()


class SettingsStore(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_web_beats_env_beats_default(self):
        with mock.patch.dict(os.environ, {"MOVE_THRESHOLD_PCT": "7"}):
            self.assertEqual((s.get("MOVE_THRESHOLD_PCT"), s.source("MOVE_THRESHOLD_PCT")), ("7", "env"))
            s.save({"MOVE_THRESHOLD_PCT": "9"})
            self.assertEqual((s.get("MOVE_THRESHOLD_PCT"), s.source("MOVE_THRESHOLD_PCT")), ("9", "web"))
            s.save({}, reset=["MOVE_THRESHOLD_PCT"])
            self.assertEqual(s.get("MOVE_THRESHOLD_PCT"), "7")
        os.environ.pop("CVR_INTERVAL", None)
        self.assertEqual((s.get("CVR_INTERVAL"), s.source("CVR_INTERVAL")), ("1800", "default"))

    def test_validate(self):
        self.assertIsNone(s.validate("MAX_TICKERS", "40"))
        self.assertIsNotNone(s.validate("MAX_TICKERS", "forty"))
        self.assertIsNotNone(s.validate("MOVE_THRESHOLD_PCT", "abc"))
        self.assertIsNotNone(s.validate("LOG_LEVEL", "LOUD"))
        self.assertIsNone(s.validate("LOG_LEVEL", "DEBUG"))


class WebPage(unittest.TestCase):
    def setUp(self):
        reset_db()
        self.restarts = []
        self.app = web.create_app(restart=lambda: self.restarts.append(1))
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def csrf(self):
        self.client.get("/health")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def make_account(self):
        code = web.setup_code()
        r = self.client.post("/setup", data={"csrf": self.csrf(), "code": code, "username": "admin",
                                             "password": "correct horse", "confirm": "correct horse"})
        self.assertEqual(r.status_code, 302)
        return code

    def test_first_visit_goes_to_setup_and_needs_code(self):
        r = self.client.get("/")
        self.assertIn("/setup", r.headers["Location"])
        r = self.client.post("/setup", data={"csrf": self.csrf(), "code": "WRONG", "username": "admin",
                                             "password": "correct horse", "confirm": "correct horse"},
                             follow_redirects=True)
        self.assertIn(b"setup code is wrong", r.data)
        self.assertFalse(web.has_user())
        self.make_account()
        self.assertTrue(web.has_user())
        self.assertIsNone(s.meta_get("web_setup_code"))  # one-time
        self.assertNotEqual(s.meta_get("web_pw_hash"), "correct horse")  # stored hashed
        self.assertEqual(self.client.get("/").status_code, 200)  # logged in right away

    def test_login_logout_and_lockout(self):
        self.make_account()
        self.client.post("/logout", data={"csrf": self.csrf()})
        self.assertIn("/login", self.client.get("/").headers["Location"])
        for _ in range(web.MAX_FAILS):
            self.client.post("/login", data={"csrf": self.csrf(), "username": "admin", "password": "nope"})
        r = self.client.post("/login", data={"csrf": self.csrf(), "username": "admin", "password": "correct horse"},
                             follow_redirects=True)
        self.assertIn(b"Too many wrong passwords", r.data)
        web._fails.clear()
        r = self.client.post("/login", data={"csrf": self.csrf(), "username": "admin", "password": "correct horse"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_post_without_csrf_is_rejected(self):
        self.make_account()
        r = self.client.post("/settings", data={"MAX_TICKERS": "10"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("MAX_TICKERS", s.stored())

    def test_save_settings_stores_changes_and_restarts(self):
        self.make_account()
        with mock.patch("threading.Timer") as timer:
            r = self.client.post("/settings", data={"csrf": self.csrf(), "MAX_TICKERS": "25", "TRACK_13G": "true",
                                                    "FINNHUB_API_KEY": ""})
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"Restarting", r.data)
            timer.assert_called_once()
        saved = s.stored()
        self.assertEqual((saved["MAX_TICKERS"], saved["TRACK_13G"]), ("25", "true"))
        self.assertNotIn("FINNHUB_API_KEY", saved)  # blank secret = keep current

    def test_bad_number_is_not_saved(self):
        self.make_account()
        r = self.client.post("/settings", data={"csrf": self.csrf(), "MAX_TICKERS": "lots"}, follow_redirects=True)
        self.assertIn(b"MAX_TICKERS must be a whole number", r.data)
        self.assertNotIn("MAX_TICKERS", s.stored())

    def test_secrets_are_never_shown(self):
        self.make_account()
        s.save({"DISCORD_WEBHOOK_URL": "https://discord.example/hook/SECRET123"})
        page = self.client.get("/").data.decode()
        self.assertNotIn("SECRET123", page)
        self.assertIn("Saved. Leave blank to keep it.", page)

    def test_import_env(self):
        self.make_account()
        with mock.patch.dict(os.environ, {"MOVE_THRESHOLD_PCT": "6"}):
            self.client.post("/settings/import-env", data={"csrf": self.csrf()})
            self.assertEqual(s.stored().get("MOVE_THRESHOLD_PCT"), "6")

    def test_cvr_page_edit_and_remove(self):
        self.make_account()
        state.cvr_put("CYCN", {"name": "Cyclerion Therapeutics, Inc.", "assets": ["Praliciguat"], "companies": []}, "test")
        page = self.client.get("/cvrs").data.decode()
        self.assertIn("Cyclerion Therapeutics", page)
        self.client.post("/cvrs/CYCN/edit", data={"csrf": self.csrf(), "assets": "Praliciguat\nZagociguat, CY3018",
                                                  "companies": "Akebia\n\nTisento"})
        x = state.cvr_get("CYCN")
        self.assertEqual(x["assets"], ["Praliciguat", "Zagociguat", "CY3018"])
        self.assertEqual(x["companies"], ["Akebia", "Tisento"])
        self.client.post("/cvrs/CYCN/remove", data={"csrf": self.csrf()})
        self.assertIsNone(state.cvr_get("CYCN"))

    def test_reset_login_command(self):
        import runpy
        self.make_account()
        runpy.run_module("app.reset_login", run_name="__main__")
        self.assertFalse(web.has_user())
        self.assertTrue(s.meta_get("web_setup_code"))
        self.assertIn("/setup", self.client.get("/").headers["Location"])

    def test_open_redirect_blocked(self):
        self.make_account()
        self.client.post("/logout", data={"csrf": self.csrf()})
        r = self.client.post("/login?next=//evil.example", data={"csrf": self.csrf(), "username": "admin",
                                                                  "password": "correct horse"})
        self.assertFalse(re.search(r"evil\.example", r.headers["Location"]))


if __name__ == "__main__":
    unittest.main()
