"""Google Sheets transport. Credentials stay on the server, never in the sheet.

Only the coordinator may write system columns. This transport deliberately does
not treat spreadsheet edits as permission to send an application.
"""
import os
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
        response = self.client.post('https://oauth2.googleapis.com/token', data={
            'grant_type': 'refresh_token',
            'client_id': os.environ['JOBS_GOOGLE_CLIENT_ID'],
            'client_secret': os.environ['JOBS_GOOGLE_CLIENT_SECRET'],
            'refresh_token': os.environ['JOBS_GOOGLE_REFRESH_TOKEN'],
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
