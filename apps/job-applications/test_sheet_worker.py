import json
import os
import unittest
from unittest.mock import patch
from sheets import HEADERS
import sheet_worker as worker


class FakeSheet:
    def __init__(self):
        self.log=[]
        self.row={h:'' for h in HEADERS}
        self.row.update({'ID':'one','Empresa':'Empresa','Vaga':'Fullstack','Canal':'E-mail',
            'E-mail':'jobs@example.org','Idioma':'pt-BR','Status':worker.READY,
            'Descrição':'Candidaturas: jobs@example.org','Observações':'TRIAGEM APROVADA',
            'Fonte':'Página da empresa','Link da candidatura':'https://example.org/jobs'})
    def read_jobs(self): return [self.row.copy()]
    def history(self): return self.log.copy()
    def append_history(self,t,id,event,previous,status,evidence):
        self.log.append([t,id,'Backend candidaturas',event,previous,status,evidence])
    def update_system(self,id,values): self.row.update(values)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'JOBS_SEND_ENABLED':'true'})
        self.env.start(); self.sheet=FakeSheet()
    def tearDown(self): self.env.stop()
    def test_unreviewed_never_sent(self):
        self.sheet.row['Status']='Triagem'
        self.assertFalse(worker.send_one(self.sheet,lambda m:self.fail('sent')))
    def test_email_must_occur_in_evidence(self):
        self.sheet.row['E-mail']='other@example.org'
        self.assertFalse(worker.send_one(self.sheet,lambda m:self.fail('sent')))
    def test_html_and_receipt_recorded(self):
        sent=[]
        def send(m): sent.append(m); return {'id':'gmail-id'}
        self.assertTrue(worker.send_one(self.sheet,send))
        self.assertIn('PROJETOS SELECIONADOS',sent[0].get_body(preferencelist=('html',)).get_content())
        self.assertEqual(self.sheet.row['ID da mensagem'],'gmail-id')
        self.sheet.row['Status']=worker.READY
        self.assertFalse(worker.send_one(self.sheet,send))
        self.assertEqual(len(sent),1)
    def test_ambiguous_failure_blocks_next_attempt(self):
        def fail(m): raise TimeoutError()
        with self.assertRaises(TimeoutError): worker.send_one(self.sheet,fail)
        self.sheet.row['ID']='another'
        self.sheet.row['Status']=worker.READY
        self.assertFalse(worker.send_one(self.sheet,lambda m:self.fail('retried')))
    def test_reservation_failure_never_sends(self):
        with patch.object(self.sheet,'append_history',side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):
                worker.send_one(self.sheet,lambda m:self.fail('sent without reservation'))
    def test_zero_limit(self):
        with patch.dict(os.environ,{'JOBS_DAILY_LIMIT':'0'}):
            self.assertFalse(worker.send_one(self.sheet,lambda m:self.fail('sent')))
    def test_link_only_is_not_emailed(self):
        self.sheet.row['Canal']='Link'
        self.assertFalse(worker.send_one(self.sheet,lambda m:self.fail('sent')))


if __name__=='__main__': unittest.main()
