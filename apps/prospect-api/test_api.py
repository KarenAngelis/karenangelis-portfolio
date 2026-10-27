import os
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
import core
from main import app
from mailer import send_one

class ProspectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'PROSPECT_DB':self.tmp.name+'/test.sqlite3',
            'PROSPECT_ADMIN_TOKEN':'a'*32,'UNSUBSCRIBE_SECRET':'b'*32,'PUBLIC_BASE_URL':'https://example.com',
            'CASA_DADOS_API_KEY':'test','SEND_ENABLED':'false','SEND_DAILY_LIMIT':'100',
            'SMTP_FROM':'karen@example.com','COLLECT_ENABLED':'false'})
        self.env.start()
        self.client=TestClient(app).__enter__()
        self.headers={'Authorization':'Bearer '+'a'*32}
        self.day=(core.today()-timedelta(days=1)).isoformat()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
    def company(self,cnpj='69768568000153',name='Empresa <teste>'):
        r=self.client.post('/api/prospect/companies',headers=self.headers,json={'cnpj':cnpj,'name':name,'opened':self.day,'source':'fixture'})
        self.assertEqual(r.status_code,200)
        return cnpj
    def contact(self,cnpj,email='hello@example.com'):
        return self.client.put('/api/prospect/companies/'+cnpj+'/contact',headers=self.headers,json={'email':email,'verified':True})
    def queued(self):
        c=self.company();self.contact(c)
        self.assertEqual(self.client.post('/api/prospect/companies/'+c+'/queue',headers=self.headers).status_code,200)
    def test_auth_fails_closed(self):
        self.assertEqual(self.client.get('/api/prospect/summary').status_code,401)
        with patch.dict(os.environ,{'PROSPECT_ADMIN_TOKEN':''}):
            self.assertEqual(self.client.get('/api/prospect/summary',headers=self.headers).status_code,503)
    def test_dedup_contact_and_render_escape(self):
        self.queued()
        c=self.company('69777657000166');self.contact(c)
        self.assertEqual(self.client.post('/api/prospect/companies/'+c+'/queue',headers=self.headers).status_code,409)
        with core.db() as db:
            row=db.execute('SELECT * FROM messages').fetchone()
            self.assertIn('Empresa &lt;teste&gt;',row['html']);self.assertIn('cid:logo-karen',row['html'])
            self.assertNotIn('[Nome da empresa]',row['html']);self.assertNotIn('{{unsubscribe_url}}',row['html'])
    def test_removal_get_no_mutation_post_cancels_and_tamper_fails(self):
        self.queued();url='/api/prospect/unsubscribe/'+core.token('hello@example.com')
        self.assertEqual(self.client.get(url).status_code,200)
        with core.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM suppression').fetchone()[0],0)
        self.assertEqual(self.client.post(url).status_code,200)
        with core.db() as db:self.assertEqual(db.execute('SELECT status FROM messages').fetchone()[0],'cancelled')
        self.assertEqual(self.client.post(url+'bad').status_code,400)
    def test_disabled_send_and_smtp_acceptance(self):
        self.queued();sent=[]
        self.assertFalse(send_one(sent.append))
        with patch.dict(os.environ,{'SEND_ENABLED':'true'}):self.assertTrue(send_one(sent.append))
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['To'],'hello@example.com')
        with core.db() as db:self.assertEqual(db.execute('SELECT status FROM messages').fetchone()[0],'accepted')
    def test_uncertain_send_never_retried(self):
        self.queued()
        def fail(message):raise TimeoutError()
        with patch.dict(os.environ,{'SEND_ENABLED':'true'}):
            self.assertFalse(send_one(fail));self.assertFalse(send_one(lambda m:self.fail('Duplicate attempt')))
        with core.db() as db:self.assertEqual(db.execute('SELECT status FROM messages').fetchone()[0],'unknown')
    def test_paused_and_limit(self):
        self.queued()
        self.client.post('/api/prospect/control',headers=self.headers,json={'paused':True})
        with patch.dict(os.environ,{'SEND_ENABLED':'true'}):self.assertFalse(send_one(lambda m:self.fail()))
        self.client.post('/api/prospect/control',headers=self.headers,json={'paused':False})
        with patch.dict(os.environ,{'SEND_ENABLED':'true','SEND_DAILY_LIMIT':'0'}):self.assertFalse(send_one(lambda m:self.fail()))
    def test_paginated_collection_resume_dedup_and_no_email_invention(self):
        pages=[]
        def source(request):
            import json
            body=json.loads(request.content);pages.append(body['pagina'])
            self.assertEqual(body['data_abertura']['inicio'],self.day)
            self.assertNotIn('uf',body);self.assertNotIn('mais_filtros',body)
            n=body['pagina'];row={'cnpj':['69768568000153','69777657000166'][n-1],
                'razao_social':'Empresa','data_abertura':self.day}
            return httpx.Response(200,json={'total':2,'cnpjs':[row]})
        self.client.post('/api/prospect/collect',headers=self.headers,json={'start':self.day,'end':self.day})
        with httpx.Client(transport=httpx.MockTransport(source)) as client:
            self.assertTrue(core.collect_page(client));self.assertTrue(core.collect_page(client))
            self.assertFalse(core.collect_page(client))
        self.assertEqual(pages,[1,2])
        with core.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM companies').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT status FROM collections').fetchone()[0],'complete')
            self.assertEqual(db.execute('SELECT count(email) FROM companies').fetchone()[0],0)
    def test_repeated_page_detected(self):
        def source(request):return httpx.Response(200,json={'total':2,'cnpjs':[{'cnpj':'69768568000153','razao_social':'Empresa','data_abertura':self.day}]})
        self.client.post('/api/prospect/collect',headers=self.headers,json={'start':self.day,'end':self.day})
        with httpx.Client(transport=httpx.MockTransport(source)) as client:
            self.assertTrue(core.collect_page(client));self.assertFalse(core.collect_page(client))
        with core.db() as db:self.assertEqual(db.execute('SELECT status FROM collections').fetchone()[0],'error')
    def test_source_failure_preserves_checkpoint(self):
        self.client.post('/api/prospect/collect',headers=self.headers,json={'start':self.day,'end':self.day})
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as client:self.assertFalse(core.collect_page(client))
        with core.db() as db:
            r=db.execute('SELECT * FROM collections').fetchone();self.assertEqual(r['page'],1);self.assertEqual(r['status'],'error')
    def test_export_injection_and_future_date(self):
        self.company(name='=HYPERLINK("bad")')
        text=self.client.get('/api/prospect/export.csv',headers=self.headers).text
        self.assertIn("'=HYPERLINK",text)
        future=(core.today()+timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post('/api/prospect/collect',headers=self.headers,json={'start':future,'end':future}).status_code,422)
    def test_alphanumeric_and_newlines(self):
        self.company('12ABC34501DE35')
        self.assertEqual(self.contact('12ABC34501DE35','a@example.com\nBcc:someone@example.com').status_code,422)

    def test_prior_contact_blocks_queue(self):
        c=self.company();self.contact(c)
        r=self.client.post('/api/prospect/suppressions',headers=self.headers,json={'email':'hello@example.com','reason':'Already sent in Gmail'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.post('/api/prospect/companies/'+c+'/queue',headers=self.headers).status_code,409)
    def test_same_company_new_email_not_sent_twice(self):
        self.queued()
        with patch.dict(os.environ,{'SEND_ENABLED':'true'}):self.assertTrue(send_one(lambda m:None))
        self.assertEqual(self.contact('69768568000153','another@example.com').status_code,200)
        self.assertEqual(self.client.post('/api/prospect/companies/69768568000153/queue',headers=self.headers).status_code,409)
    def test_daily_schedule_catches_up_and_does_not_reset_midday(self):
        with patch.dict(os.environ,{'COLLECT_ENABLED':'true','COLLECT_START_DATE':self.day}):
            core.daily_schedule()
            with core.db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM collections').fetchone()[0],2)
                db.execute('UPDATE collections SET page=4 WHERE day=?',(self.day,))
            core.daily_schedule()
            with core.db() as db:self.assertEqual(db.execute('SELECT page FROM collections WHERE day=?',(self.day,)).fetchone()[0],4)
    def test_collection_transaction_rolls_back_invalid_page(self):
        self.client.post('/api/prospect/collect',headers=self.headers,json={'start':self.day,'end':self.day})
        rows=[{'cnpj':'69768568000153','razao_social':'Valid','data_abertura':self.day},
              {'cnpj':'invalid','razao_social':'Invalid','data_abertura':self.day}]
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'total':2,'cnpjs':rows}))) as client:
            self.assertFalse(core.collect_page(client))
        with core.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM companies').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT page FROM collections').fetchone()[0],1)

if __name__=='__main__':unittest.main()
