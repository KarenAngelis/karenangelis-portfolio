"""Technical eligibility only: syntax + MX, never proof of mailbox ownership."""
import os
from datetime import datetime, timedelta, timezone
import dns.resolver
import dns.exception
from core import db, email_value, now

resolver = dns.resolver.Resolver()
resolver.cache = dns.resolver.LRUCache(max_size=1000)


def check(email, resolve=None):
    resolve = resolve or resolver.resolve
    try:
        address = email_value(email)
    except ValueError:
        return 'invalid'
    try:
        answers = resolve(address.rsplit('@', 1)[1], 'MX', lifetime=2, search=False)
        return 'mx_ok' if any(str(r.exchange) != '.' for r in answers) else 'no_mail'
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return 'no_mail'
    except dns.exception.DNSException:
        return 'temporary'


def validate_batch():
    if os.getenv('AUTO_VALIDATE_CONTACTS') != 'true':
        return
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS contact_checks(email TEXT PRIMARY KEY, result TEXT, checked TEXT, retry_after TEXT)')
        rows = c.execute('''SELECT cnpj,email FROM companies WHERE contact_verified=0
            AND email IS NOT NULL AND source LIKE 'RFB dados abertos CNPJ;%'
            AND email NOT IN (SELECT email FROM suppression)
            AND email NOT IN (SELECT email FROM messages)
            AND email NOT IN (SELECT email FROM contact_checks WHERE retry_after>?)
            ORDER BY opened DESC,cnpj LIMIT 10''', (now(),)).fetchall()
    for row in rows:
        result = check(row['email'])
        delay = 1 if result == 'temporary' else 168
        retry = (datetime.now(timezone.utc)+timedelta(hours=delay)).isoformat()
        with db() as c:
            c.execute('INSERT OR REPLACE INTO contact_checks VALUES(?,?,?,?)',
                      (row['email'],result,now(),retry))
            if result == 'mx_ok':
                c.execute('''UPDATE companies SET contact_verified=1 WHERE cnpj=? AND email=?
                    AND email NOT IN (SELECT email FROM suppression)''',(row['cnpj'],row['email']))
