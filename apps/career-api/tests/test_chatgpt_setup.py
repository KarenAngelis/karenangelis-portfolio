"""The local OAuth helper is exercised with fake HTTP and generated test keys."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "connect-career-chatgpt.py"
spec = importlib.util.spec_from_file_location("career_chatgpt_setup", SCRIPT)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.private_key.public_key()))
        cls.public_jwk.update(kid="test-key", use="sig", alg="RS256")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.output = Path(self.directory.name) / "credentials.json"
        self.attempt = setup.transaction("http://127.0.0.1:1455/auth/callback", "urn:uuid:test-local-host")
        self.requests = []

    def tearDown(self):
        self.directory.cleanup()

    def claims(self, **changes):
        claims = {"sub": "test-owner", "iss": setup.ISSUER, "aud": "oaiapp_test-issued", "iat": int(time.time()),
                  "exp": int(time.time()) + 3600, "nonce": self.attempt["nonce"], "email": "owner@example.com"}
        claims.update(changes)
        return claims

    def token(self, **changes):
        return jwt.encode(self.claims(**changes), self.private_key, algorithm="RS256", headers={"kid": "test-key"})

    def client(self, token=None, scope=setup.SCOPES):
        encoded = token or self.token()
        def respond(request):
            self.requests.append(request)
            if str(request.url) == setup.TOKEN:
                return httpx.Response(200, json={"id_token": encoded, "access_token": "TEST_ACCESS", "refresh_token": "TEST_REFRESH",
                                                "expires_in": 3600, "token_type": "Bearer", "scope": scope})
            if str(request.url) == setup.DISCOVERY:
                return httpx.Response(200, json={"issuer": setup.ISSUER, "jwks_uri": setup.ISSUER + "/.well-known/jwks.json"})
            if str(request.url) == setup.ISSUER + "/.well-known/jwks.json":
                return httpx.Response(200, json={"keys": [self.public_jwk]})
            raise AssertionError("Unexpected HTTP request")
        return httpx.Client(transport=httpx.MockTransport(respond))

    def callback(self, **changes):
        query = {"code": "TEST_AUTHORIZATION_CODE", "state": self.attempt["state"], "client_id": "oaiapp_test-issued"}
        query.update(changes)
        return query

    def test_initial_authorization_uses_loopback_pkce_nonce_and_matching_agent_name(self):
        parameters = parse_qs(urlsplit(setup.authorization_url(self.attempt)).query)
        self.assertEqual(parameters["client_id"], ["dynamic_agent_client"])
        self.assertEqual(parameters["agent_name_hint"], ["karen_career_manager"])
        self.assertEqual(parameters["redirect_uri"], ["http://127.0.0.1:1455/auth/callback"])
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.assertNotIn(self.attempt["verifier"], setup.authorization_url(self.attempt))
        for uri in ("https://karenangelis.com/auth/callback", "http://localhost:1455/auth/callback", "http://127.0.0.1:1455/callback"):
            with self.assertRaises(setup.SetupError):
                setup.transaction(uri, "host")

    def test_callback_state_error_expiry_and_reuse_are_rejected_before_exchange(self):
        with self.assertRaises(setup.SetupError):
            setup.consume_callback(self.attempt, self.callback(state="wrong"))
        with self.assertRaises(setup.SetupError):
            setup.consume_callback(self.attempt, self.callback())
        for change in ({"error": "access_denied"}, {"client_id": "dynamic_agent_client"}):
            attempt = setup.transaction("http://127.0.0.1:1455/auth/callback", "host")
            with self.assertRaises(setup.SetupError):
                setup.consume_callback(attempt, {**self.callback(), "state": attempt["state"], **change})
        self.attempt["consumed"] = False
        self.attempt["created_at"] -= 301
        with self.assertRaises(setup.SetupError):
            setup.consume_callback(self.attempt, self.callback())

    def test_exchange_uses_issued_client_and_validates_signed_identity(self):
        with self.client() as client:
            record = setup.exchange_registration(client, self.attempt, self.callback())
        self.assertEqual(record["subject"], "test-owner")
        self.assertEqual(record["client_id"], "oaiapp_test-issued")
        self.assertIn("chatgpt.tokens.use.direct", record["scopes"])
        request = self.requests[0]
        parameters = parse_qs(request.content.decode())
        self.assertEqual(parameters["client_id"], ["oaiapp_test-issued"])
        self.assertEqual(parameters["redirect_uri"], [self.attempt["redirect_uri"]])
        self.assertEqual(parameters["resource"], [setup.RESOURCE])
        self.assertEqual(parameters["code_verifier"], [self.attempt["verifier"]])
        self.assertNotIn("client_secret", parameters)

    def test_invalid_signature_issuer_audience_expiry_and_nonce_are_rejected(self):
        for changes in ({"iss": "https://attacker.invalid"}, {"aud": "wrong-client"},
                        {"exp": int(time.time()) - 100}, {"nonce": "wrong-nonce"}):
            with self.subTest(changes=changes):
                with self.client(token=self.token(**changes)) as client:
                    with self.assertRaises(setup.SetupError):
                        setup.validate_identity(client, self.token(**changes), "oaiapp_test-issued", self.attempt["nonce"])
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode(self.claims(), other_key, algorithm="RS256", headers={"kid": "test-key"})
        with self.client() as client:
            with self.assertRaises(setup.SetupError):
                setup.validate_identity(client, forged, "oaiapp_test-issued", self.attempt["nonce"])

    def test_returning_flow_keeps_client_and_refuses_different_identity(self):
        existing = {"issuer": setup.ISSUER, "subject": "another-owner", "client_id": "oaiapp_test-issued", "id_token": "TEST_OLD_ID"}
        self.attempt = setup.transaction("http://127.0.0.1:1455/auth/callback", "host", existing)
        parameters = parse_qs(urlsplit(setup.authorization_url(self.attempt, existing)).query)
        self.assertNotIn("agent_name_hint", parameters)
        self.assertEqual(parameters["client_id"], [existing["client_id"]])
        with self.client() as client:
            with self.assertRaises(setup.SetupError):
                setup.exchange_registration(client, self.attempt, self.callback(), existing)

    def test_identity_only_consent_does_not_produce_inference_registration(self):
        with self.client(scope="openid email") as client:
            with self.assertRaises(setup.SetupError):
                setup.exchange_registration(client, self.attempt, self.callback())
        self.assertFalse(self.output.exists())

    def test_protected_save_does_not_overwrite_without_explicit_replace(self):
        data = {"issuer": setup.ISSUER, "subject": "test-owner", "client_id": "oaiapp_test-issued"}
        setup.save_registration(self.output, data)
        self.assertEqual(os.stat(self.output).st_mode & 0o777, 0o600)
        with self.assertRaises(setup.SetupError):
            setup.save_registration(self.output, {"new": "data"})
        self.assertEqual(json.loads(self.output.read_text()), data)
        with self.assertRaises(setup.SetupError):
            setup.load_existing(self.output)
        self.assertEqual(setup.load_existing(self.output, replace=True), data)
        self.assertEqual(list(self.output.parent.glob(".siwc-*")), [])

    def test_host_id_is_preserved_and_tokens_cannot_be_saved_to_repo_or_codex_auth(self):
        host = setup.prepare_host(self.output)
        self.assertEqual(host, setup.prepare_host(self.output))
        for bad in (setup.REPOSITORY_ROOT / "unsafe-credentials.json", self.output.parent / "auth.json"):
            with self.assertRaises(setup.SetupError):
                setup.save_registration(bad, {})

    def test_console_success_never_displays_tokens_or_authorization_url(self):
        safe = {"path": str(self.output), "email": "owner@example.com", "scopes": ["openid"]}
        capture = io.StringIO()
        with patch.object(setup, "connect", return_value=safe), redirect_stdout(capture):
            self.assertEqual(setup.main(["--output", str(self.output)]), 0)
        self.assertIn("owner@example.com", capture.getvalue())
        self.assertNotIn("TEST_ACCESS", capture.getvalue())
        self.assertNotIn("auth.openai.com", capture.getvalue())

    def test_console_error_is_sanitized(self):
        capture = io.StringIO()
        with patch.object(setup, "connect", side_effect=setup.SetupError("Pareamento indisponível.")), redirect_stderr(capture):
            self.assertEqual(setup.main([]), 1)
        self.assertEqual(capture.getvalue().strip(), "Pareamento indisponível.")

    def test_local_listener_exists_before_browser_and_callback_is_processed(self):
        opened = {}
        record = {"issuer": setup.ISSUER, "subject": "test-owner", "client_id": "oaiapp_test-issued",
                  "email": "owner@example.com", "scopes": setup.SCOPES.split()}
        class FakeServer:
            def __init__(self, address, handler):
                self.server_port = 15432
                self.handler = handler
                self.bound = address
                opened["bound"] = address
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def handle_request(self):
                handler = self.handler.__new__(self.handler)
                values = opened["parameters"]
                handler.path = "/auth/callback?" + setup.urlencode({"state": values["state"][0], "code": "TEST_CODE", "client_id": "oaiapp_test-issued"})
                handler.wfile = io.BytesIO()
                handler.send_response = lambda *_: None
                handler.send_header = lambda *_: None
                handler.end_headers = lambda: None
                handler.do_GET()
        def browser(url, **_):
            self.assertEqual(opened["bound"], ("127.0.0.1", 0))
            opened["parameters"] = parse_qs(urlsplit(url).query)
            return True
        with patch.object(setup, "HTTPServer", FakeServer), patch.object(setup, "exchange_registration", return_value=record) as exchange:
            result = setup.connect(self.output, client=object(), browser_open=browser)
        self.assertEqual(result["email"], "owner@example.com")
        self.assertEqual(exchange.call_args.args[1]["redirect_uri"], "http://127.0.0.1:15432/auth/callback")
        self.assertTrue(self.output.exists())

    def test_callback_timeout_does_not_exchange_or_save_credentials(self):
        server = unittest.mock.MagicMock()
        server.__enter__.return_value = server
        server.server_port = 15432
        with patch.object(setup, "HTTPServer", return_value=server), patch.object(setup, "exchange_registration") as exchange:
            with patch.object(setup.time, "monotonic", side_effect=[0, 0, 301]):
                with self.assertRaises(setup.SetupError) as caught:
                    setup.connect(self.output, client=object(), browser_open=lambda *_, **__: True)
        self.assertIn("cinco minutos", str(caught.exception))
        exchange.assert_not_called()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
