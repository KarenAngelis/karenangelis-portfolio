"""One coordinator, Google Sheets as job and attempt storage. No SQLite.

History must not be deleted: it is the durable at-most-once sending ledger.
An acknowledged reservation precedes every Gmail request. Unresolved attempts
block all subsequent sending, including after a restart.
"""
import base64
import fcntl
import hashlib
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import httpx
from jobs import ROOT, SENDER, render
from sheets import Sheets

START = 'GMAIL_ATTEMPT'
DONE = 'GMAIL_ACCEPTED'
READY = 'Pronto para e-mail'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def queue_email_jobs(sheet):
    """Explicit opt-in by the owner: email rows no longer require manual review."""
    rows = sheet.read_jobs()
    history = sheet.history()
    used = {json.loads(r[6])['email'].lower() for r in history if r[3] == START}
    used.update(r['E-mail'].strip().lower() for r in rows
                if r['Status'] == 'Candidatura concluída' and r['E-mail'])
    for row in rows:
        if row['Status'] not in ('Triagem', READY) or row['Canal'] != 'E-mail':
            continue
        email = row['E-mail'].strip().lower()
        reason = ''
        status = READY
        if email in used:
            status, reason = 'Descartada', 'Envio duplicado evitado: destinatário já contatado.'
        elif (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._%+\-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email)
              or email not in [e.lower() for e in re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', row['Descrição'])]
              or not row['Fonte'] or not row['Link da candidatura']):
            status, reason = 'Pendente por link', 'E-mail inválido ou sem evidência no anúncio; usar o link ou corrigir o endereço.'
        else:
            reason = 'Envio automático autorizado pela titular; aguardando intervalo/cota do Gmail.'
        if row['Status'] == status:
            continue
        sheet.append_history(timestamp(), row['ID'], 'EMAIL_AUTO_QUEUE', row['Status'], status, reason)
        sheet.update_system(row['ID'], {'Status': status, 'Próxima ação': reason, 'Atualizado em': timestamp()})


def send_one(sheet, transport=None, now=None):
    if os.getenv('JOBS_SEND_ENABLED') != 'true':
        return False
    queue_email_jobs(sheet)
    now = time.time() if now is None else now
    history = sheet.history()
    attempts = [r for r in history if r[3] == START]
    completed = {r[1] for r in history if r[3] == DONE}
    if any(r[1] not in completed for r in attempts):
        return False
    # Invalid timestamps fail closed rather than silently ignoring a past attempt.
    times = [datetime.fromisoformat(r[0]).timestamp() for r in attempts]
    limit = max(0,min(500,int(os.getenv('JOBS_DAILY_LIMIT','500'))) -
                max(0,int(os.getenv('JOBS_PERSONAL_RESERVE','50'))))
    if sum(t > now-86400 for t in times) >= limit:
        return False
    interval = max(180,int(os.getenv('JOBS_SEND_INTERVAL_SECONDS','180')))
    if times and max(times) > now-interval:
        return False
    used_ids={r[1] for r in attempts}
    used_emails={json.loads(r[6])['email'].lower() for r in attempts}
    for row in sheet.read_jobs():
        if row['Status'] != READY or row['Canal'] != 'E-mail':
            continue
        email=row['E-mail'].strip().lower()
        if row['ID'] in used_ids or email in used_emails:
            continue
        candidates=re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',row['Descrição'])
        # The owner's standing authorization replaces manual approval.
        if (email not in [e.lower() for e in candidates]
                or not row['Fonte'] or not row['Link da candidatura']):
            continue
        subject,body=render(row['Empresa'],row['Vaga'],row['Idioma'])
        if '\n' in subject or '\r' in subject:
            raise ValueError('Invalid subject')
        message=EmailMessage()
        message['From']=f'Karen Angelis <{SENDER}>'
        message['To']=email
        message['Subject']=subject
        identity=hashlib.sha256(row['ID'].encode()).hexdigest()
        message['Message-ID']=f'<job-{identity}@karenangelis.com>'
        plain=html.unescape(re.sub('<[^>]+>',' ',body))
        message.set_content(re.sub(r'\s+',' ',plain)+'\nhttps://karenangelis.com\nhttps://github.com/KarenAngelis')
        message.add_alternative(body,subtype='html')
        when=timestamp()
        sheet.append_history(when,row['ID'],START,READY,'Em andamento',json.dumps({'email':email}))
        sheet.update_system(row['ID'],{'Status':'Em andamento','Tentativa em':when,'Atualizado em':when})
        # No automatic retries: even a timeout may mean Google accepted the message.
        if transport:
            result=transport(message)
        else:
            response=sheet.client.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                json={'raw':base64.urlsafe_b64encode(message.as_bytes()).decode()})
            if response.status_code != 200:
                raise RuntimeError('Gmail result uncertain; reconcile before resuming')
            result=response.json()
        if not result.get('id'):
            raise RuntimeError('Missing Gmail confirmation')
        evidence='https://mail.google.com/mail/u/0/#sent/'+result['id']
        sheet.append_history(timestamp(),row['ID'],DONE,'Em andamento','Candidatura concluída',evidence)
        sheet.update_system(row['ID'],{'Status':'Candidatura concluída','Enviado em':timestamp(),
            'Atualizado em':timestamp(),'Próxima ação':'Aguardar retorno da empresa.','ID da mensagem':result['id'],'Comprovante ou thread':evidence})
        return True
    return False


def collect(sheet):
    from direct_sources import collect_direct
    return collect_direct(sheet)


def run():
    lock=Path('/data/coordinator.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            sheet=Sheets()
            try:
                sheet.authenticate()
                try:
                    collect(sheet)
                except Exception as exc:
                    print('Collection:',type(exc).__name__,flush=True)
                send_one(sheet)
            except Exception as exc:
                print('Coordinator:',type(exc).__name__,flush=True)
            finally:
                sheet.client.close()
            time.sleep(60)


if __name__=='__main__': run()
