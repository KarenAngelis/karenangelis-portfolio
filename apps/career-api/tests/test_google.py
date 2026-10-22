import base64
import hashlib
import json
import time
import unittest
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
from cryptography.fernet import Fernet

from career.google import (
    CALENDAR_EVENTS,
    CONNECTED_SCOPES,
    GMAIL_READ,
    GMAIL_SEND,
    GoogleIntegration,
    IntegrationError,
)


class MemoryStore:
    def __init__(self):
        self.settings = {}
        self.secrets = {}

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value

    def get_secret(self, key):
        return self.secrets.get(key)

    def set_secret(self, key, value):
        self.secrets[key] = value


class GoogleIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.settings = SimpleNamespace(
            google_client_id="client-id", google_client_secret="secret-for-test",
            public_url="https://karenangelis.com", owner_email="owner@example.com",
            encryption_key=Fernet.generate_key().decode(), cookie_secure=True,
        )
        self.google = GoogleIntegration(self.store, self.settings)

    def transport(self, handler):
        mock = httpx.MockTransport(handler)
        self.google._client_factory = lambda **kwargs: httpx.AsyncClient(transport=mock, **kwargs)

    def connect(self, **overrides):
        tokens = {
            "access_token": "access-secret", "refresh_token": "refresh-secret",
            "email": self.settings.owner_email, "sub": "owner-sub", "name": "Owner",
            "expires_at": time.time() + 3600, "scopes": list(CONNECTED_SCOPES),
        }
        tokens.update(overrides)
        self.google._save_tokens(tokens)

    async def test_unconfigured_status_is_safe(self):
        self.settings.google_client_secret = ""
        result = await self.google.status()
        self.assertFalse(result["configured"])
        self.assertFalse(result["connected"])
        with self.assertRaises(IntegrationError):
            await self.google.authorization_url("state")

    async def test_oauth_uses_pkce_one_time_state_and_encrypts_credentials(self):
        authorization = await self.google.authorization_url("session-state", connect=True)
        params = parse_qs(urlsplit(authorization).query)
        self.assertEqual(params["access_type"], ["offline"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(set(params["scope"][0].split()), set(CONNECTED_SCOPES))
        captured = []

        def handle(request):
            captured.append(request)
            if request.url.host == "oauth2.googleapis.com":
                body = parse_qs(request.content.decode())
                actual = base64.urlsafe_b64encode(hashlib.sha256(body["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
                self.assertEqual(actual, params["code_challenge"][0])
                return httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600, "scope": " ".join(CONNECTED_SCOPES)})
            return httpx.Response(200, json={"email": "owner@example.com", "email_verified": True, "sub": "owner-sub", "name": "Owner"})

        self.transport(handle)
        identity = await self.google.complete_oauth("authorization-code", "session-state")
        self.assertTrue(identity["email_verified"])
        self.assertEqual(identity["sub"], "owner-sub")
        self.assertNotIn("access_token", identity)
        self.assertNotIn("new-refresh", self.store.secrets["google_tokens"])
        self.assertNotIn("new-access", self.store.secrets["google_tokens"])
        status = await self.google.status()
        self.assertTrue(status["gmail_connected"])
        self.assertTrue(status["calendar_connected"])
        self.assertNotIn("refresh_token", status)
        with self.assertRaises(IntegrationError) as replay:
            await self.google.complete_oauth("authorization-code", "session-state")
        self.assertEqual(replay.exception.code, "invalid_oauth_state")
        self.assertEqual(len(captured), 2)

    async def test_wrong_or_unverified_owner_is_rejected_without_saved_tokens(self):
        for identity in (
            {"email": "other@example.com", "email_verified": True, "sub": "other"},
            {"email": "owner@example.com", "email_verified": False, "sub": "owner-sub"},
        ):
            await self.google.authorization_url("state")
            self.transport(lambda request: httpx.Response(200, json={"access_token": "test-token"})
                           if request.url.host == "oauth2.googleapis.com" else httpx.Response(200, json=identity))
            with self.assertRaises(IntegrationError) as error:
                await self.google.complete_oauth("code", "state")
            self.assertEqual(error.exception.code, "owner_required")
            self.assertNotIn("google_tokens", self.store.secrets)

    async def test_expired_state_is_consumed_before_exchange(self):
        await self.google.authorization_url("expired")
        key = "google_oauth_state:" + hashlib.sha256(b"expired").hexdigest()
        pending = self.google._decrypt(self.store.get_setting(key))
        pending["expires_at"] = time.time() - 1
        self.store.set_setting(key, self.google._encrypt(pending))
        self.transport(lambda request: self.fail("Expired state made a network request"))
        with self.assertRaises(IntegrationError):
            await self.google.complete_oauth("code", "expired")
        self.assertEqual(self.store.get_setting(key), "")

    async def test_refresh_token_is_preserved_on_reconnect(self):
        self.connect()
        await self.google.authorization_url("reconnect", connect=True)
        self.transport(lambda request: httpx.Response(200, json={"access_token": "replacement"})
                       if request.url.host == "oauth2.googleapis.com"
                       else httpx.Response(200, json={"email": "owner@example.com", "email_verified": True, "sub": "owner-sub"}))
        await self.google.complete_oauth("code", "reconnect")
        self.assertEqual(self.google._tokens()["refresh_token"], "refresh-secret")

    async def test_oauth_does_not_assume_requested_permissions_were_granted(self):
        await self.google.authorization_url("partial", connect=True)
        self.transport(lambda request: httpx.Response(200, json={"access_token": "replacement", "scope": "openid email profile"})
                       if request.url.host == "oauth2.googleapis.com"
                       else httpx.Response(200, json={"email": "owner@example.com", "email_verified": True, "sub": "owner-sub"}))
        await self.google.complete_oauth("code", "partial")
        status = await self.google.status()
        self.assertFalse(status["gmail_connected"])
        self.assertFalse(status["calendar_connected"])

    async def test_offline_refresh_preserves_refresh_and_hides_google_errors(self):
        self.connect(expires_at=0)

        def handle(request):
            body = parse_qs(request.content.decode())
            self.assertEqual(body["grant_type"], ["refresh_token"])
            self.assertEqual(body["refresh_token"], ["refresh-secret"])
            return httpx.Response(200, json={"access_token": "renewed", "expires_in": 3600})

        self.transport(handle)
        self.assertEqual(await self.google.access_token(), "renewed")
        self.assertEqual(self.google._tokens()["refresh_token"], "refresh-secret")
        self.connect(expires_at=0)
        self.transport(lambda request: httpx.Response(400, json={"error_description": "PRIVATE-TOKEN"}))
        with self.assertRaises(IntegrationError) as error:
            await self.google.access_token()
        self.assertNotIn("PRIVATE-TOKEN", str(error.exception))

    async def test_search_fetches_full_messages_and_paginates_to_limit(self):
        self.connect()
        seen_pages = []

        def handle(request):
            if request.url.path.endswith("/messages"):
                page = request.url.params.get("pageToken")
                seen_pages.append(page)
                return httpx.Response(200, json={"messages": [{"id": "m1"}], "nextPageToken": "p2"} if not page
                                      else {"messages": [{"id": "m2"}, {"id": "m3"}], "nextPageToken": "unused"})
            self.assertEqual(request.url.params["format"], "full")
            message_id = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"id": message_id, "threadId": "t", "snippet": "received", "payload": {"headers": [{"name": "Subject", "value": "Interview"}]}})

        self.transport(handle)
        results = await self.google.search_messages("in:inbox", 3)
        self.assertEqual([message["id"] for message in results], ["m1", "m2", "m3"])
        self.assertEqual(seen_pages, [None, "p2"])
        self.assertEqual(results[0]["payload"]["headers"][0]["value"], "Interview")

    def application(self):
        return {"id": "application-1", "contact_email": "hiring@example.org", "email_subject": "Python developer", "email_body": "Portfolio: https://karenangelis.com"}

    async def test_send_searches_sent_uses_deterministic_mime_and_deduplicates(self):
        self.connect()
        captured = []

        def handle(request):
            captured.append(request)
            if request.method == "GET":
                self.assertIn("in:sent rfc822msgid:career.", request.url.params["q"])
                return httpx.Response(200, json={})
            raw = json.loads(request.content)["raw"]
            mime = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
            self.assertEqual(mime["To"], "hiring@example.org")
            self.assertTrue(mime["Message-ID"].startswith("<career."))
            self.assertFalse(mime.is_multipart())
            self.assertEqual(list(mime.iter_attachments()), [])
            return httpx.Response(200, json={"id": "sent-1", "threadId": "thread-1"})

        self.transport(handle)
        expected = {"message_id": "sent-1", "thread_id": "thread-1"}
        self.assertEqual(await self.google.send_application(self.application(), {}), expected)
        self.assertEqual(await self.google.send_application(self.application(), {}), expected)
        self.assertEqual(len(captured), 2)

    async def test_send_recovers_existing_sent_message_without_posting(self):
        self.connect()
        self.transport(lambda request: httpx.Response(200, json={"messages": [{"id": "existing", "threadId": "thread"}]}))
        result = await self.google.send_application(self.application(), {})
        self.assertEqual(result["message_id"], "existing")

    async def test_uncertain_send_is_not_repeated_after_timeout(self):
        self.connect()
        post_count = 0

        def handle(request):
            nonlocal post_count
            if request.method == "POST":
                post_count += 1
                raise httpx.ReadTimeout("PRIVATE ACCESS TOKEN", request=request)
            return httpx.Response(200, json={})

        self.transport(handle)
        with self.assertRaises(IntegrationError) as first:
            await self.google.send_application(self.application(), {})
        self.assertNotIn("PRIVATE ACCESS TOKEN", str(first.exception))
        with self.assertRaises(IntegrationError) as second:
            await self.google.send_application(self.application(), {})
        self.assertEqual(second.exception.code, "send_unconfirmed")
        self.assertEqual(post_count, 1)
        self.transport(lambda request: httpx.Response(200, json={"messages": [{"id": "recovered", "threadId": "t"}]}))
        recovered = await self.google.send_application(self.application(), {})
        self.assertEqual(recovered["message_id"], "recovered")

    async def test_send_rejects_header_injection_and_wrong_sender(self):
        self.connect()
        self.transport(lambda request: self.fail("Invalid email made a network request"))
        application = {**self.application(), "email_subject": "Subject\nBcc: attacker@example.com"}
        with self.assertRaises(IntegrationError):
            await self.google.send_application(application, {})
        with self.assertRaises(IntegrationError):
            await self.google.send_application(self.application(), {"facts": {"email": "someone@example.com"}})

    async def test_reconciliation_fetches_and_verifies_sent_metadata_without_posting(self):
        self.connect()
        digest, expected_id = self.google._message_identity("application-1")
        self.store.set_setting("google_send:" + digest, {"status": "uncertain"})
        requests = []

        def handle(request):
            requests.append(request)
            self.assertEqual(request.method, "GET")
            if request.url.path.endswith("/messages"):
                self.assertEqual(request.url.params["q"], f"in:sent rfc822msgid:{expected_id}")
                return httpx.Response(200, json={"messages": [{"id": "recovered"}]})
            self.assertEqual(request.url.params["format"], "metadata")
            return httpx.Response(200, json={"id": "recovered", "threadId": "thread-recovered", "labelIds": ["SENT"],
                                            "payload": {"headers": [{"name": "Message-ID", "value": f"<{expected_id}>"}]}})

        self.transport(handle)
        receipt = await self.google.reconcile_application("application-1")
        self.assertEqual(receipt, {"message_id": "recovered", "thread_id": "thread-recovered"})
        self.assertEqual(self.store.get_setting("google_send:" + digest)["status"], "sent")
        self.assertEqual(len(requests), 2)

    async def test_reconciliation_missing_or_malformed_result_never_submits(self):
        self.connect()
        for response in ({}, {"messages": "not-a-list"}, {"messages": [None, {}, {"id": 123}]}):
            requests = []

            def handle(request):
                requests.append(request)
                self.assertEqual(request.method, "GET")
                return httpx.Response(200, json=response)

            self.transport(handle)
            self.assertIsNone(await self.google.reconcile_application("application-1"))
            self.assertEqual(len(requests), 1)

    async def test_reconciliation_rejects_non_sent_or_wrong_message_id(self):
        self.connect()
        digest, expected_id = self.google._message_identity("application-1")
        self.store.set_setting("google_send:" + digest, {"status": "uncertain"})
        for labels, header in ((["INBOX"], expected_id), (["SENT"], "another@example.com")):
            def handle(request):
                self.assertEqual(request.method, "GET")
                if request.url.path.endswith("/messages"):
                    return httpx.Response(200, json={"messages": [{"id": "m"}]})
                return httpx.Response(200, json={"id": "m", "threadId": "t", "labelIds": labels,
                                                "payload": {"headers": [{"name": "Message-ID", "value": f"<{header}>"}]}})
            self.transport(handle)
            self.assertIsNone(await self.google.reconcile_application("application-1"))
            self.assertEqual(self.store.get_setting("google_send:" + digest)["status"], "uncertain")

    def interview(self):
        return {"title": "Technical interview", "start": "2026-10-23T10:00:00-03:00", "end": "2026-10-23T11:00:00-03:00", "time_zone": "America/Sao_Paulo", "meeting_url": "https://meet.google.com/example", "source_message_id": "invitation-1"}

    async def test_calendar_creates_deterministic_event_without_invites_and_recovers_duplicate(self):
        self.connect()
        captured = []
        stored = {}

        def handle(request):
            captured.append(request)
            if request.method == "GET":
                return httpx.Response(200, json=stored) if stored else httpx.Response(404, json={"error": {}})
            body = json.loads(request.content)
            self.assertEqual(request.url.params["sendUpdates"], "none")
            self.assertNotIn("attendees", body)
            self.assertEqual(body["start"]["timeZone"], "America/Sao_Paulo")
            self.assertTrue(all(character in "0123456789abcdef" for character in body["id"]))
            stored.update(id=body["id"], htmlLink="https://calendar.google.com/event")
            return httpx.Response(200, json=stored)

        self.transport(handle)
        first = await self.google.create_interview("application-1", self.interview())
        second = await self.google.create_interview("application-1", self.interview())
        self.assertEqual(first, second)
        self.assertEqual([request.method for request in captured], ["GET", "POST", "GET"])

    async def test_calendar_requires_explicit_consistent_timezone(self):
        self.connect()
        self.transport(lambda request: self.fail("Invalid interview made a network request"))
        for fields in (
            {"start": "2026-10-23T10:00:00"}, {"time_zone": "UTC"},
            {"time_zone": "Invalid/Zone"}, {"end": "2026-10-23T09:00:00-03:00"},
        ):
            with self.assertRaises(IntegrationError) as error:
                await self.google.create_interview("application-1", {**self.interview(), **fields})
            self.assertEqual(error.exception.code, "invalid_interview")

    async def test_calendar_slot_identity_deduplicates_emails_and_allows_multiple_rounds(self):
        self.connect()
        events = {}
        created = []

        def handle(request):
            if request.method == "GET":
                identifier = request.url.path.rsplit("/", 1)[1]
                return httpx.Response(200, json=events[identifier]) if identifier in events else httpx.Response(404, json={})
            body = json.loads(request.content)
            created.append(body)
            events[body["id"]] = {"id": body["id"], "htmlLink": "https://calendar.google.com/event"}
            return httpx.Response(200, json=events[body["id"]])

        self.transport(handle)
        first = await self.google.create_interview("application-1", self.interview())
        duplicate = await self.google.create_interview("application-1", {**self.interview(), "source_message_id": "confirmation-2", "title": "Confirmed interview"})
        equivalent = await self.google.create_interview("application-1", {**self.interview(), "start": "2026-10-23T13:00:00Z", "end": "2026-10-23T14:00:00+00:00", "time_zone": "UTC", "source_message_id": "confirmation-3"})
        next_round = await self.google.create_interview("application-1", {**self.interview(), "start": "2026-10-24T10:00:00-03:00", "end": "2026-10-24T11:00:00-03:00", "source_message_id": "owner"})
        self.assertEqual(first, duplicate)
        self.assertEqual(first, equivalent)
        self.assertNotEqual(first["id"], next_round["id"])
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]["extendedProperties"]["private"]["career_source_message_id"], "invitation-1")

    async def test_missing_scopes_do_not_make_requests(self):
        self.connect(scopes=["openid", "email", "profile"])
        self.transport(lambda request: self.fail("Missing scope made a network request"))
        for operation in (
            self.google.search_messages("in:inbox"),
            self.google.send_application(self.application(), {}),
            self.google.create_interview("a", self.interview()),
        ):
            with self.assertRaises(IntegrationError) as error:
                await operation
            self.assertEqual(error.exception.code, "missing_scopes")


if __name__ == "__main__":
    unittest.main()
