"""Google Sheets transport. Credentials stay on the server, never in the sheet.

Only the coordinator may write system columns. This transport deliberately does
not treat spreadsheet edits as permission to send an application.
"""
import os
import json
from pathlib import Path
from urllib.parse import quote
import httpx

SHEET_ID = '1XaS_gJ_gp7V3NHFInpx4qrQNecz3ApmBWr4maHugt8o'
HEADERS = ['ID', 'Empresa', 'Vaga', 'País', 'Contrato', 'Modalidade', 'Nível',
           'Idioma', 'Canal', 'E-mail', 'Link da candidatura', 'Status',
           'Responsável', 'Próxima ação', 'Prazo', 'Tentativa em', 'Enviado em',
           'Última resposta', 'Comprovante ou thread', 'Fonte', 'Observações',
           'Atualizado em', 'Descrição', 'ID da mensagem']


class Sheets:
    def __init__(self, client=None):
        self.client = client or httpx.Client(timeout=30)
        self.base = 'https://sheets.googleapis.com/v4/spreadsheets/' + SHEET_ID

    def authenticate(self):
        secret_dir = Path(os.getenv('JOBS_SECRETS_DIR', '/secrets'))
        if (secret_dir / 'token.json').exists():
            settings = json.loads((secret_dir / 'client.json').read_text())
            token = json.loads((secret_dir / 'token.json').read_text())
            if token.get('email') != 'karen.denich@gmail.com':
                raise ValueError('Unexpected Google account')
            settings['refresh_token'] = token['refresh_token']
        else:
            settings = {
                'client_id': os.environ['JOBS_GOOGLE_CLIENT_ID'],
                'client_secret': os.environ['JOBS_GOOGLE_CLIENT_SECRET'],
                'refresh_token': os.environ['JOBS_GOOGLE_REFRESH_TOKEN'],
            }
        response = self.client.post('https://oauth2.googleapis.com/token', data={
            'grant_type': 'refresh_token',
            **settings,
        })
        if response.status_code != 200:
            raise RuntimeError('Google authorization failed; reconnect the account')
        self.client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']

    def request(self, method, path, **kwargs):
        response = self.client.request(method, self.base + path, **kwargs)
        if response.status_code >= 400:
            # Never include request headers, tokens or private response bodies.
            raise RuntimeError(f'Sheets request failed ({response.status_code})')
        return response.json()

    def read_jobs(self):
        # A bounded read, expanded explicitly when the initial capacity is reached.
        values = self.request('GET', '/values/' + quote('Candidaturas!A1:X1000', safe=''))
        rows = values.get('values', [])
        if not rows or rows[0] != HEADERS:
            raise ValueError('Unexpected Candidaturas schema; no writes allowed')
        result = []
        seen = set()
        for cells in rows[1:]:
            if not any(cells):
                continue
            row = dict(zip(HEADERS, cells + [''] * (len(HEADERS)-len(cells))))
            if not row['ID'] or row['ID'] in seen:
                raise ValueError('Missing or duplicate ID; resolve before processing')
            seen.add(row['ID'])
            result.append(row)
        return result

    def append_history(self, timestamp, job_id, event, previous, status, evidence):
        # RAW prevents text from an external job listing becoming a formula.
        return self.request('POST', '/values/' + quote('Historico!A:G', safe='') + ':append',
            params={'valueInputOption': 'RAW', 'insertDataOption': 'INSERT_ROWS'},
            json={'values': [[timestamp, job_id, 'Backend candidaturas', event,
                              previous, status, evidence]]})

    def history(self):
        data = self.request('GET', '/values/Historico!A1:G10000').get('values', [])
        if len(data) >= 10000:
            raise ValueError('History capacity reached; archive before resuming')
        return [r + [''] * (7-len(r)) for r in data[1:] if r]

    def append_jobs(self, rows):
        if not rows:
            return
        existing = self.read_jobs()
        if len(existing) + len(rows) > 999:
            raise ValueError('Sheet capacity reached')
        appended = self.request('POST', '/values/Candidaturas!A:X:append',
            params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},
            json={'values': [[row.get(h, '') for h in HEADERS] for row in rows]})
        # Extend the existing native table so appended jobs keep its dropdowns.
        # No row sorting or rewriting of human edits.
        import re
        updated = appended.get('updates', {}).get('updatedRange', '')
        end = re.search(r':X(\d+)$', updated)
        if end:
            self.expand_job_table(int(end.group(1)))

    def expand_job_table(self, end_row):
        metadata = self.request('GET', '', params={'fields': 'sheets(properties(sheetId,title),tables(tableId,name,range))'})
        for tab in metadata.get('sheets', []):
            if tab.get('properties', {}).get('title') != 'Candidaturas':
                continue
            for table in tab.get('tables', []):
                if table.get('name') != 'Candidaturas':
                    continue
                span = table['range']
                if span.get('endRowIndex', 0) >= end_row:
                    return
                self.request('POST', ':batchUpdate', json={'requests': [{'updateTable': {
                    'table': {'tableId': table['tableId'], 'range': dict(span, endRowIndex=end_row)},
                    'fields': 'range'}}]})
                return


    def update_system(self, job_id, values):
        # Re-resolve ID each time; never keep row numbers across collection cycles.
        raw = self.request('GET','/values/Candidaturas!A1:X1000').get('values',[])
        positions = [i+1 for i,r in enumerate(raw) if r and r[0]==job_id]
        if len(positions)!=1:
            raise ValueError('Job ID missing or ambiguous')
        row = positions[0]
        allowed={'Status':'L','Tentativa em':'P','Enviado em':'Q',
                 'Comprovante ou thread':'S','Atualizado em':'V','ID da mensagem':'X'}
        data=[{'range':f'Candidaturas!{allowed[k]}{row}','values':[[v]]}
              for k,v in values.items()]
        self.request('POST','/values:batchUpdate',json={'valueInputOption':'RAW','data':data})


if __name__ == '__main__':
    import json
    sheet = Sheets()
    try:
        sheet.authenticate()
        jobs = sheet.read_jobs()
        print(json.dumps({'connected': True, 'records': len(jobs),
                          'spreadsheet_id': SHEET_ID}))
    finally:
        sheet.client.close()
