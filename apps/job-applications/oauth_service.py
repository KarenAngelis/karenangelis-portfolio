"""One-time, operator-initiated OAuth connection on the portfolio's HTTPS host.

No public authorization-start endpoint: an operator runs `authorize` in the VPS.
Only the callback and a non-sensitive health response are public.
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

SECRET_DIR = Path(os.getenv('JOBS_SECRETS_DIR', '/secrets'))
CALLBACK = 'https://karenangelis.com/api/jobs/oauth/callback'
ACCOUNT = 'karen.denich@gmail.com'
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/gmail.send']


def write_private(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def authorize():
    client = json.loads((SECRET_DIR / 'client.json').read_text())
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    write_private(SECRET_DIR / 'pending.json', {
        'state': state, 'verifier': verifier, 'expires': time.time() + 900})
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': client['client_id'], 'redirect_uri': CALLBACK,
        'response_type': 'code', 'scope': ' '.join(SCOPES),
        'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
        'access_type': 'offline', 'prompt': 'consent', 'login_hint': ACCOUNT})


def complete(query, client=None):
    if query.get('error'):
        raise ValueError('Authorization was not granted')
    pending_path = SECRET_DIR / 'pending.json'
    pending = json.loads(pending_path.read_text())
    state = query.get('state', [''])
    code = query.get('code', [''])
    if (len(state) != 1 or len(code) != 1 or not code[0]
            or not secrets.compare_digest(state[0], pending['state'])
            or time.time() > pending['expires']):
        raise ValueError('Invalid or expired authorization')
    # Consume the state before contacting Google. Failures require a new flow.
    pending_path.unlink()
    credentials = json.loads((SECRET_DIR / 'client.json').read_text())
    session = client or httpx.Client(timeout=30)
    try:
        response = session.post('https://oauth2.googleapis.com/token', data={
            **credentials, 'grant_type': 'authorization_code', 'code': code[0],
            'redirect_uri': CALLBACK, 'code_verifier': pending['verifier']})
        if response.status_code != 200:
            raise ValueError('Google token exchange failed')
        token = response.json()
        if not token.get('refresh_token'):
            raise ValueError('Offline authorization missing')
        granted = set(token.get('scope', '').split())
        if not set(SCOPES).issubset(granted):
            raise ValueError('Required permissions were not granted')
        profile = session.get('https://openidconnect.googleapis.com/v1/userinfo',
            headers={'Authorization': 'Bearer ' + token['access_token']})
        if profile.status_code != 200:
            raise ValueError('Could not verify account')
        user = profile.json()
        if user.get('email') != ACCOUNT or user.get('email_verified') is not True:
            raise ValueError('Wrong Google account')
        write_private(SECRET_DIR / 'token.json', {
            'refresh_token': token['refresh_token'], 'email': ACCOUNT,
            'scope': token['scope'], 'connected_at': time.time()})
    finally:
        if client is None:
            session.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Authorization codes must never be written to access logs.

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == '/api/jobs/oauth/health':
            self.respond(200, 'Serviço de conexão disponível.')
        elif parts.path == '/api/jobs/oauth/callback':
            try:
                complete(parse_qs(parts.query))
            except Exception:
                self.respond(400, 'Conexão não concluída. Gere uma nova autorização no servidor.')
            else:
                self.respond(200, 'Google conectado. A autorização foi salva no servidor. Os envios dependem da ativação da fila.')
        else:
            self.respond(404, 'Não encontrado.')

    def respond(self, status, text):
        data = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'authorize':
        print(authorize())
    else:
        HTTPServer(('0.0.0.0', 8003), Handler).serve_forever()
