"""ResellerClub HTTP API and Mercado Pago Checkout Pro. No secrets in logs/errors."""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from urllib.parse import urlparse

import httpx


class ProviderError(Exception):
    pass


class Rejected(ProviderError):
    """Provider explicitly refused an operation; distinct from uncertain transport failure."""


class Registrar:
    def __init__(self, settings):
        self.settings = settings
        self.base = 'https://httpapi.com/api/' if settings.live else 'https://test.httpapi.com/api/'

    def call(self, path, params, method='GET'):
        params = {'auth-userid': self.settings.reseller_id, 'api-key': self.settings.reseller_key, **params}
        try:
            with httpx.Client(timeout=25) as client:
                response = client.request(method, self.base + path + '.json',
                                          **({'params': params} if method == 'GET' else {'data': params}))
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            raise ProviderError('O fornecedor não confirmou a operação. Tente novamente mais tarde.') from None
        if isinstance(data, dict) and str(data.get('status', '')).upper() == 'ERROR':
            raise Rejected('O fornecedor não autorizou a operação. Entre em contato com o suporte.')
        return data

    def availability(self, label, tlds):
        data = self.call('domains/available', {'domain-name': label, 'tlds': tlds})
        result = []
        for tld in tlds:
            domain = f'{label}.{tld}'
            item = data.get(domain, {}) if isinstance(data, dict) else {}
            special = bool(item.get('costHash') or item.get('tm-claims-key'))
            status = item.get('status', 'unknown')
            result.append({'domain': domain, 'available': status == 'available' and not special,
                           'status': 'special' if special else status})
        return result

    def customer(self, contact, email):
        return str(self.call('customers/v2/signup', {
            **self.contact_fields(contact), 'username': email, 'passwd': secrets.token_urlsafe(24) + 'Aa1!',
            'lang-pref': 'pt', 'accept-policy': 'true', 'marketing-email-consent': 'false'}, 'POST'))

    @staticmethod
    def contact_fields(contact):
        return {'name': contact['name'], 'company': contact['company'] or 'N/A',
                'address-line-1': contact['address'], 'city': contact['city'], 'state': contact['state'],
                'country': 'BR', 'zipcode': contact['zipcode'], 'phone-cc': '55', 'phone': contact['phone']}

    def contact(self, contact, email, customer_id, kind='Contact'):
        fields = {**self.contact_fields(contact), 'email': email, 'customer-id': customer_id, 'type': kind}
        if kind == 'BrOrgContact':
            fields.update({'attr-name1': 'organisationId', 'attr-value1': contact['document']})
        return str(self.call('contacts/add', fields, 'POST'))

    def register(self, order):
        return self.call('domains/register', {
            'domain-name': order['domain'], 'years': 1, 'ns': json.loads(order['nameservers']),
            'customer-id': order['customer_id'], 'reg-contact-id': order['contact_id'],
            'admin-contact-id': order['admin_contact_id'], 'tech-contact-id': order['admin_contact_id'],
            'billing-contact-id': order['admin_contact_id'], 'invoice-option': 'NoInvoice',
            'purchase-privacy': 'false', 'auto-renew': 'false'}, 'POST')

    def details(self, order):
        return self.call('domains/details', {'order-id': order['registrar_order_id'], 'options': 'All'})


class Payments:
    def __init__(self, settings):
        self.settings = settings

    def call(self, method, path, body=None, key=None):
        headers = {'Authorization': 'Bearer ' + self.settings.mp_token}
        if key:
            headers['X-Idempotency-Key'] = key
        try:
            with httpx.Client(timeout=25) as client:
                response = client.request(method, 'https://api.mercadopago.com' + path,
                                          headers=headers, json=body)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise ProviderError('Não foi possível confirmar a operação de pagamento.') from None

    def checkout(self, order, email):
        return_url = self.settings.origin + '/dominios/?pedido=' + order['id']
        body = {
            'items': [{'id': order['id'], 'title': order['domain'] + ' — registro por 1 ano',
                       'quantity': 1, 'currency_id': 'BRL', 'unit_price': order['amount'] / 100}],
            'payer': {'email': email}, 'external_reference': order['id'],
            'metadata': {'domain_order_id': order['id']},
            'payment_methods': {'installments': 5, 'excluded_payment_types': [{'id': 'ticket'}]},
            'back_urls': {status: return_url for status in ('success', 'pending', 'failure')},
            'auto_return': 'approved',
            'notification_url': self.settings.origin + '/api/domains/webhooks/mercadopago',
            'expires': True,
            'expiration_date_to': (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        }
        data = self.call('POST', '/checkout/preferences', body, order['id'])
        url = data.get('init_point' if self.settings.live else 'sandbox_init_point', '')
        if urlparse(url).scheme != 'https' or urlparse(url).hostname not in {'www.mercadopago.com.br', 'sandbox.mercadopago.com.br'}:
            raise ProviderError('O pagamento não retornou um endereço válido.')
        return {'id': str(data['id']), 'url': url}

    def payment(self, payment_id):
        return self.call('GET', '/v1/payments/' + payment_id)

    def refund(self, payment_id):
        return self.call('POST', f'/v1/payments/{payment_id}/refunds', {}, 'domain-refund-' + payment_id)

    def valid_signature(self, payment_id, request_id, signature):
        try:
            values = dict(piece.strip().split('=', 1) for piece in signature.split(','))
            timestamp = int(values['ts'])
            seconds = timestamp / 1000 if timestamp > 10**12 else timestamp
            if not self.settings.mp_secret or not request_id or abs(time.time() - seconds) > 600:
                return False
            message = f"id:{payment_id.lower()};request-id:{request_id};ts:{values['ts']};"
            expected = hmac.new(self.settings.mp_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, values['v1'])
        except (ValueError, KeyError):
            return False

    def matches(self, payment, order):
        try:
            return (payment['currency_id'] == 'BRL'
                    and Decimal(str(payment['transaction_amount'])) == Decimal(order['amount']) / 100
                    and str(payment['collector_id']) == self.settings.mp_collector
                    and payment['live_mode'] is self.settings.live
                    and payment['external_reference'] == order['id']
                    and payment.get('metadata', {}).get('domain_order_id') == order['id'])
        except (KeyError, ValueError, TypeError):
            return False
