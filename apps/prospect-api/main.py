import csv
import io
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from core import (ROOT, init, db, now, today, schedule_days, save_company, email_value,
                  cnpj_value, queue, suppress, decode_token)

@asynccontextmanager
async def lifespan(app):
    init()
    yield

app = FastAPI(title='Karen Angelis — Prospecção',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
security = HTTPBearer(auto_error=False)

@app.middleware('http')
async def private_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


def auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected = os.getenv('PROSPECT_ADMIN_TOKEN','')
    if len(expected) < 32:
        raise HTTPException(503,'Configure a credencial administrativa')
    if not credentials or not secrets.compare_digest(credentials.credentials,expected):
        raise HTTPException(401,'Autenticação necessária',headers={'WWW-Authenticate':'Bearer'})

class Company(BaseModel):
    cnpj: str
    name: str = Field(min_length=1,max_length=300)
    opened: date
    source: str = Field(min_length=1,max_length=1000)
    city: str = Field(default='',max_length=200)
    state: str = Field(default='',max_length=2)

class Contact(BaseModel):
    email: str
    verified: bool

class Collection(BaseModel):
    start: date
    end: date
    refresh: bool = False

class Control(BaseModel):
    paused: bool

class PreviousContact(BaseModel):
    email: str
    reason: str = Field(default='Contato anterior à implantação',min_length=1,max_length=300)

class Outcome(BaseModel):
    status: Literal['replied','bounced','closed','not_interested']

@app.get('/health')
def health():
    return {'status':'ok'}

@app.get('/prospeccao/',response_class=HTMLResponse)
def panel():
    return (ROOT/'panel.html').read_text()

@app.get('/api/prospect/summary',dependencies=[Depends(auth)])
def summary():
    with db() as c:
        return {'companies':c.execute('SELECT count(*) FROM companies').fetchone()[0],
            'contacts':c.execute('SELECT count(*) FROM companies WHERE contact_verified=1').fetchone()[0],
            'messages':{r[0]:r[1] for r in c.execute('SELECT status,count(*) FROM messages GROUP BY status')},
            'collections':[dict(r) for r in c.execute('SELECT * FROM collections ORDER BY day DESC LIMIT 90')],
            'send_enabled':os.getenv('SEND_ENABLED')=='true',
            'source_configured':bool(os.getenv('CASA_DADOS_API_KEY')),
            'paused':bool(c.execute("SELECT 1 FROM settings WHERE key='paused' AND value='true'").fetchone())}

@app.post('/api/prospect/collect',dependencies=[Depends(auth)])
def collect(body: Collection):
    if (body.end-body.start).days > 366:
        raise HTTPException(422,'Use intervalos de até 366 dias por solicitação')
    try:
        with db() as c:
            schedule_days(c,body.start,body.end,body.refresh)
    except ValueError as e:
        raise HTTPException(422,str(e))
    return {'status':'scheduled','source_configured':bool(os.getenv('CASA_DADOS_API_KEY'))}

@app.post('/api/prospect/companies',dependencies=[Depends(auth)])
def import_company(body: Company):
    if body.opened > today():
        raise HTTPException(422,'Abertura futura')
    try:
        with db() as c:
            cnpj = save_company(c,body.model_dump(mode='json'))
    except ValueError as e:
        raise HTTPException(422,str(e))
    return {'cnpj':cnpj}

@app.put('/api/prospect/companies/{cnpj}/contact',dependencies=[Depends(auth)])
def contact(cnpj: str, body: Contact):
    try:
        email, cnpj = email_value(body.email),cnpj_value(cnpj)
    except ValueError as e:
        raise HTTPException(422,str(e))
    with db() as c:
        if not c.execute('SELECT 1 FROM companies WHERE cnpj=?',(cnpj,)).fetchone():
            raise HTTPException(404,'Empresa não encontrada')
        if c.execute("SELECT 1 FROM messages WHERE cnpj=? AND status IN ('queued','sending')",(cnpj,)).fetchone():
            raise HTTPException(409,'Cancele ou conclua o envio existente antes de alterar o contato')
        c.execute('UPDATE companies SET email=?,contact_verified=?,updated=? WHERE cnpj=?',
            (email,body.verified,now(),cnpj))
    return {'status':'updated'}

@app.post('/api/prospect/companies/{cnpj}/queue',dependencies=[Depends(auth)])
def enqueue(cnpj: str):
    try:
        with db() as c:
            queued = queue(c,cnpj_value(cnpj))
    except ValueError as e:
        raise HTTPException(422,str(e))
    if not queued:
        raise HTTPException(409,'Contato ausente, não verificado, removido ou já abordado')
    return {'status':'queued'}

@app.post('/api/prospect/control',dependencies=[Depends(auth)])
def control(body: Control):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES('paused',?)",(str(body.paused).lower(),))
    return {'paused':body.paused}

@app.post('/api/prospect/messages/{message_id}/outcome',dependencies=[Depends(auth)])
def outcome(message_id: int, body: Outcome):
    with db() as c:
        row = c.execute('SELECT * FROM messages WHERE id=?',(message_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Mensagem não encontrada')
        if row['status'] in ('queued','sending','cancelled'):
            raise HTTPException(409,'Mensagem não enviada')
        c.execute('UPDATE messages SET status=? WHERE id=?',(body.status,message_id))
        suppress(c,row['email'],body.status)
    return {'status':body.status}

@app.get('/api/prospect/companies',dependencies=[Depends(auth)])
def companies(offset: int = Query(0,ge=0), limit: int = Query(100,ge=1,le=500)):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM companies ORDER BY opened DESC,cnpj LIMIT ? OFFSET ?',(limit,offset))]

@app.get('/api/prospect/export.csv',dependencies=[Depends(auth)])
def export():
    out = io.StringIO()
    writer = csv.writer(out,delimiter=';')
    writer.writerow(['CNPJ','Empresa','Abertura','Cidade','UF','Email','Contato verificado','Envio','Data','Fonte'])
    with db() as c:
        for r in c.execute('''SELECT c.cnpj,c.name,c.opened,c.city,c.state,c.email,c.contact_verified,m.status,m.sent,c.source
            FROM companies c LEFT JOIN messages m ON c.cnpj=m.cnpj ORDER BY c.opened,c.cnpj'''):
            # Prevent spreadsheet formula injection, keep CNPJ as text.
            writer.writerow(["'"+str(v) if i==0 or str(v or '').lstrip().startswith(('=','+','-','@')) else (v or '') for i,v in enumerate(r)])
    return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=prospeccao.csv'})

@app.get('/api/prospect/unsubscribe/{value}',response_class=HTMLResponse)
def removal_form(value: str):
    try:
        decode_token(value)
    except Exception:
        raise HTTPException(400,'Link inválido')
    # GET is read-only: scanners must not silently unsubscribe recipients.
    return '<!doctype html><meta charset="utf-8"><h1>Cancelar recebimento</h1><form method="post"><button>Não receber novas propostas</button></form>'

@app.post('/api/prospect/unsubscribe/{value}',response_class=HTMLResponse)
def removal(value: str):
    try:
        email = decode_token(value)
    except Exception:
        raise HTTPException(400,'Link inválido')
    with db() as c:
        suppress(c,email,'unsubscribe')
    return '<!doctype html><meta charset="utf-8"><p>Recebimento cancelado.</p>'


@app.post('/api/prospect/suppressions',dependencies=[Depends(auth)])
def previous_contact(body: PreviousContact):
    try:
        email = email_value(body.email)
    except ValueError as e:
        raise HTTPException(422,str(e))
    with db() as c:
        suppress(c,email,body.reason)
    return {'status':'suppressed'}

@app.get('/api/prospect/messages',dependencies=[Depends(auth)])
def messages(offset: int = Query(0,ge=0), limit: int = Query(100,ge=1,le=500)):
    with db() as c:
        return [dict(r) for r in c.execute(
            'SELECT id,cnpj,email,status,created,attempted,sent,error,message_id FROM messages ORDER BY id DESC LIMIT ? OFFSET ?',
            (limit,offset))]
