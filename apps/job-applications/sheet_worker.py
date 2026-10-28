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


def send_one(sheet, transport=None, now=None):
    if os.getenv('JOBS_SEND_ENABLED') != 'true':
        return False
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
        # Approval must attest to checking eligibility, channel, attachments and instructions.
        if (email not in [e.lower() for e in candidates]
                or 'TRIAGEM APROVADA' not in row['Observações']
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
            'Atualizado em':timestamp(),'ID da mensagem':result['id'],'Comprovante ou thread':evidence})
        return True
    return False


def collect(sheet):
    key_path=Path(os.getenv('JOBS_SECRETS_DIR','/secrets'))/'serpapi.txt'
    if not key_path.exists():
        return
    key=key_path.read_text().strip()
    history=sheet.history()
    existing={r['ID'] for r in sheet.read_jobs()}
    for search in json.loads((ROOT/'searches.json').read_text()):
        marker='serpapi-'+search['country']
        starts=[datetime.fromisoformat(r[0]).timestamp() for r in history
                if r[1]==marker and r[3]=='SEARCH_ATTEMPT']
        if starts and max(starts)>time.time()-43200:
            continue
        sheet.append_history(timestamp(),marker,'SEARCH_ATTEMPT','','','Uma página; intervalo mínimo de 12h')
        # Use a separate client: never send a Google bearer token to the job source.
        params=dict(search['params'])
        if search.get('queries'):
            params['q']=search['queries'][len(starts)%len(search['queries'])]
        with httpx.Client(timeout=httpx.Timeout(120,connect=15)) as source:
            response=source.get('https://serpapi.com/search',params={
                'engine':'google_jobs','api_key':key,**params})
        if response.status_code!=200:
            raise RuntimeError('Job source request failed')
        result=response.json()
        if result.get('error') and result['error'] != "Google hasn't returned any results for this query.":
            raise RuntimeError('Job source returned an error')
        rows=[]
        for job in result.get('jobs_results',[]):
            links=job.get('apply_options',[])
            identity=str(job.get('job_id') or json.dumps([job.get('company_name'),job.get('title'),links],sort_keys=True))
            uid='serp-'+hashlib.sha256(identity.encode()).hexdigest()
            if uid in existing:
                continue
            existing.add(uid)
            description=str(job.get('description',''))[:45000]
            emails=sorted(set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',description)))
            rows.append({'ID':uid,'Empresa':job.get('company_name',''),'Vaga':job.get('title',''),
                'País':search['country'],'Canal':'E-mail' if len(emails)==1 else 'Link',
                'E-mail':emails[0] if len(emails)==1 else '',
                'Link da candidatura':next((x.get('link','') for x in links if x.get('link')),''),
                'Idioma':{'BR':'pt-BR','PT':'pt-PT','IT':'it'}[search['country']],
                'Status':'Triagem','Fonte':'SerpApi / Google Jobs','Descrição':description,
                'Atualizado em':timestamp(),'Próxima ação':'Verificar requisitos, vigência e canal de candidatura',
                'Observações':'E-mail extraído do anúncio; ainda não validado como canal de candidatura.'})
        sheet.append_jobs(rows)
        sheet.append_history(timestamp(),marker,'SEARCH_COMPLETE','','',str(len(rows))+' novas vagas')


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
