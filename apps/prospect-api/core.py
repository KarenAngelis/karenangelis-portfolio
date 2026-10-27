"""Persistent prospecting queue. No network side effects on import."""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
TZ = ZoneInfo('America/Sao_Paulo')

def now():
    return datetime.now(timezone.utc).isoformat()

def today():
    return datetime.now(TZ).date()

@contextmanager
def db():
    path = Path(os.getenv('PROSPECT_DB', '/data/prospect.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=40)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def init():
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS companies(
          cnpj TEXT PRIMARY KEY, name TEXT NOT NULL, opened TEXT NOT NULL,
          city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
          email TEXT, contact_verified INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS suppression(email TEXT PRIMARY KEY, reason TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY, cnpj TEXT NOT NULL UNIQUE REFERENCES companies(cnpj),
          email TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'queued',
          created TEXT NOT NULL, attempted TEXT, sent TEXT, error TEXT,
          message_id TEXT UNIQUE, html TEXT NOT NULL, subject TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS collections(
          day TEXT PRIMARY KEY, page INTEGER NOT NULL DEFAULT 1,
          seen INTEGER NOT NULL DEFAULT 0, total INTEGER,
          status TEXT NOT NULL DEFAULT 'pending', error TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS collection_seen(
          day TEXT NOT NULL, cnpj TEXT NOT NULL, PRIMARY KEY(day,cnpj));
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        ''')

def email_value(value):
    value = str(value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", value):
        raise ValueError('E-mail inválido')
    return value

def cnpj_value(value):
    # Preserve alphanumeric CNPJs; punctuation is removed, never cast to integer.
    value = re.sub(r'[./\-\s]', '', str(value)).upper()
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', value):
        raise ValueError('Formato de CNPJ inválido')
    return value

def save_company(c, item):
    cnpj = cnpj_value(item['cnpj'])
    name = str(item['name']).strip()
    if not name or len(name) > 300:
        raise ValueError('Nome inválido')
    opened = date.fromisoformat(item['opened']).isoformat()
    c.execute('''INSERT INTO companies(cnpj,name,opened,city,state,source,updated)
      VALUES(?,?,?,?,?,?,?) ON CONFLICT(cnpj) DO UPDATE SET
      name=excluded.name,opened=excluded.opened,city=excluded.city,state=excluded.state,
      source=excluded.source,updated=excluded.updated''',
      (cnpj,name,opened,item.get('city',''),item.get('state',''),item['source'],now()))
    return cnpj

def token(email):
    secret = os.environ.get('UNSUBSCRIBE_SECRET', '')
    if len(secret) < 32:
        raise ValueError('UNSUBSCRIBE_SECRET precisa ter pelo menos 32 caracteres')
    encoded = base64.urlsafe_b64encode(email.encode()).decode().rstrip('=')
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature

def decode_token(value):
    encoded, signature = value.split('.', 1)
    email = email_value(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode())
    if not hmac.compare_digest(token(email), value):
        raise ValueError('Token inválido')
    return email

def unsubscribe_url(email):
    base = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('PUBLIC_BASE_URL deve usar HTTPS')
    return base + '/api/prospect/unsubscribe/' + token(email)

def render(company):
    template = (ROOT / 'templates/site.html').read_text()
    return template.replace('[Nome da empresa]', html.escape(company['name'])).replace(
        '{{unsubscribe_url}}', html.escape(unsubscribe_url(company['email']), quote=True))

def queue(c, cnpj):
    company = c.execute('SELECT * FROM companies WHERE cnpj=?', (cnpj,)).fetchone()
    if not company or not company['email'] or not company['contact_verified']:
        return False
    email = company['email']
    if c.execute('SELECT 1 FROM suppression WHERE email=?',(email,)).fetchone():
        return False
    subject = 'Um site para sua empresa | Karen Angelis'
    return c.execute('''INSERT OR IGNORE INTO messages(cnpj,email,created,html,subject)
        VALUES(?,?,?,?,?)''', (cnpj,email,now(),render(company),subject)).rowcount == 1

def suppress(c, email, reason):
    c.execute('INSERT OR REPLACE INTO suppression VALUES(?,?,?)',(email,reason,now()))
    c.execute("UPDATE messages SET status='cancelled' WHERE email=? AND status='queued'",(email,))

def schedule_days(c, start, end, refresh=False):
    if start > end or end > today():
        raise ValueError('Intervalo de datas inválido')
    day = start
    while day <= end:
        key = day.isoformat()
        existing = c.execute('SELECT status FROM collections WHERE day=?',(key,)).fetchone()
        if existing is None:
            c.execute('INSERT INTO collections(day,updated) VALUES(?,?)',(key,now()))
        elif refresh and existing['status'] in ('complete','error'):
            c.execute("UPDATE collections SET page=1,seen=0,total=NULL,status='pending',error=NULL,updated=? WHERE day=?",(now(),key))
            c.execute('DELETE FROM collection_seen WHERE day=?',(key,))
        day += timedelta(days=1)

def daily_schedule():
    if os.getenv('COLLECT_ENABLED') != 'true':
        return
    start = date.fromisoformat(os.environ['COLLECT_START_DATE'])
    current = today()
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key='scheduled_day'").fetchone()
        if row and row['value'] == current.isoformat():
            return
        # Catch up all missing days. Rescan the recent window for delayed registrations.
        schedule_days(c, start, current)
        schedule_days(c, max(start,current-timedelta(days=int(os.getenv('LOOKBACK_DAYS','7')))), current, True)
        c.execute("INSERT OR REPLACE INTO settings VALUES('scheduled_day',?)",(current.isoformat(),))

def collect_page(client):
    key = os.getenv('CASA_DADOS_API_KEY')
    if not key:
        return False
    with db() as c:
        job = c.execute("SELECT * FROM collections WHERE status='pending' ORDER BY day LIMIT 1").fetchone()
    if not job:
        return False
    day, page = job['day'], job['page']
    try:
        response = client.post('https://api.casadosdados.com.br/v5/cnpj/pesquisa',
            headers={'api-key': key}, json={'data_abertura':{'inicio':day,'fim':day},
            'limite':int(os.getenv('COLLECT_PAGE_SIZE','100')), 'pagina':page})
        response.raise_for_status()
        data = response.json()
        rows, total = data['cnpjs'], data['total']
        if not isinstance(rows,list) or type(total) is not int or total < 0:
            raise ValueError('Resposta da fonte incompatível')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Single collector process; lease check also protects stale responses.
            current = c.execute('SELECT * FROM collections WHERE day=?',(day,)).fetchone()
            if current['page'] != page or current['status'] != 'pending':
                return False
            added = 0
            for row in rows:
                if row['data_abertura'] != day:
                    raise ValueError('Fonte retornou data fora do intervalo')
                address = row.get('endereco') or {}
                cnpj = save_company(c, {'cnpj':row['cnpj'], 'name':row.get('nome_fantasia') or row['razao_social'],
                    'opened':row['data_abertura'], 'city':address.get('municipio',''), 'state':address.get('uf',''),
                    'source':'https://api.casadosdados.com.br/v5/cnpj/pesquisa'})
                added += c.execute('INSERT OR IGNORE INTO collection_seen VALUES(?,?)',(day,cnpj)).rowcount
            seen = current['seen'] + added
            if seen < total and added == 0:
                raise ValueError('Paginação incompleta ou repetida; revisar limite do fornecedor')
            c.execute('UPDATE collections SET page=?,seen=?,total=?,status=?,error=NULL,updated=? WHERE day=?',
                (page+1,seen,total,'complete' if seen >= total else 'pending',now(),day))
        return True
    except Exception as exc:
        # Avoid logging response bodies, credentials or personal data.
        with db() as c:
            c.execute("UPDATE collections SET status='error',error=?,updated=? WHERE day=?",
                (type(exc).__name__,now(),day))
        return False
