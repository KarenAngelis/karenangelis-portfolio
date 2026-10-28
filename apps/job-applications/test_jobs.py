import json
import os
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
import jobs

class JobTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'JOBS_DB':self.temp.name+'/db.sqlite','JOBS_SEND_ENABLED':'true','JOBS_SMTP_USER':jobs.SENDER,'JOBS_DAILY_LIMIT':'500','JOBS_PERSONAL_RESERVE':'50','JOBS_SEND_INTERVAL_SECONDS':'180'})
  self.env.start()
 def tearDown(self): self.env.stop(); self.temp.cleanup()
 def seed(self):
  jobs.store_jobs([{'job_id':'one','company_name':'A & B','title':'Frontend','description':'Send CV to jobs@example.org','apply_options':[]}],'BR')
  with closing(jobs.connect()) as c: return c.execute('SELECT id FROM jobs').fetchone()[0]
 def ready(self): jobs.prepare(self.seed(),'jobs@example.org','pt-BR')
 def test_translations_escape_and_complete(self):
  for lang in ['pt-BR','pt-PT','it','en']:
   _,body=jobs.render('<company>','Dev',lang)
   self.assertNotIn('{{',body); self.assertNotIn('<company>',body); self.assertIn('&lt;company&gt;',body)
 def test_discovery_dedup_and_no_auto_send(self):
  self.seed();self.seed()
  with closing(jobs.connect()) as c: self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
  self.assertFalse(jobs.send_one(lambda x:self.fail('Unreviewed job sent')))
 def test_recipient_must_be_in_source(self):
  with self.assertRaises(ValueError): jobs.prepare(self.seed(),'other@example.org','it')
 def test_acceptance_not_repeated(self):
  self.ready(); sent=[]
  self.assertTrue(jobs.send_one(sent.append));self.assertFalse(jobs.send_one(sent.append)); self.assertEqual(len(sent),1)
  self.assertIn(jobs.SENDER,sent[0]['From'])
 def test_failure_pauses_without_retry(self):
  self.ready()
  def fail(_): raise TimeoutError()
  self.assertFalse(jobs.send_one(fail))
  with closing(jobs.connect()) as c:
   self.assertEqual(c.execute('SELECT status FROM jobs').fetchone()[0],'unknown')
   self.assertEqual(c.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0],'true')
  self.assertFalse(jobs.send_one(lambda _:self.fail('retried')))
 def test_sender_guard(self):
  self.ready()
  with patch.dict(os.environ,{'JOBS_SMTP_USER':'wrong@example.org'}):
   with self.assertRaises(ValueError):jobs.send_one()
 def test_zero_budget(self):
  self.ready()
  with patch.dict(os.environ,{'JOBS_DAILY_LIMIT':'0'}): self.assertFalse(jobs.send_one())
 def test_suppression(self):
  self.ready()
  with closing(jobs.connect()) as c,c:c.execute('INSERT INTO suppression VALUES(?)',('jobs@example.org',))
  self.assertFalse(jobs.send_one())
if __name__=='__main__':unittest.main()
