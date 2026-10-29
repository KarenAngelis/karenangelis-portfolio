"""Isolated job discovery and application queue. No commercial campaign data."""
import argparse
import hashlib
import html
import json
import os
import re
import smtplib
import sqlite3
import ssl
import time
from contextlib import closing
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).parent
SENDER = 'karen.denich@gmail.com'

def connect():
    path = Path(os.getenv('JOBS_DB', '/data/jobs.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, company TEXT, title TEXT, country TEXT,
      description TEXT, links TEXT, email_candidates TEXT,
      discovered REAL, status TEXT DEFAULT 'review', email TEXT,
      language TEXT, subject TEXT, body TEXT, attempted REAL, error TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS suppression(email TEXT PRIMARY KEY);
    ''')
    return c

def store_jobs(results, country):
    with closing(connect()) as c, c:
        for job in results:
            company = str(job.get('company_name', '')).strip()
            title = str(job.get('title', '')).strip()
            description = str(job.get('description', ''))
            links = job.get('apply_options', [])
            identity = str(job.get('job_id') or json.dumps([company, title, links], sort_keys=True))
            key = hashlib.sha256(identity.encode()).hexdigest()
            # Candidates are evidence to inspect, not automatically trusted recipients.
            emails = sorted(set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', description)))
            c.execute('INSERT OR IGNORE INTO jobs(id,company,title,country,description,links,email_candidates,discovered) VALUES(?,?,?,?,?,?,?,?)',
                      (key, company, title, country, description, json.dumps(links), json.dumps(emails), time.time()))

def collect():
    raise RuntimeError('Legacy collector retired. Use sheet_worker.py with sources.json.')


def render(company, title, language):
    texts = json.loads((ROOT / 'translations.json').read_text())[language]
    greeting = texts['greeting'].format(company=company) if company else texts['fallback']
    template = (ROOT / 'template.approved.pt-BR.html').read_text()
    template = re.sub(r'<!--(?!\[if).*?-->', '', template, flags=re.S)
    template = template.replace('{{saudacao}}', html.escape(greeting))
    if language != 'pt-BR':
        # Keep every layout element/style of the approved HTML in all languages.
        template = template.replace('lang="pt-BR"', 'lang="'+language+'"')
        paragraphs = {
            'Gostaria de apresentar meu trabalho':texts['intro']+' '+texts['data'],
            'Minha experiência em suporte SaaS':texts['background'],
            'Produto web e aplicativo Flutter/Dart':texts['luniay'],
            'Produto de atendimento com interface web':texts['clycka'],
            'Gestão de estoque com React':texts['stock'],
            'Tenho interesse em oportunidades':texts['closing'],
        }
        for prefix,value in paragraphs.items():
            template,n=re.subn('>'+re.escape(prefix)+r'.*?</p>',
                lambda m:'>'+html.escape(value)+'</p>',template,count=1,flags=re.S)
            if n!=1: raise ValueError('Approved template paragraph missing')
        labels={'Currículo online':texts['cv'],'Ver meu GitHub':texts['github'],
                'Um pouco do que construo.':texts['projects'],'Conhecer Luniay':texts['visit'],
                'Conhecer Clycka':texts['visit'],'Explorar o código':texts['code'],
                'Obrigada pela atenção,':texts['thanks'],'Desenvolvedora Full Stack':texts['role'],
                'DESENVOLVIMENTO WEB &amp; APLICATIVOS':texts['role'].upper(),
                'Interfaces, APIs e dados conectados<br>às necessidades de quem usa.':texts['role'],
                'Conheça meu trabalho com interfaces, APIs e banco de dados — portfólio, aplicações e código.':texts['role'],
                'PROJETOS SELECIONADOS':{'pt-PT':'PROJETOS SELECIONADOS','it':'PROGETTI SELEZIONATI','en':'SELECTED PROJECTS'}[language],
                'Vamos conversar?':{'pt-PT':'Vamos conversar?','it':'Parliamone!','en':"Let’s talk!"}[language],
                '/ INTEGRAÇÕES':{'pt-PT':'/ INTEGRAÇÕES','it':'/ INTEGRAZIONI','en':'/ INTEGRATIONS'}[language],
                '/ API + DADOS':{'pt-PT':'/ API + DADOS','it':'/ API + DATI','en':'/ API + DATA'}[language]}
        for before,after in labels.items():
            template=template.replace(before,html.escape(after))
    if '{{' in template:
        raise ValueError('Unresolved template variables')
    return texts['subject'].format(title=title), template


def prepare(job_id, email, language):
    """After checking active status, role/stack, location, language and application instructions."""
    if language not in ('pt-BR', 'pt-PT', 'it', 'en'):
        raise ValueError('Unsupported language')
    email = email.strip().lower()
    with closing(connect()) as c, c:
        row = c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row or row['status'] != 'review':
            raise ValueError('Job must be in review')
        candidates = [x.lower() for x in json.loads(row['email_candidates'])]
        if email not in candidates:
            raise ValueError('Recipient must occur in the job description')
        subject, body = render(row['company'], row['title'], language)
        if '\n' in subject or '\r' in subject:
            raise ValueError('Invalid subject')
        c.execute("UPDATE jobs SET email=?,language=?,subject=?,body=?,status='queued' WHERE id=?",
                  (email, language, subject, body, job_id))


def send_one(transport=None):
    if os.getenv('JOBS_SEND_ENABLED') != 'true':
        return False
    if os.getenv('JOBS_SMTP_USER') != SENDER:
        raise ValueError('Authenticate the designated Gmail sender')
    # Hard ceiling, not a promise of provider quota. Reserve room for personal mail.
    ceiling = min(500, max(0, int(os.getenv('JOBS_DAILY_LIMIT', '500'))))
    reserve = max(0, int(os.getenv('JOBS_PERSONAL_RESERVE', '50')))
    limit = max(0, ceiling - reserve)
    interval = max(180, int(os.getenv('JOBS_SEND_INTERVAL_SECONDS', '180')))
    now = time.time()
    with closing(connect()) as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM settings WHERE key='paused' AND value='true'").fetchone():
            return False
        if c.execute("SELECT 1 FROM jobs WHERE status='sending'").fetchone():
            return False
        if c.execute('SELECT count(*) FROM jobs WHERE attempted>?', (now-86400,)).fetchone()[0] >= limit:
            return False
        if c.execute('SELECT 1 FROM jobs WHERE attempted>?', (now-interval,)).fetchone():
            return False
        row = c.execute("""SELECT * FROM jobs j WHERE status='queued'
          AND email NOT IN (SELECT email FROM suppression)
          AND NOT EXISTS (SELECT 1 FROM jobs old WHERE old.email=j.email AND old.attempted IS NOT NULL)
          ORDER BY discovered LIMIT 1""").fetchone()
        if not row:
            return False
        if not row['body'] or '{{' in row['body']:
            raise ValueError('Unrendered application')
        message = EmailMessage()
        message['From'] = f'Karen Angelis <{SENDER}>'
        message['To'] = row['email']
        message['Subject'] = row['subject']
        message['Message-ID'] = f'<job-{row["id"]}@gmail.com>'
        text = html.unescape(re.sub('<[^>]+>', ' ', row['body']))
        message.set_content(re.sub(r'\s+', ' ', text).strip() + '\nhttps://karenangelis.com\nhttps://github.com/KarenAngelis')
        message.add_alternative(row['body'], subtype='html')
        c.execute("UPDATE jobs SET status='sending',attempted=? WHERE id=?", (now,row['id']))
        c.commit()
    try:
        if transport:
            transport(message)
        else:
            with smtplib.SMTP('smtp.gmail.com',587,timeout=30) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(SENDER,os.environ['JOBS_SMTP_APP_PASSWORD'])
                smtp.send_message(message)
        with closing(connect()) as c, c:
            c.execute("UPDATE jobs SET status='accepted' WHERE id=?", (row['id'],))
        return True
    except Exception as exc:
        with closing(connect()) as c, c:
            c.execute("UPDATE jobs SET status='unknown',error=? WHERE id=?", (type(exc).__name__,row['id']))
            c.execute("INSERT OR REPLACE INTO settings VALUES('paused','true')")
        return False


def run():
    next_collect = 0
    while True:
        if time.time() >= next_collect:
            try:
                collect()
            except Exception as exc:
                print('Collection failed:', type(exc).__name__, flush=True)
            next_collect = time.time() + max(43200,int(os.getenv('JOBS_SEARCH_INTERVAL_SECONDS','43200')))
        send_one()
        time.sleep(10)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['run','collect','status','prepare'])
    parser.add_argument('--id'); parser.add_argument('--email'); parser.add_argument('--language')
    args = parser.parse_args()
    if args.command == 'run': run()
    elif args.command == 'collect': collect()
    elif args.command == 'prepare': prepare(args.id,args.email,args.language)
    else:
        with closing(connect()) as c:
            print(json.dumps([dict(x) for x in c.execute('SELECT id,company,title,country,email_candidates,status FROM jobs')],ensure_ascii=False))
