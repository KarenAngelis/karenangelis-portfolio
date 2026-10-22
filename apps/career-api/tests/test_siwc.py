import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs

import httpx

from career.siwc import DIRECT_SCOPE, RESOURCE, SiwcCredentials, SiwcError, TOKEN_ENDPOINT


class SiwcTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "credentials.json"
        self.settings = SimpleNamespace(siwc_credentials_file=str(self.path))

    async def asyncTearDown(self):
        self.directory.cleanup()

    def registration(self, **changes):
        value = {"issuer": "https://auth.openai.com", "subject": "test-validated-subject",
                 "client_id": "oaiapp_test-issued", "email": "owner@example.com",
                 "access_token": "test-access", "refresh_token": "test-refresh", "id_token": "test-id",
                 "scopes": [DIRECT_SCOPE, "resource.invoke", "offline_access", "openid", "email"],
                 "saved_at": datetime.now(timezone.utc).isoformat(), "expires_in": 3600,
                 "ext_agent_host_id": "urn:uuid:00000000-0000-4000-8000-000000000001"}
        value.update(changes)
        self.path.write_text(json.dumps(value))
        self.path.chmod(0o600)
        return value

    async def test_missing_registration_requires_pairing_without_token_or_path_leaks(self):
        provider = SiwcCredentials(self.settings)
        metadata = provider.metadata()
        self.assertFalse(metadata["configured"])
        self.assertTrue(metadata["pairing_required"])
        self.assertNotIn(str(self.path), json.dumps(metadata))
        with self.assertRaises(SiwcError):
            await provider.access_token()

    async def test_fresh_registration_returns_token_and_uses_distinct_stable_vm_host(self):
        original = self.registration()
        provider = SiwcCredentials(self.settings)
        self.assertTrue(provider.metadata()["token_ready"])
        self.assertNotIn("test-access", json.dumps(provider.metadata()))
        self.assertEqual(await provider.access_token(), "test-access")
        host = provider.host_id()
        self.assertNotEqual(host, original["ext_agent_host_id"])
        self.assertEqual(host, provider.host_id())
        self.assertEqual(json.loads(self.path.read_text())["ext_agent_host_id"], host)
        self.assertEqual(os.stat(provider.host_path).st_mode & 0o777, 0o600)

    async def test_refresh_is_serialized_and_rotating_record_saved_atomically(self):
        self.registration(saved_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
        requests = []
        async def respond(request):
            requests.append(request)
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={"access_token": "replacement-access", "refresh_token": "replacement-refresh",
                                           "expires_in": 3600, "scope": DIRECT_SCOPE + " resource.invoke offline_access"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            provider = SiwcCredentials(self.settings, client=client)
            values = await asyncio.gather(provider.access_token(), provider.access_token())
        self.assertEqual(values, ["replacement-access", "replacement-access"])
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), TOKEN_ENDPOINT)
        self.assertEqual(parse_qs(requests[0].content.decode()), {
            "grant_type": ["refresh_token"], "client_id": ["oaiapp_test-issued"],
            "refresh_token": ["test-refresh"], "resource": [RESOURCE],
        })
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["refresh_token"], "replacement-refresh")
        self.assertEqual(saved["id_token"], "test-id")
        self.assertEqual(saved["subject"], "test-validated-subject")
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(list(self.path.parent.glob(".credentials-*")), [])

    async def test_restricted_file_and_codex_auth_file_are_rejected(self):
        self.registration()
        self.path.chmod(0o644)
        provider = SiwcCredentials(self.settings)
        self.assertFalse(provider.metadata()["configured"])
        with self.assertRaises(SiwcError):
            await provider.access_token()
        wrong = SiwcCredentials(SimpleNamespace(siwc_credentials_file=str(self.path.parent / "auth.json")))
        self.assertIn("auth.json", wrong.metadata()["reason"])

    async def test_symbolic_link_registration_is_rejected(self):
        self.registration()
        link = self.path.parent / "linked.json"
        link.symlink_to(self.path)
        provider = SiwcCredentials(SimpleNamespace(siwc_credentials_file=str(link)))
        with self.assertRaises(SiwcError):
            await provider.access_token()

    async def test_identity_only_and_dynamic_placeholder_client_do_not_authorize_inference(self):
        self.registration(scopes=["openid", "email"])
        provider = SiwcCredentials(self.settings)
        self.assertTrue(provider.metadata()["pairing_required"])
        with self.assertRaises(SiwcError):
            await provider.access_token()
        self.registration(client_id="dynamic_agent_client")
        self.assertFalse(provider.metadata()["configured"])

    async def test_temporary_refresh_failure_preserves_registration(self):
        self.registration(saved_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503, json={"detail": "SECRET upstream"}))) as client:
            provider = SiwcCredentials(self.settings, client=client)
            with self.assertRaises(SiwcError) as caught:
                await provider.access_token()
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["refresh_token"], "test-refresh")
        self.assertNotIn("SECRET", str(caught.exception))

    async def test_revoked_refresh_token_clears_unusable_tokens_but_retains_registration(self):
        self.registration(saved_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(400, json={"error": "invalid_grant"}))) as client:
            provider = SiwcCredentials(self.settings, client=client)
            with self.assertRaises(SiwcError):
                await provider.access_token()
        saved = json.loads(self.path.read_text())
        self.assertTrue(saved["needs_reauth"])
        self.assertNotIn("access_token", saved)
        self.assertNotIn("refresh_token", saved)
        self.assertEqual(saved["client_id"], "oaiapp_test-issued")
        self.assertTrue(provider.metadata()["pairing_required"])


if __name__ == "__main__":
    unittest.main()
