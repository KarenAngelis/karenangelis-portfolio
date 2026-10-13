import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date

from fastapi.testclient import TestClient
import main

BROWSER = {"User-Agent": "Mozilla/5.0 Firefox/130"}
class StatsTests(unittest.TestCase):
    def setUp(self):
        main.reset()
        self.client = TestClient(main.app)

    def view(self, path="/", headers=BROWSER, **extra):
        return self.client.post("/api/stats/event", json={"type": "view", "path": path, **extra}, headers=headers)

    def test_views_clicks_and_dimensions_are_counted(self):
        self.assertEqual(self.view("/", lang="pt-BR", device="mobile", referrer="github.com").status_code, 204)
        self.view("/", lang="pt-BR", device="desktop")
        self.view("/app/", lang="en-US")
        self.client.post("/api/stats/event", json={"type": "click", "path": "/", "name": "contato:whatsapp"}, headers=BROWSER)
        data = self.client.get("/api/stats/summary?days=7").json()
        self.assertEqual(data["totals"], {"views": 3, "visitors": 1, "clicks": 1})
        self.assertEqual(data["pages"][0], {"key": "/", "total": 2})
        self.assertEqual(data["clicks"], [{"key": "contato:whatsapp", "total": 1}])
        self.assertEqual(data["referrers"], [{"key": "github.com", "total": 1}])
        self.assertEqual(len(data["daily"]), 7)
        self.assertEqual(data["daily"][-1]["views"], 3)

    def test_different_browsers_are_different_visitors(self):
        self.view()
        self.view(headers={"User-Agent": "Mozilla/5.0 Safari/17"})
        self.assertEqual(self.client.get("/api/stats/summary").json()["totals"]["visitors"], 2)

    def test_nothing_personal_is_stored(self):
        self.view(headers={**BROWSER, "X-Forwarded-For": "203.0.113.9"})
        stored = " ".join(str(value) for row in main.database().execute("SELECT * FROM counts") for value in row)
        self.assertNotIn("203.0.113.9", stored)
        self.assertNotIn("Firefox", stored)
        self.assertEqual([column[1] for column in main.database().execute("PRAGMA table_info(counts)")], ["day", "kind", "key", "total"])
        self.assertIsNone(main.database().execute("SELECT name FROM sqlite_master WHERE name='panel_auth'").fetchone())

    def test_invalid_events_are_rejected(self):
        for body in ({"type": "view"}, {"type": "x", "path": "/"}, {"type": "view", "path": "/<script>"}, {"type": "click", "path": "/", "name": "Nome Livre"}, {"type": "click", "path": "/"}):
            self.assertEqual(self.client.post("/api/stats/event", json=body, headers=BROWSER).status_code, 422, body)
        self.assertEqual(self.client.post("/api/stats/event", content=b"x" * 700, headers=BROWSER).status_code, 413)
        self.assertEqual(self.client.get("/api/stats/summary").json()["totals"]["views"], 0)

    def test_bots_are_ignored(self):
        self.assertEqual(self.view(headers={"User-Agent": "Googlebot/2.1"}).status_code, 204)
        self.assertEqual(self.client.get("/api/stats/summary").json()["totals"]["views"], 0)

    def test_privacy_signals_are_ignored_by_server(self):
        self.assertEqual(self.view(headers={**BROWSER, "DNT": "1"}).status_code, 204)
        self.assertEqual(self.view(headers={**BROWSER, "Sec-GPC": "1"}).status_code, 204)
        self.assertEqual(self.client.get("/api/stats/summary").json()["totals"]["views"], 0)

    def test_summary_is_public_without_a_password(self):
        self.assertEqual(self.client.get("/api/stats/summary").status_code, 200)
        self.assertEqual(self.client.get("/api/stats/summary", headers={"Authorization": "Bearer errada"}).status_code, 200)

    def test_old_password_verifier_is_removed_without_losing_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "stats.sqlite3")
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE panel_auth (id INTEGER PRIMARY KEY, salt BLOB, digest BLOB, rounds INTEGER)")
                db.execute("INSERT INTO panel_auth VALUES (1,?,?,?)", (b"old", b"old", 1))
                db.execute("CREATE TABLE counts (day TEXT, kind TEXT, key TEXT, total INTEGER, PRIMARY KEY (day,kind,key))")
                db.execute("INSERT INTO counts VALUES (?,'view','/',3)", (date.today().isoformat(),))
                db.commit()
            main.reset(path)
            result = self.client.get("/api/stats/summary")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["totals"]["views"], 3)
            self.assertIsNone(main.database().execute("SELECT name FROM sqlite_master WHERE name='panel_auth'").fetchone())
            main.reset()

    def test_event_flood_is_limited_and_keys_are_capped(self):
        codes = [self.view().status_code for _ in range(95)]
        self.assertEqual(codes.count(204), 90)
        self.assertEqual(codes[-1], 429)
        main.reset()
        with main._lock:
            for index in range(main.MAX_KEYS + 5):
                main.add(main.database(), "2026-01-01", "click", f"k{index}")
        self.assertEqual(main.database().execute("SELECT total FROM counts WHERE key='outros'").fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()
