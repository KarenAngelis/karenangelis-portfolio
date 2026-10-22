"""HTTP contract tests with real SQLite and no external requests or account actions."""
import atexit
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi.testclient import TestClient

# main constructs a default app during import; keep its database out of /data.
_import_directory = tempfile.TemporaryDirectory(prefix="career-api-import-")
with patch.dict(os.environ, {"CAREER_DATA_DIR": _import_directory.name, "CAREER_WORKER_ENABLED": "false"}):
    import main as api
from career.config import Settings
from career.store import Store


def _clean_import_app():
    api.app.state.store.close()
    _import_directory.cleanup()


atexit.register(_clean_import_app)


class FakeGoogle:
    def __init__(self, owner):
        self.configured = True
        self.identity = {"email": owner, "email_verified": True, "name": "Karen"}
        self.authorization_calls = []
        self.exchange_calls = []
        self.calendar_calls = []
        self.search_messages = AsyncMock(return_value=[])
        self.send_application = AsyncMock(side_effect=AssertionError("No email may be sent by API tests."))

    async def status(self):
        return {"configured": self.configured, "gmail_connected": True, "calendar_connected": True}

    async def authorization_url(self, state, connect=False):
        self.authorization_calls.append({"state": state, "connect": connect})
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"state": state})

    async def complete_oauth(self, code, state):
        self.exchange_calls.append({"code": code, "state": state})
        return dict(self.identity)

    async def create_interview(self, application_id, interview):
        self.calendar_calls.append({"application_id": application_id, "interview": interview})
        return {"id": "calendar-test-1", "htmlLink": "https://calendar.google.com/calendar/event?eid=test"}


class FakeCodex:
    def __init__(self):
        self.closed = False
        self.proposal = {"eligible": True, "reason": "Explicit worldwide remote role.",
            "missing_required": [], "location_evidence": "Remote worldwide",
            "subject": "Application: Python Developer", "body": "My application based on the profile."}
        self.run_json = AsyncMock(side_effect=self._proposal)

    async def status(self):
        return {"available": True, "connected": True}

    async def login(self):
        return {"status": "pending", "verification_uri": "https://auth.openai.com/device", "user_code": "TEST-ONLY"}

    async def close(self):
        self.closed = True

    async def _proposal(self, *args, **kwargs):
        return dict(self.proposal)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="career-api-test-")
        self.settings = Settings(data_dir=self.directory.name, public_url="https://karenangelis.com",
            owner_email="karen.denich@gmail.com", cookie_secure=True, worker_enabled=False,
            codex_home=str(Path(self.directory.name) / "codex"),
            public_data_dir=str(Path(__file__).resolve().parents[3] / "web" / "data"),
            google_client_id="client-id-PRIVATE-SENTINEL", google_client_secret="client-secret-PRIVATE-SENTINEL",
            encryption_key="encryption-PRIVATE-SENTINEL")
        self.store = Store(self.settings.db_path)
        self.store.set_secret("google_tokens", "encrypted-token-PRIVATE-SENTINEL")
        self.google, self.codex = FakeGoogle(self.settings.owner_email), FakeCodex()
        self.app = api.create_app(self.settings, self.store, self.google, self.codex)
        self.stack = ExitStack()
        # A missed mock must fail instead of touching a real provider.
        self.stack.enter_context(patch("career.sources.httpx.AsyncClient", side_effect=AssertionError("Live requests are forbidden.")))
        self.client = self.stack.enter_context(TestClient(self.app, base_url=self.settings.public_url, follow_redirects=False))

    def tearDown(self):
        self.stack.close()
        self.store.close()
        self.directory.cleanup()

    def start_login(self, connect=False):
        response = self.client.get(api.API + "/auth/google/start", params={"connect": int(connect)})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(urlsplit(response.headers["location"]).hostname, "accounts.google.com")
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        self.assertEqual(self.client.cookies.get(api.STATE_COOKIE), state)
        return state, response

    def login(self):
        state, _ = self.start_login()
        response = self.client.get(api.API + "/auth/google/callback", params={"code": "test-code", "state": state})
        self.assertEqual(response.status_code, 303, response.text)
        session = self.client.get(api.API + "/session").json()
        self.assertTrue(session["authenticated"])
        return {"x-csrf-token": session["csrf_token"], "origin": self.settings.public_url}

    def profile_payload(self):
        return {"resume_text": "Confirmed professional facts.", "skills": ["Python"],
            "facts": {"name": "Karen", "residence_country": "BR"},
            "preferences": {"roles": ["Python Developer"], "countries": ["BR"],
                            "remote_only": True, "min_score": 80, "auto_apply": False}}

    def create_job(self, headers):
        payload = {"company": "Example", "title": "Python Developer", "url": "https://example.org/jobs/1",
                   "description": "Python. Remote worldwide. Apply at jobs@example.org.",
                   "location": "Worldwide", "apply_email": "jobs@example.org"}
        response = self.client.post(api.API + "/jobs", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), payload

    def test_anonymous_requests_cannot_reach_any_private_handler(self):
        cases = [
            ("GET", "/dashboard", None), ("GET", "/sources", None),
            ("PUT", "/profile", self.profile_payload()), ("POST", "/profile/import-site", None),
            ("POST", "/profile/sync-github", {"username": "KarenAngelis"}),
            ("POST", "/answers", {"intent": "formation", "text": "Marketing"}),
            ("DELETE", "/answers/missing", None),
            ("POST", "/jobs", {"company": "Example", "title": "Developer", "url": "https://example.org/jobs/1", "description": "Python"}),
            ("POST", "/sources", {"kind": "lever", "identifier": "example"}),
            ("POST", "/applications", {"job_id": "missing"}),
            ("POST", "/applications/missing/prepare", None),
            ("POST", "/interviews", {"application_id": "missing", "title": "Interview", "start": "2026-10-26T10:00:00-03:00", "end": "2026-10-26T11:00:00-03:00"}),
            ("POST", "/codex/login", None), ("POST", "/run", None),
            ("POST", "/sync-mail", None), ("POST", "/logout", None),
        ]
        for method, path, payload in cases:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, api.API + path, json=payload)
                self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.store.list_jobs(), [])
        self.assertEqual(self.store.list_applications(), [])
        self.codex.run_json.assert_not_awaited()
        self.google.send_application.assert_not_awaited()

    def test_session_and_setup_status_never_expose_configuration_or_provider_secrets(self):
        response = self.client.get(api.API + "/session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": False, "user": None, "csrf_token": None,
            "setup_required": False, "google_configured": True})
        self.assertNotIn("PRIVATE-SENTINEL", response.text)
        self.google.configured = False
        response = self.client.get(api.API + "/session")
        self.assertTrue(response.json()["setup_required"])
        response = self.client.get(api.API + "/auth/google/start")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("PRIVATE-SENTINEL", response.text)

    def test_callback_requires_matching_state_cookie_before_token_exchange(self):
        response = self.client.get(api.API + "/auth/google/callback", params={"code": "test-code", "state": "invented"})
        self.assertEqual(response.status_code, 400)
        state, _ = self.start_login()
        response = self.client.get(api.API + "/auth/google/callback", params={"code": "test-code", "state": state + "wrong"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get(api.API + "/auth/google/callback", params={"state": state})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.google.exchange_calls, [])
        self.assertFalse(self.client.get(api.API + "/session").json()["authenticated"])

    def test_callback_rejects_wrong_owner_or_unverified_identity(self):
        for identity in [
            {"email": "other@example.org", "email_verified": True},
            {"email": self.settings.owner_email, "email_verified": False},
        ]:
            with self.subTest(identity=identity):
                self.google.identity = identity
                state, _ = self.start_login()
                response = self.client.get(api.API + "/auth/google/callback", params={"code": "test-code", "state": state})
                self.assertEqual(response.status_code, 403)
                self.assertFalse(self.client.get(api.API + "/session").json()["authenticated"])

    def test_login_uses_secure_httponly_cookies_and_connect_is_incremental(self):
        self.assertEqual(self.client.get(api.API + "/auth/google/start?connect=1").status_code, 401)
        state, response = self.start_login()
        cookie = response.headers["set-cookie"].lower()
        for attribute in ["secure", "httponly", "samesite=lax", "path=/api/career/auth/google"]:
            self.assertIn(attribute, cookie)
        self.assertFalse(self.google.authorization_calls[-1]["connect"])
        self.google.identity["email"] = self.settings.owner_email.upper()
        response = self.client.get(api.API + "/auth/google/callback", params={"code": "test-code", "state": state})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/carreira/")
        session_cookie = response.headers.get_list("set-cookie")[0].lower()
        self.assertIn("secure", session_cookie)
        self.assertIn("httponly", session_cookie)
        self.assertIn("path=/api/career", session_cookie)
        session = self.client.get(api.API + "/session").json()
        self.assertEqual(session["user"]["email"], self.settings.owner_email)
        self.assertTrue(session["csrf_token"])
        self.start_login(connect=True)
        self.assertTrue(self.google.authorization_calls[-1]["connect"])

    def test_expired_or_forged_session_cannot_authorize_requests(self):
        self.client.cookies.set(api.COOKIE, "forged-session", domain="karenangelis.com", path=api.API)
        self.assertEqual(self.client.get(api.API + "/dashboard").status_code, 401)
        self.client.cookies.clear()
        self.login()
        token = self.client.cookies.get(api.COOKIE)
        key = "session:" + hashlib.sha256(token.encode()).hexdigest()
        session = self.store.get_setting(key)
        self.store.set_setting(key, {**session, "expires": time.time() - 1})
        self.assertEqual(self.client.get(api.API + "/dashboard").status_code, 401)

    def test_csrf_and_origin_protect_writes_and_logout_invalidates_session(self):
        headers = self.login()
        url = api.API + "/profile"
        self.assertEqual(self.client.put(url, json=self.profile_payload()).status_code, 403)
        self.assertEqual(self.client.put(url, json=self.profile_payload(), headers={**headers, "origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.put(url, json=self.profile_payload(), headers={**headers, "x-csrf-token": "wrong"}).status_code, 403)
        self.assertEqual(self.client.put(url, json=self.profile_payload(), headers=headers).status_code, 200)
        self.assertEqual(self.client.post(api.API + "/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get(api.API + "/dashboard").status_code, 401)
        self.assertFalse(self.client.get(api.API + "/session").json()["authenticated"])

    def test_import_profile_and_answer_bank_write_real_database(self):
        headers = self.login()
        response = self.client.post(api.API + "/profile/import-site", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()
        self.assertIn("portfolio_sources", profile)
        self.assertTrue(profile["skills"])
        self.assertEqual(profile["facts"]["email"], self.settings.owner_email)
        self.assertFalse(profile["preferences"]["auto_apply"])
        self.assertEqual(self.store.get_profile()["revision"], profile["revision"])
        response = self.client.put(api.API + "/profile", json=self.profile_payload(), headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["revision"], profile["revision"])
        response = self.client.post(api.API + "/answers", json={"intent": "formation", "text": "Marketing", "source": "cv-v1"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual(self.store.list_answers()[0]["source"], "cv-v1")
        updated = self.client.post(api.API + "/answers", json={"intent": "formation", "text": "Updated", "source": "cv-v2"}, headers=headers).json()
        self.assertEqual(updated["id"], answer["id"])
        self.assertEqual(len(self.store.list_answers()), 1)
        self.assertEqual(self.client.delete(api.API + "/answers/" + answer["id"], headers=headers).status_code, 200)
        self.assertEqual(self.store.list_answers(), [])

    def test_jobs_applications_prepare_and_timeline_are_persisted_without_sending(self):
        headers = self.login()
        self.assertEqual(self.client.put(api.API + "/profile", json=self.profile_payload(), headers=headers).status_code, 200)
        job, payload = self.create_job(headers)
        duplicate = self.client.post(api.API + "/jobs", json=payload, headers=headers).json()
        self.assertEqual(duplicate["id"], job["id"])
        response = self.client.post(api.API + "/applications", json={"job_id": job["id"]}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        application = response.json()
        self.assertEqual(application["status"], "draft")
        response = self.client.post(api.API + "/applications", json={"job_id": job["id"]}, headers=headers)
        self.assertEqual(response.json()["id"], application["id"])
        response = self.client.post(api.API + "/applications/" + application["id"] + "/prepare", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ready")
        dashboard = self.client.get(api.API + "/dashboard").json()
        self.assertEqual(dashboard["stats"]["jobs"], 1)
        self.assertEqual(dashboard["stats"]["applications"], 1)
        self.assertEqual(dashboard["stats"]["sent"], 0)
        self.assertEqual(dashboard["applications"][0]["snapshot"]["profile"]["skills"], ["Python"])
        self.assertEqual([event["kind"] for event in dashboard["events"]], ["application.created", "application.updated"])
        self.assertFalse(dashboard["worker"]["enabled"])
        self.assertNotIn("PRIVATE-SENTINEL", str(dashboard))
        self.google.send_application.assert_not_awaited()

    def test_calendar_endpoint_records_one_confirmed_interview_in_timeline(self):
        headers = self.login()
        job, _ = self.create_job(headers)
        application = self.client.post(api.API + "/applications", json={"job_id": job["id"]}, headers=headers).json()
        payload = {"application_id": application["id"], "title": "Interview · Example",
                   "start": "2026-10-26T10:00:00-03:00", "end": "2026-10-26T11:00:00-03:00",
                   "time_zone": "America/Sao_Paulo", "meeting_url": "https://meet.google.com/abc-defg-hij"}
        response = self.client.post(api.API + "/interviews", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], "calendar-test-1")
        dashboard = self.client.get(api.API + "/dashboard").json()
        self.assertEqual(dashboard["applications"][0]["status"], "interview")
        self.assertEqual(dashboard["stats"]["interviews"], 1)
        self.assertEqual(dashboard["interviews"][0]["start"], payload["start"])
        self.assertEqual(len(self.google.calendar_calls), 1)
        invalid = {**payload, "start": "2026-10-26T10:00:00", "end": "2026-10-26T11:00:00", "time_zone": "Unknown/Nowhere"}
        self.assertEqual(self.client.post(api.API + "/interviews", json=invalid, headers=headers).status_code, 422)
        self.assertEqual(len(self.google.calendar_calls), 1)

    def test_github_sync_uses_explicit_mock_and_persists_provenance(self):
        headers = self.login()
        projects = [{"name": "Example", "url": "https://github.com/KarenAngelis/example", "source": "github_public_metadata"}]
        with patch.object(api, "github_projects", new=AsyncMock(return_value=projects)) as fetch:
            response = self.client.post(api.API + "/profile/sync-github", json={"username": "KarenAngelis"}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        fetch.assert_awaited_once_with("KarenAngelis")
        self.assertEqual(self.store.get_profile()["github_projects"], projects)
        self.assertIn("github_synced_at", self.store.get_profile())

    def test_sources_validation_missing_application_and_private_headers(self):
        headers = self.login()
        response = self.client.post(api.API + "/sources", json={"kind": "lever", "identifier": "example"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.client.post(api.API + "/sources", json={"kind": "lever", "identifier": "example"}, headers=headers)
        self.assertEqual(self.client.get(api.API + "/sources").json(), [{"kind": "lever", "identifier": "example"}])
        self.assertEqual(self.client.post(api.API + "/sources", json={"kind": "lever", "identifier": "../../internal"}, headers=headers).status_code, 422)
        self.assertEqual(self.client.post(api.API + "/applications", json={"job_id": "missing"}, headers=headers).status_code, 404)
        response = self.client.get(api.API + "/dashboard")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-robots-tag"], "noindex, nofollow")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertNotIn("PRIVATE-SENTINEL", response.text)


if __name__ == "__main__":
    unittest.main()
