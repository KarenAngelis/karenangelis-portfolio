import unittest
from unittest.mock import patch
import httpx
import sheets
import jobs


class SheetsTests(unittest.TestCase):
    def make(self, rows):
        return sheets.Sheets(httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={'values': rows}))))

    def test_preserves_link_jobs(self):
        cells = ['one', 'Empresa', 'Dev'] + [''] * 21
        cells[8] = 'Link'
        cells[10] = 'https://example.org/apply'
        cells[11] = 'Triagem'
        result = self.make([sheets.HEADERS, cells]).read_jobs()
        self.assertEqual(result[0]['Canal'], 'Link')
        self.assertEqual(result[0]['Status'], 'Triagem')

    def test_duplicate_ids_fail_closed(self):
        with self.assertRaises(ValueError):
            self.make([sheets.HEADERS, ['one'], ['one']]).read_jobs()

    def test_changed_schema_fails_closed(self):
        with self.assertRaises(ValueError):
            self.make([['Company', 'Email']]).read_jobs()

    def test_api_failure_does_not_expose_body(self):
        sheet = sheets.Sheets(httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(403, text='PRIVATE DATA'))))
        with self.assertRaisesRegex(RuntimeError, r'\(403\)') as caught:
            sheet.read_jobs()
        self.assertNotIn('PRIVATE', str(caught.exception))

    def test_history_uses_raw_values(self):
        def handle(request):
            self.assertEqual(request.url.params['valueInputOption'], 'RAW')
            self.assertIn(b'=untrusted', request.content)
            return httpx.Response(200, json={})
        sheet = sheets.Sheets(httpx.Client(transport=httpx.MockTransport(handle)))
        sheet.append_history('2026-10-28', 'one', '=untrusted', '', 'Triagem', '')

    def test_append_expands_existing_native_table_without_overwriting_rows(self):
        calls=[]
        def handle(request):
            calls.append(request)
            url=str(request.url)
            if '/values/Candidaturas!A:X:append' in url:
                return httpx.Response(200,json={'updates':{'updatedRange':'Candidaturas!A10:X11'}})
            if '/values/' in url:
                return httpx.Response(200,json={'values':[sheets.HEADERS]})
            if request.method=='GET':
                return httpx.Response(200,json={'sheets':[{'properties':{'title':'Candidaturas','sheetId':1},
                    'tables':[{'tableId':'t1','name':'Candidaturas','range':{'sheetId':1,'endRowIndex':9,'endColumnIndex':24}}]}]})
            body=__import__('json').loads(request.content)
            table=body['requests'][0]['updateTable']
            self.assertEqual(table['fields'],'range')
            self.assertEqual(table['table']['range']['endRowIndex'],11)
            return httpx.Response(200,json={})
        sheet=sheets.Sheets(httpx.Client(transport=httpx.MockTransport(handle),trust_env=False))
        sheet.append_jobs([{'ID':'new','Empresa':'Demo','Vaga':'Frontend'}])
        self.assertEqual(len(calls),4)

    def test_approved_html_is_actual_mime_body(self):
        subject, body = jobs.render('Empresa & Filhos', 'Fullstack', 'pt-BR')
        self.assertIn('PROJETOS SELECIONADOS', body)
        self.assertIn('Interfaces, APIs e dados conectados', body)
        self.assertEqual(body.count('width="48%" height="50"'), 2)
        self.assertIn('Olá, equipe da Empresa &amp; Filhos!', body)
        self.assertNotIn('{{', body)


if __name__ == '__main__':
    unittest.main()
