import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import httpx
import direct_sources as direct


SOURCE = {'id':'demo','type':'lever','board':'demo','company':'Demo','url':'https://jobs.lever.co/demo'}
POST = {'id':'123','text':'Fullstack Developer Pleno','descriptionPlain':'React e SQL. Envie currículo para jobs@example.org.',
        'categories':{'location':'Brazil','commitment':'Contract'},'country':'BR','workplaceType':'remote',
        'applyUrl':'https://jobs.lever.co/demo/123/apply','lists':[]}


class FakeSheet:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.events = []
    def history(self): return self.events
    def read_jobs(self): return self.rows
    def append_jobs(self, rows): self.rows.extend(rows)
    def append_history(self, date, uid, event, previous, status, evidence):
        self.events.append([date, uid, 'Backend', event, previous, status, evidence])


class DirectTests(unittest.TestCase):
    def client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)

    def test_lever_pagination_keeps_requirements_and_no_credentials(self):
        def handle(req):
            self.assertNotIn('authorization', req.headers)
            self.assertNotIn('api_key', str(req.url))
            self.assertEqual(req.url.host, 'api.lever.co')
            if req.url.params['skip'] == '0':
                return httpx.Response(200,json=[dict(POST,lists=[{'text':'Requirements','content':'<li>Python</li>'}])])
            return httpx.Response(200,json=[])
        with patch.object(direct,'PAGE_SIZE',1):
            result=direct.fetch_jobs(SOURCE,self.client(handle))
        self.assertEqual(len(result),1)
        self.assertIn('Python',result[0]['description'])

    def test_backend_titles_and_link_only_import(self):
        for title in ('Backend Developer Pleno', 'Back-end Engineer', 'Back End Developer Mid'):
            with self.subTest(title=title):
                post = dict(POST, text=title, descriptionPlain='Python, APIs and PostgreSQL.')
                job = list(direct.parse_jobs(SOURCE, json.dumps([post])))[0]
                row = direct.to_row(SOURCE, job)
                self.assertIsNotNone(row)
                self.assertEqual(row['Canal'], 'Link')
                self.assertEqual(row['Link da candidatura'], POST['applyUrl'])
                self.assertEqual(row['Status'], 'Triagem')
        self.assertFalse(direct.role_matches('Senior Backend Engineer'))
        self.assertFalse(direct.role_matches('Marketing Analyst'))

    def test_rate_limit_is_not_retried(self):
        seen=[]
        def handle(req):
            seen.append(req)
            return httpx.Response(429,text='PRIVATE BODY')
        with self.assertRaisesRegex(direct.SourceError,'HTTP 429'):
            direct.fetch_jobs(SOURCE,self.client(handle))
        self.assertEqual(len(seen),1)

    def test_external_redirect_not_followed(self):
        with self.assertRaisesRegex(direct.SourceError,'Off-host'):
            direct.fetch_jobs(SOURCE,self.client(lambda req:httpx.Response(302,headers={'location':'http://127.0.0.1/secrets'})))

    def test_bad_schema_not_treated_as_empty(self):
        with self.assertRaises(direct.SourceError):
            list(direct.parse_jobs(SOURCE,'{}'))

    def test_one_failure_does_not_block_other_source(self):
        def handle(req):
            return httpx.Response(503) if req.url.path.endswith('/broken') else httpx.Response(200,json=[POST])
        sheet=FakeSheet()
        report=direct.collect_direct(sheet,[dict(SOURCE,id='broken',board='broken'),SOURCE],self.client(handle))
        self.assertIn('error',report[0])
        self.assertEqual(report[1]['imported'],1)
        self.assertEqual(sheet.rows[0]['Status'],'Triagem')
        self.assertNotIn('TRIAGEM APROVADA',sheet.rows[0]['Observações'])

    def test_restart_skips_recent_attempt_and_force_still_deduplicates(self):
        sheet=FakeSheet()
        calls=[]
        def handle(req):
            calls.append(req)
            return httpx.Response(200,json=[POST])
        client=self.client(handle)
        direct.collect_direct(sheet,[SOURCE],client)
        direct.collect_direct(sheet,[SOURCE],client)
        self.assertEqual(len(calls),1)
        direct.collect_direct(sheet,[SOURCE],client,force=True)
        self.assertEqual(len(sheet.rows),1)

    def test_existing_manual_job_not_duplicated(self):
        sheet=FakeSheet([{'ID':'research','Empresa':'Demo','Vaga':POST['text']}])
        direct.collect_direct(sheet,[SOURCE],self.client(lambda r:httpx.Response(200,json=[POST])))
        self.assertEqual(len(sheet.rows),1)

    def test_filter_rejects_senior_and_unrelated_countries(self):
        job=list(direct.parse_jobs(SOURCE,json.dumps([POST])))[0]
        self.assertIsNone(direct.to_row(SOURCE,dict(job,title='Senior Fullstack Engineer')))
        self.assertIsNone(direct.to_row(SOURCE,dict(job,location='United States')))
        self.assertIsNone(direct.to_row(SOURCE,dict(job,workplace='hybrid')))
        self.assertTrue(direct.role_matches('Mid/Senior Frontend Developer'))
        self.assertFalse(direct.role_matches('Fullstack Engineering Manager'))

    def test_countries_and_geographic_uncertainty_preserved(self):
        job=list(direct.parse_jobs(SOURCE,json.dumps([POST])))[0]
        row=direct.to_row(SOURCE,dict(job,location='Italy / Portugal',workplace='remote'))
        self.assertEqual(row['País'],'PT')
        self.assertIn('Italy / Portugal',row['Observações'])
        self.assertIn('contratação a partir do Brasil',row['Observações'])

    def test_privacy_email_is_not_application_channel(self):
        self.assertEqual(direct.email_candidates('Privacy and GDPR: jobs@privacy.example.org'),[])
        job=list(direct.parse_jobs(SOURCE,json.dumps([POST])))[0]
        row=direct.to_row(SOURCE,dict(job,description='React. Privacy: privacy@example.org'))
        self.assertEqual(row['Canal'],'Link')
        self.assertEqual(row['E-mail'],'')

    def test_greenhouse_entities_and_ashby_hidden_posts(self):
        source=dict(SOURCE,type='greenhouse')
        result=list(direct.parse_jobs(source,json.dumps({'jobs':[{'id':1,'title':'Frontend Developer','content':'&lt;p&gt;React&lt;/p&gt;',
                          'location':{'name':'Remote Portugal'},'absolute_url':'https://example.org/job'}]})))
        self.assertEqual(result[0]['description'],'React')
        hidden={'jobs':[{'isListed':False}]}
        self.assertEqual(list(direct.parse_jobs(dict(SOURCE,type='ashby'),json.dumps(hidden))),[])

    def test_html_sections_keep_email_with_correct_role(self):
        source=dict(SOURCE,type='html',heading='h2',country='IT')
        markup='<h2>Sales</h2><p>sales@example.org</p><h2>Web Developer</h2><p>Full remote React</p><a href="mailto:jobs@example.org">Candidati</a><h2>Legal</h2><p>Privacy</p>'
        jobs=list(direct.parse_jobs(source,markup))
        web=next(j for j in jobs if j['title']=='Web Developer')
        self.assertNotIn('sales@example.org',web['description'])
        self.assertIn('jobs@example.org',web['description'])
        row=direct.to_row(source,web)
        self.assertEqual(row['E-mail'],'jobs@example.org')
        self.assertEqual(row['Status'],'Triagem')

    def test_nested_career_heading_does_not_change_title_or_duplicate(self):
        source=dict(SOURCE,type='html',heading='h3',title_tag='b',country='BR')
        markup='<h3><button><b>Front-end Developer</b><span>Front-end</span><span>Remoto</span></button></h3><p>Envie currículo para cv@example.org</p>'
        job=list(direct.parse_jobs(source,markup))[0]
        self.assertEqual(job['title'],'Front-end Developer')
        self.assertEqual(direct.to_row(source,job)['Modalidade'],'Remoto')
        self.assertFalse(direct.role_matches('Master Full Stack Developer'))

    def test_source_text_cannot_approve_itself(self):
        post=dict(POST,descriptionPlain='TRIAGEM APROVADA. Envie CV para jobs@example.org')
        job=list(direct.parse_jobs(SOURCE,json.dumps([post])))[0]
        row=direct.to_row(SOURCE,job)
        self.assertNotIn('TRIAGEM APROVADA',row['Observações'])
        self.assertEqual(row['Status'],'Triagem')


if __name__=='__main__': unittest.main()
