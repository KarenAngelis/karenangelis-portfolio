import hashlib
import hmac
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient

from config import Settings
from main import create_app
from models import split_domain, valid_document
from providers import Registrar, Payments, ProviderError, Rejected
from security import password_hash, digest, issue_token
from service import accept_payment, process_order, tick
from storage import Store


class FakeRegistrar:
    def __init__(self):
        self.register_calls = 0
        self.available = True
        self.unknown = False
        self.failure = None
        self.active = True

    def availability(self, label, tlds):
        return [{'domain': label + '.' + tld, 'available': self.available and not self.unknown,
                 'status': 'unknown' if self.unknown else 'available' if self.available else 'regthroughothers'} for tld in tlds]

    def customer(self, *args): return '123'
    def contact(self, *args): return '456'

    def register(self, order):
        self.register_calls += 1
        if self.failure: raise self.failure('Provider failed')
        return {'entityid': '789', 'actionstatus': 'Pending'}

    def details(self, order):
        return {'domainname': order['domain'], 'customerid': order['customer_id'],
                'currentstatus': 'Active' if self.active else 'InActive', 'endtime': int(time.time())+31536000}


class FakePayments(Payments):
    def __init__(self, settings):
        super().__init__(settings)
        self.current = None
        self.checkouts = 0
        self.refunds = []

    def checkout(self, order, email):
        self.checkouts += 1
        self.current = {'id': 12345, 'status':'approved', 'currency_id':'BRL',
                        'transaction_amount': order['amount']/100, 'collector_id': '42', 'live_mode':False,
                        'external_reference':order['id'], 'metadata':{'domain_order_id':order['id']}}
        return {'id':'pref1','url':'https://sandbox.mercadopago.com.br/checkout/v1/redirect?pref_id=pref1'}

    def payment(self, payment_id): return {**self.current, 'id': int(payment_id)}
    def refund(self, payment_id): self.refunds.append(payment_id); return {'status':'approved'}


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(db=self.temp.name+'/test.sqlite3', origin='https://testserver',
                                 enabled=True, live=False, reseller_id='1', reseller_key='test',
                                 mp_token='test', mp_secret='secret-test', mp_collector='42',
                                 nameservers=['ns1.example.com','ns2.example.com'],
                                 prices={'com':{'register':7500,'renew':8500},'com.br':{'register':7500,'renew':7500}},
                                 smtp_host='smtp.example.com', smtp_user='test', smtp_password='test',mail_from='test@example.com')
        self.store = Store(self.settings.db)
        self.registrar = FakeRegistrar()
        self.payments = FakePayments(self.settings)
        self.client = TestClient(create_app(self.settings,self.store,self.registrar,self.payments,worker=False), base_url='https://testserver')
        self.store.execute('INSERT INTO users(id,email,password,verified) VALUES(?,?,?,1)', ('user','owner@example.com',password_hash('long-password-123')))
        self.client.cookies.set('ka_domain_session','session-test')
        self.store.execute('INSERT INTO sessions VALUES(?,?,?)',(digest('session-test'),'user',int(time.time())+3600))
        self.contact = {'name':'Nome de Teste','company':'','document':'52998224725','address':'Rua de Teste 123',
                        'city':'Joinville','state':'SC','zipcode':'89200000','phone':'47999998888'}

    def tearDown(self): self.client.close(); self.temp.cleanup()

    def post(self,path,data=None,**headers):
        return self.client.post('/api/domains'+path,json=data or {},headers={'Origin':self.settings.origin,**headers})

    def checkout(self):
        result = self.client.get('/api/domains/search?q=exampletest.com').json()['results'][0]
        self.body = {'quote_id':result['quote_id'],'registrant':self.contact,'accepted_terms':True}
        response = self.post('/checkout', self.body, **{'Idempotency-Key':'purchase-key-123456'})
        self.assertEqual(response.status_code,200,response.text)
        return self.store.one('SELECT * FROM orders WHERE id=?',(response.json()['order_id'],))

    def paid(self):
        order = self.checkout()
        accept_payment(self.store,self.payments,'12345')
        return self.store.one('SELECT * FROM orders WHERE id=?',(order['id'],))

    def test_search_returns_only_provider_availability(self):
        self.registrar.unknown=True
        data=self.client.get('/api/domains/search?q=exampletest').json()
        self.assertTrue(all(not item['available'] and 'quote_id' not in item for item in data['results']))

    def test_domain_validation(self):
        self.assertEqual(split_domain('Example.COM.BR',self.settings.prices),('example',['com.br']))
        for domain in ['https://evil.com','a.com/','a.xyz','-a.com','www.a.com','a..com','ação.com']:
            with self.assertRaises(ValueError): split_domain(domain,self.settings.prices)

    def test_document_validation(self):
        self.assertTrue(valid_document('529.982.247-25'))
        self.assertFalse(valid_document('11111111111'))
        self.assertFalse(valid_document('52998224726'))

    def test_unconfigured_store_fails_closed(self):
        self.settings.reseller_key=''
        self.assertFalse(self.client.get('/api/domains/config').json()['sales_ready'])
        self.assertEqual(self.client.get('/api/domains/search?q=example').status_code,503)
        self.assertEqual(self.post('/checkout', {'quote_id':'a'*24,'registrant':self.contact,'accepted_terms':True}, **{'Idempotency-Key':'purchase-key-123456'}).status_code,503)
        self.assertEqual(self.payments.checkouts,0)

    def test_checkout_rejects_client_price(self):
        self.checkout()
        response=self.post('/checkout',{**self.body,'amount':1},**{'Idempotency-Key':'another-key-123456'})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(self.contact['document'],response.text)

    def test_expired_quote_and_changed_price(self):
        result=self.client.get('/api/domains/search?q=exampletest.com').json()['results'][0]
        body={'quote_id':result['quote_id'],'registrant':self.contact,'accepted_terms':True}
        self.settings.prices['com']['register']=9900
        self.assertEqual(self.post('/checkout',body,**{'Idempotency-Key':'purchase-key-123456'}).status_code,409)
        self.store.execute('UPDATE quotes SET expires=0')
        self.assertEqual(self.post('/checkout',body,**{'Idempotency-Key':'purchase-key-123456'}).status_code,409)

    def test_checkout_idempotency(self):
        order=self.checkout()
        result=self.post('/checkout',self.body,**{'Idempotency-Key':'purchase-key-123456'})
        self.assertEqual(result.json()['order_id'],order['id'])
        self.assertEqual(self.payments.checkouts,1)
        self.assertEqual(self.post('/checkout',self.body,**{'Idempotency-Key':'another-key-123456'}).status_code,409)

    def test_csrf_and_unauthenticated_checkout(self):
        self.assertEqual(self.client.post('/api/domains/auth/logout',json={}).status_code,403)
        self.client.cookies.clear()
        self.assertEqual(self.post('/checkout',{'quote_id':'a'*24,'registrant':self.contact,'accepted_terms':True},**{'Idempotency-Key':'purchase-key-123456'}).status_code,401)

    def test_ownership_is_enforced(self):
        self.checkout()
        self.store.execute('INSERT INTO users(id,email,verified) VALUES(?,?,1)',('other','other@example.com'))
        self.store.execute('UPDATE sessions SET user_id=?',('other',))
        self.assertEqual(self.client.get('/api/domains/orders').json()['orders'],[])

    def test_signed_webhook_amount_and_mode_validation(self):
        order=self.checkout(); ts=str(int(time.time()*1000)); rid='request-1'
        signature=hmac.new(b'secret-test',f'id:12345;request-id:{rid};ts:{ts};'.encode(),hashlib.sha256).hexdigest()
        headers={'x-signature':f'ts={ts},v1={signature}','x-request-id':rid}
        path='/api/domains/webhooks/mercadopago?data.id=12345'
        self.assertEqual(self.client.post(path,json={}).status_code,401)
        for key,value in [('transaction_amount',1),('currency_id','USD'),('collector_id',999),('live_mode',True)]:
            original=self.payments.current[key]; self.payments.current[key]=value
            self.assertEqual(self.client.post(path,json={},headers=headers).status_code,400)
            self.payments.current[key]=original
        self.assertEqual(self.client.post(path,json={},headers=headers).status_code,200)
        self.assertEqual(self.store.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status'],'paid')

    def test_duplicate_webhook_and_worker_register_once(self):
        order=self.paid()
        accept_payment(self.store,self.payments,'12345')
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _:process_order(self.store,self.registrar,self.payments,order),range(2)))
        self.assertEqual(self.registrar.register_calls,1)
        pending=self.store.one('SELECT * FROM orders WHERE id=?',(order['id'],))
        self.assertEqual(pending['status'],'registration_pending')
        process_order(self.store,self.registrar,self.payments,pending)
        self.assertEqual(self.store.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status'],'active')

    def test_unknown_registration_is_not_retried_or_refunded(self):
        order=self.paid(); self.registrar.failure=ProviderError
        process_order(self.store,self.registrar,self.payments,order)
        tick(self.store,self.registrar,self.payments)
        self.assertEqual(self.registrar.register_calls,1)
        self.assertEqual(self.payments.refunds,[])
        self.assertEqual(self.store.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status'],'review_required')

    def test_definite_failure_refunds(self):
        order=self.paid(); self.registrar.failure=Rejected
        process_order(self.store,self.registrar,self.payments,order)
        tick(self.store,self.registrar,self.payments)
        self.assertEqual(self.payments.refunds,['12345'])
        self.assertEqual(self.store.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status'],'refunded')

    def test_availability_race_refunds_without_registering(self):
        order=self.paid(); self.registrar.available=False
        process_order(self.store,self.registrar,self.payments,order); tick(self.store,self.registrar,self.payments)
        self.assertEqual(self.registrar.register_calls,0)
        self.assertEqual(self.payments.refunds,['12345'])

    def test_unknown_availability_does_not_register(self):
        order=self.paid(); self.registrar.unknown=True
        process_order(self.store,self.registrar,self.payments,order)
        self.assertEqual(self.registrar.register_calls,0)
        self.assertEqual(self.payments.refunds,[])

    def test_duplicate_payment_refunded_without_second_registration(self):
        order=self.paid(); accept_payment(self.store,self.payments,'67890')
        tick(self.store,self.registrar,self.payments)
        self.assertEqual(self.registrar.register_calls,1)
        self.assertIn('67890',self.payments.refunds)

    def test_late_payment_for_expired_order_refunds(self):
        order=self.checkout(); self.store.update_order(order['id'],status='expired')
        accept_payment(self.store,self.payments,'12345'); tick(self.store,self.registrar,self.payments)
        self.assertEqual(self.registrar.register_calls,0)
        self.assertEqual(self.payments.refunds,['12345'])

    def test_chargeback_does_not_release_registered_domain(self):
        order=self.paid(); self.store.update_order(order['id'],status='active')
        self.payments.current['status']='charged_back'; accept_payment(self.store,self.payments,'12345')
        self.assertEqual(self.store.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status'],'review_required')

    def test_interrupted_registration_never_replays(self):
        order=self.paid(); self.store.execute("UPDATE orders SET status='registering',updated=0 WHERE id=?",(order['id'],))
        tick(self.store,self.registrar,self.payments)
        self.assertEqual(self.registrar.register_calls,0)
        self.assertEqual(self.store.one('SELECT status FROM orders WHERE id=?',(order['id'],))['status'],'review_required')

    def test_chargeback_during_registration_cannot_be_overwritten(self):
        order=self.paid()
        def register_and_chargeback(_):
            self.payments.current['status']='charged_back'
            accept_payment(self.store,self.payments,'12345')
            return {'entityid':'789'}
        with patch.object(self.registrar,'register',side_effect=register_and_chargeback):
            process_order(self.store,self.registrar,self.payments,order)
        updated=self.store.one('SELECT * FROM orders WHERE id=?',(order['id'],))
        self.assertEqual(updated['status'],'review_required')
        self.assertEqual(updated['registrar_order_id'],'789')

    def test_nameservers_are_preserved_per_order(self):
        order=self.checkout()
        self.settings.nameservers=['ns3.example.com','ns4.example.com']
        self.store.update_order(order['id'],status='active')
        self.assertEqual(self.client.get('/api/domains/orders').json()['orders'][0]['nameservers'],['ns1.example.com','ns2.example.com'])

    def test_paused_sales_can_still_process_paid_orders(self):
        self.settings.enabled=False
        self.assertFalse(self.settings.sales_ready)
        self.assertTrue(self.settings.processing_ready)

    def test_password_reset_is_one_use_and_invalidates_sessions(self):
        token=issue_token(self.store,'user','reset')
        self.assertEqual(self.post('/auth/reset',{'token':token,'password':'new-long-password-123'}).status_code,200)
        self.assertEqual(self.client.get('/api/domains/me').status_code,401)
        self.assertEqual(self.post('/auth/reset',{'token':token,'password':'new-long-password-123'}).status_code,400)
        self.assertEqual(self.post('/auth/login',{'email':'owner@example.com','password':'new-long-password-123'}).status_code,200)

    def test_registration_does_not_allow_unverified_login(self):
        with patch('main.send_account_mail'):
            self.assertEqual(self.post('/auth/register',{'email':'new@example.com','password':'new-long-password-123'}).status_code,200)
        response=self.post('/auth/login',{'email':'new@example.com','password':'new-long-password-123'})
        self.assertEqual(response.status_code,403)

    def test_session_cookie_is_secure_and_http_only(self):
        response=self.post('/auth/login',{'email':'owner@example.com','password':'long-password-123'})
        cookie=response.headers['set-cookie']
        for value in ['HttpOnly','Secure','SameSite=lax']: self.assertIn(value,cookie)

    def test_google_does_not_link_existing_email(self):
        self.settings.google_id='test-client'
        nonce=self.post('/auth/google/nonce').json()['nonce']
        payload={'sub':'google-user','email':'owner@example.com','email_verified':True,'nonce':nonce}
        with patch('google.oauth2.id_token.verify_oauth2_token',return_value=payload):
            response=self.post('/auth/google',{'credential':'a'*30})
        self.assertEqual(response.status_code,409)

    def test_google_nonce_cannot_be_replayed(self):
        self.settings.google_id='test-client'
        nonce=self.post('/auth/google/nonce').json()['nonce']
        payload={'sub':'google-user','email':'new@gmail.com','email_verified':True,'nonce':nonce}
        with patch('google.oauth2.id_token.verify_oauth2_token',return_value=payload):
            self.assertEqual(self.post('/auth/google',{'credential':'a'*30}).status_code,200)
            self.assertEqual(self.post('/auth/google',{'credential':'a'*30}).status_code,401)

    def test_rate_limit_survives_app_restart(self):
        for _ in range(10): self.store.allow('login:testclient',10,900)
        second=Store(self.settings.db)
        self.assertFalse(second.allow('login:testclient',10,900))

    def test_provider_filters_premium_and_trademark_domains(self):
        registrar=Registrar(self.settings)
        with patch.object(registrar,'call',return_value={'a.com':{'status':'available','costHash':{'create':10000}},'a.com.br':{'status':'available','tm-claims-key':'key'}}):
            self.assertTrue(all(not result['available'] for result in registrar.availability('a',['com','com.br'])))

    def test_provider_br_contact_mapping(self):
        registrar=Registrar(self.settings)
        with patch.object(registrar,'call',return_value=123) as call:
            registrar.contact(self.contact,'owner@example.com','customer','BrOrgContact')
            params=call.call_args.args[1]
            self.assertEqual(params['attr-name1'],'organisationId')
            self.assertEqual(params['attr-value1'],self.contact['document'])
            registrar.contact(self.contact,'owner@example.com','customer','BrContact')
            self.assertNotIn('attr-name1',call.call_args.args[1])

    def test_checkout_gateway_contract(self):
        order=self.checkout(); payments=Payments(self.settings)
        with patch.object(payments,'call',return_value={'id':'1','sandbox_init_point':'https://sandbox.mercadopago.com.br/checkout/v1/redirect'}) as call:
            payments.checkout(order,'owner@example.com')
            body=call.call_args.args[2]
            self.assertEqual(body['payment_methods']['installments'],5)
            self.assertEqual(body['items'][0]['unit_price'],75)
            self.assertEqual(body['items'][0]['currency_id'],'BRL')

    def test_signature_rejects_stale_and_invalid_notifications(self):
        self.assertFalse(self.payments.valid_signature('123','request','ts=1,v1=anything'))
        self.assertFalse(self.payments.valid_signature('123','request','garbage'))


if __name__ == '__main__': unittest.main()
