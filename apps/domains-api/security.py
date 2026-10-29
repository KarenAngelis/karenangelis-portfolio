import hashlib
import hmac
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ':' + key.hex()


def password_matches(password, encoded):
    # Run a KDF even for unknown users to reduce email enumeration by timing.
    encoded = encoded or ('00' * 16 + ':' + '00' * 64)
    return hmac.compare_digest(password_hash(password, encoded.split(':')[0]), encoded)


def issue_token(store, user_id, kind, ttl=1800):
    token = secrets.token_urlsafe(32)
    store.execute('INSERT INTO tokens VALUES(?,?,?,?)', (digest(token), user_id, kind, int(time.time()) + ttl))
    return token


def consume_token(store, token, kind):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM tokens WHERE token=? AND kind=? AND expires>?',
                         (digest(token), kind, int(time.time()))).fetchone()
        if row:
            db.execute('DELETE FROM tokens WHERE token=?', (digest(token),))
            return dict(row)
    return None


def send_account_mail(settings, email, token, kind):
    message = EmailMessage()
    message['From'] = settings.mail_from
    message['To'] = email
    message['Subject'] = 'Confirme seu e-mail — Karen Angelis' if kind == 'verify' else 'Redefina sua senha — Karen Angelis'
    action = 'confirmar seu e-mail' if kind == 'verify' else 'definir uma nova senha'
    message.set_content(f'Olá!\n\nAbra este link para {action}:\n\n'
                        f'{settings.origin}/dominios/#{kind}={token}\n\n'
                        'O link vale por 30 minutos. Se você não solicitou, ignore esta mensagem.\nKaren Angelis')
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
