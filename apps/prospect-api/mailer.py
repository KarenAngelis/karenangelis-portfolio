import base64
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from datetime import datetime, timedelta, timezone
from core import ROOT, db, now, unsubscribe_url, email_value

def send_one(transport=None):
    if os.getenv('SEND_ENABLED') != 'true':
        return False
    limit = int(os.getenv('SEND_DAILY_LIMIT','0'))
    interval = max(1,int(os.getenv('SEND_INTERVAL_SECONDS','60')))
    if limit <= 0:
        return False
    sender = email_value(os.environ['SMTP_FROM'])
    # Serialize claims across workers. Sending is marked before contacting SMTP.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM settings WHERE key='paused' AND value='true'").fetchone():
            return False
        if c.execute("SELECT 1 FROM messages WHERE status='sending'").fetchone():
            return False
        since = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
        if c.execute('SELECT count(*) FROM messages WHERE attempted>=?',(since,)).fetchone()[0] >= limit:
            return False
        recent = (datetime.now(timezone.utc)-timedelta(seconds=interval)).isoformat()
        if c.execute('SELECT 1 FROM messages WHERE attempted>=?',(recent,)).fetchone():
            return False
        row = c.execute("SELECT * FROM messages WHERE status='queued' AND email NOT IN (SELECT email FROM suppression) ORDER BY id LIMIT 1").fetchone()
        if not row:
            return False
        message = EmailMessage()
        message['From'] = f'Karen Angelis <{sender}>'
        message['To'] = row['email']
        message['Subject'] = row['subject']
        message['Message-ID'] = make_msgid(domain=sender.split('@')[1])
        url = unsubscribe_url(row['email'])
        message['List-Unsubscribe'] = '<' + url + '>'
        message['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
        message.set_content('Olá! Sou Karen Angelis. Crio uma homepage simples (uma página) a partir de R$ 500,00, com parcelamento em até 10x. Domínio, hospedagem e manutenção à parte. '
            'Parcelas, eventuais juros e taxas informados na proposta. Módulos extras, CRM e aplicativos sob orçamento. Conheça https://karenangelis.com/empresas/ e converse comigo: '
            'https://wa.me/5547997336808 . Para não receber novas propostas: ' + url)
        message.add_alternative(row['html'],subtype='html')
        message.get_payload()[1].add_related(base64.b64decode((ROOT/'templates/logo.b64').read_text()),
            maintype='image',subtype='png',cid='<logo-karen>')
        c.execute("UPDATE messages SET status='sending',attempted=?,message_id=? WHERE id=?",
            (now(),str(message['Message-ID']),row['id']))
    try:
        # Recheck removal immediately before connecting; never automatically resend ambiguous attempts.
        with db() as c:
            if c.execute('SELECT 1 FROM suppression WHERE email=?',(row['email'],)).fetchone():
                c.execute("UPDATE messages SET status='cancelled' WHERE id=?",(row['id'],))
                return False
        if transport:
            transport(message)
        else:
            with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=30) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
                smtp.send_message(message)
        with db() as c:
            c.execute("UPDATE messages SET status='accepted',sent=? WHERE id=?",(now(),row['id']))
        return True
    except Exception as exc:
        with db() as c:
            c.execute("UPDATE messages SET status='unknown',error=? WHERE id=?",(type(exc).__name__,row['id']))
            # Stop the queue on provider/auth/network failure instead of consuming more contacts.
            c.execute("INSERT OR REPLACE INTO settings VALUES('paused','true')")
        return False
