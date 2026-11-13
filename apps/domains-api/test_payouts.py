import base64
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from payouts import PayoutConfig, PayoutNotReady, PayoutUncertain, Payouts


class PayoutTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.account = {'id': 42, 'tags': ['test_user']}
        self.config = PayoutConfig(token='test-token', account_id='42', mode='sandbox',
                                   pix_type='EMAIL', pix_key='registrar@example.com',
                                   max_cents=10000, recipient_verified=True)

    def client(self, config=None, outcome=None):
        def handler(request):
            self.requests.append(request)
            if request.url.path == '/users/me':
                return httpx.Response(200, json=self.account)
            if outcome:
                return outcome(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'id': 'TOP123', 'status': 'success',
                                                'status_detail': 'accredited'})
            return httpx.Response(202, json={'id': 'POP123', 'status': 'created'})
        return Payouts(config or self.config, httpx.MockTransport(handler))

    def test_default_disabled_and_checkout_credentials_are_not_reused(self):
        with patch.dict(os.environ, {'MERCADOPAGO_ACCESS_TOKEN': 'live-checkout-token'}, clear=True):
            config = PayoutConfig.from_env()
        self.assertEqual(config.mode, 'disabled')
        self.assertEqual(config.token, '')
        with self.assertRaises(PayoutNotReady): self.client(config).create('order-1', 7900)
        self.assertEqual(self.requests, [])

    def test_sandbox_request_has_test_headers_stable_reference_and_exact_value(self):
        result = self.client().create('order-1', 7901)
        self.assertEqual(result, {'id': 'POP123', 'status': 'created'})
        request = self.requests[-1]
        self.assertEqual(request.headers['x-test-token'], 'true')
        self.assertEqual(request.headers['x-enforce-signature'], 'false')
        self.assertNotIn('x-signature', request.headers)
        self.assertEqual(request.headers['x-idempotency-key'], 'order-1')
        body = json.loads(request.content)
        self.assertEqual(body['external_reference'], 'order-1')
        transaction = body['transactions'][0]
        self.assertEqual(transaction['amount'], {'currency': 'BRL', 'value': 79.01})
        self.assertEqual(transaction['pix'], {'type': 'EMAIL', 'chave': 'registrar@example.com'})
        self.assertEqual(transaction['external_reference'], 'order-1')

    def test_unverified_recipient_cannot_receive_transfers(self):
        with self.assertRaises(PayoutNotReady):
            self.client(replace(self.config, recipient_verified=False)).create('order-1', 7900)
        self.assertEqual(self.requests, [])

    def test_values_and_references_are_checked_before_network_calls(self):
        for amount in (True, 79.0, 99, 0, -1, 10001):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.client().create('order-1', amount)
        for reference in ('', 'a'*51, 'owner@example.com', '../order', 'order 1'):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.client().create(reference, 7900)
        self.assertEqual(self.requests, [])

    def test_wrong_account_or_live_token_is_never_used_for_sandbox_payout(self):
        for account in ({'id': 43, 'tags': ['test_user']}, {'id': 42, 'tags': []}, {'id': 42}):
            self.account = account
            with self.subTest(account=account), self.assertRaises(PayoutNotReady):
                self.client().create('order-1', 7900)
        self.assertTrue(all(request.method == 'GET' for request in self.requests))

    def test_timeout_never_automatically_replays_write_or_leaks_secret(self):
        def timeout(request):
            raise httpx.ReadTimeout('test-token registrar@example.com', request=request)
        with self.assertRaises(PayoutUncertain) as error:
            self.client(outcome=timeout).create('order-1', 7900)
        self.assertEqual(sum(r.method == 'POST' for r in self.requests), 1)
        self.assertNotIn('test-token', str(error.exception))
        self.assertNotIn('registrar@example.com', str(error.exception))

    def test_server_error_and_malformed_accepted_response_require_reconciliation(self):
        for response in (httpx.Response(503, text='private provider error'),
                         httpx.Response(202, json={}), httpx.Response(202, text='invalid json')):
            self.requests.clear()
            with self.subTest(response=response), self.assertRaises(PayoutUncertain):
                self.client(outcome=lambda request: response).create('order-1', 7900)
            self.assertEqual(sum(r.method == 'POST' for r in self.requests), 1)

    def test_redirect_cannot_receive_an_authorization_header(self):
        with self.assertRaises(PayoutUncertain):
            self.client(outcome=lambda request: httpx.Response(307, headers={'Location': 'https://example.com'})).create('order-1', 7900)
        self.assertTrue(all(r.url.host == 'api.mercadopago.com' for r in self.requests))
        self.assertEqual(sum(r.method == 'POST' for r in self.requests), 1)

    def test_production_requires_explicit_authorization_and_signing_key(self):
        self.account = {'id': 42, 'tags': []}
        with self.assertRaises(PayoutNotReady):
            self.client(replace(self.config, mode='production')).create('order-1', 7900)
        self.assertEqual(self.requests, [])

    def test_production_signs_the_exact_transmitted_body(self):
        self.account = {'id': 42, 'tags': []}
        key = Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'private.pem'
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
            path.chmod(0o600)
            config = replace(self.config, mode='production', live_authorized=True, signing_key_file=str(path))
            self.client(config).create('order-1', 7900)
        request = self.requests[-1]
        self.assertEqual(request.headers['x-test-token'], 'false')
        self.assertEqual(request.headers['x-enforce-signature'], 'true')
        key.public_key().verify(base64.b64decode(request.headers['x-signature']), request.content)

    def test_world_readable_private_key_is_rejected_before_any_write(self):
        self.account = {'id': 42, 'tags': []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'private.pem'; path.write_text('not a private key'); path.chmod(0o644)
            config = replace(self.config, mode='production', live_authorized=True, signing_key_file=str(path))
            with self.assertRaises(PayoutNotReady): self.client(config).create('order-1', 7900)
        self.assertTrue(all(request.method == 'GET' for request in self.requests))

    def test_status_is_queried_and_untrusted_ids_cannot_change_api_path(self):
        result = self.client().transaction('POP123', 'TOP123')
        self.assertEqual(result['status_detail'], 'accredited')
        self.assertEqual(self.requests[-1].url.path, '/v1/payouts/POP123/transactions/TOP123')
        self.requests.clear()
        with self.assertRaises(ValueError): self.client().transaction('../users', 'TOP123')
        self.assertEqual(self.requests, [])


if __name__ == '__main__': unittest.main()
