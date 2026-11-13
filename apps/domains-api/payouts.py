"""Mercado Pago Payouts transport. Not connected to checkout or the order worker yet.

Keep disabled until the registrar supplies a destination that credits this reseller
automatically, and the durable funding/reconciliation workflow is implemented.
"""
import base64
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import UnsupportedAlgorithm

from providers import ProviderError


class PayoutNotReady(ProviderError):
    pass


class PayoutUncertain(ProviderError):
    """A write may have reached the provider. Reconcile before any further write."""


@dataclass(frozen=True)
class PayoutConfig:
    token: str = field(default='', repr=False)
    account_id: str = ''
    mode: str = 'disabled'
    pix_type: str = ''
    pix_key: str = field(default='', repr=False)
    max_cents: int = 0
    signing_key_file: str = field(default='', repr=False)
    recipient_verified: bool = False
    live_authorized: bool = False

    @classmethod
    def from_env(cls):
        # Separate credentials prevent accidentally using the checkout's live token in tests.
        return cls(token=os.getenv('MERCADOPAGO_PAYOUTS_ACCESS_TOKEN', ''),
                   account_id=os.getenv('MERCADOPAGO_PAYOUTS_ACCOUNT_ID', ''),
                   mode=os.getenv('DOMAINS_PAYOUTS_MODE', 'disabled'),
                   pix_type=os.getenv('DOMAIN_FUNDING_PIX_TYPE', ''),
                   pix_key=os.getenv('DOMAIN_FUNDING_PIX_KEY', ''),
                   max_cents=int(os.getenv('DOMAIN_FUNDING_MAX_CENTS', '0')),
                   signing_key_file=os.getenv('MERCADOPAGO_PAYOUTS_SIGNING_KEY_FILE', ''),
                   recipient_verified=os.getenv('DOMAIN_FUNDING_RECIPIENT_VERIFIED') == 'true',
                   live_authorized=os.getenv('DOMAINS_PAYOUTS_LIVE_AUTHORIZED') == 'true')


class Payouts:
    def __init__(self, config, transport=None):
        self.config = config
        self.transport = transport

    def _validate(self):
        c = self.config
        if (c.mode not in {'sandbox', 'production'} or not c.token or not c.account_id.isdigit()
                or c.pix_type not in {'EMAIL', 'PHONE', 'CPF', 'CNPJ', 'PIX_CODE'}
                or not c.pix_key or not c.recipient_verified
                or type(c.max_cents) is not int or c.max_cents <= 0):
            raise PayoutNotReady('Transferência não configurada e validada.')
        if c.mode == 'production' and (not c.live_authorized or not c.signing_key_file):
            raise PayoutNotReady('Transferências reais não estão autorizadas e configuradas.')

    def _sign(self, body):
        try:
            path = Path(self.config.signing_key_file)
            if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ValueError('unsafe permissions')
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError('wrong key type')
            return base64.b64encode(key.sign(body)).decode('ascii')
        except (OSError, ValueError, TypeError, UnsupportedAlgorithm):
            raise PayoutNotReady('Confira a chave privada Ed25519 e suas permissões.') from None

    def _request(self, method, path, body=None, reference=None):
        c = self.config
        headers = {'Authorization': 'Bearer ' + c.token}
        if c.mode == 'sandbox':
            headers.update({'X-test-token': 'true', 'X-enforce-signature': 'false'})
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'X-Idempotency-Key': reference})
            if c.mode == 'production':
                headers.update({'X-test-token': 'false', 'X-enforce-signature': 'true',
                                'X-signature': self._sign(body)})
        try:
            with httpx.Client(timeout=25, follow_redirects=False, transport=self.transport) as client:
                response = client.request(method, 'https://api.mercadopago.com' + path,
                                          headers=headers, content=body)
                # An accepted request is not a completed transfer; callers must query its status.
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            error = PayoutUncertain if method == 'POST' else ProviderError
            raise error('Transferência não confirmada. Confira a operação antes de reenviar.') from None

    def create(self, reference, amount_cents):
        self._validate()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', reference):
            raise ValueError('Use uma referência estável sem dados pessoais.')
        if type(amount_cents) is not int or not 100 <= amount_cents <= self.config.max_cents:
            raise ValueError('Valor fora do limite de transferência autorizado.')
        # Validate the account/environment before any outgoing-money request.
        account = self._request('GET', '/users/me')
        if not isinstance(account, dict):
            raise PayoutNotReady('Não foi possível validar a conta de transferências.')
        tags = account.get('tags')
        if (str(account.get('id')) != self.config.account_id or not isinstance(tags, list)
                or ('test_user' in tags) != (self.config.mode == 'sandbox')):
            raise PayoutNotReady('A credencial não corresponde à conta e ao ambiente configurados.')
        body = json.dumps({
            'external_reference': reference,
            'description': 'Domain registrar funding',
            'transactions': [{
                'external_reference': reference, 'description': 'Domain registrar funding',
                'type': 'pix', 'pix': {'type': self.config.pix_type, 'chave': self.config.pix_key},
                'amount': {'currency': 'BRL', 'value': amount_cents / 100},
            }],
        }, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
        data = self._request('POST', '/v1/payouts', body, reference)
        if not isinstance(data, dict) or not self._valid_id(data.get('id')):
            raise PayoutUncertain('O provedor não confirmou o identificador. Não reenvie a transferência.')
        return {'id': data['id'], 'status': data.get('status', 'created')}

    @staticmethod
    def _valid_id(value):
        return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value))

    def transaction(self, payout_id, transaction_id):
        self._validate()
        if not self._valid_id(payout_id) or not self._valid_id(transaction_id):
            raise ValueError('Identificador inválido.')
        data = self._request('GET', f'/v1/payouts/{payout_id}/transactions/{transaction_id}')
        return {key: data.get(key) for key in ('id', 'status', 'status_detail')}
