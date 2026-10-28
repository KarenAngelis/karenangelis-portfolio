"""Importação local dos ZIPs Estabelecimentos da Receita, sem API paga.

CSV oficial: Latin-1, delimitador ponto e vírgula, sem cabeçalho.
Não marca contato como verificado nem dispara mensagens ao importar.
"""
import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, date
from pathlib import Path
from core import init, db, save_company, email_value, now


def parse_row(row, since, until, source):
    if len(row) != 30:
        raise ValueError('Layout de Estabelecimentos incompatível: esperado 30 campos')
    if row[5] != '02':
        return None
    try:
        opened = datetime.strptime(row[10], '%Y%m%d').date()
    except ValueError:
        return None
    if not since <= opened <= until:
        return None
    # Nome fantasia ausente: preservar identificação sem inventar razão social.
    cnpj = ''.join(row[:3])
    item = dict(cnpj=cnpj, name=row[4].strip() or 'Empresa CNPJ ' + cnpj,
                opened=opened.isoformat(), city=row[20], state=row[19], source=source)
    try:
        item['email'] = email_value(row[27])
    except ValueError:
        item['email'] = None
    return item


def import_zip(path, since, until, competence):
    datetime.strptime(competence, '%Y-%m')
    if since > until or until > date.today():
        raise ValueError('Intervalo inválido')
    with open(path, 'rb') as archive_file:
        digest = hashlib.file_digest(archive_file, 'sha256').hexdigest()
    key = 'rfb:' + digest + ':' + since.isoformat() + ':' + until.isoformat()
    source = 'RFB dados abertos CNPJ; competencia=' + competence + '; sha256=' + digest
    init()
    with db() as c:
        if c.execute('SELECT 1 FROM settings WHERE key=?', (key,)).fetchone():
            return {'already_imported': True}
    count = 0
    # Validate ZIP structure first; never extract untrusted paths to disk.
    with zipfile.ZipFile(path) as archive:
        members = [i for i in archive.infolist() if not i.is_dir()]
        if not members:
            raise ValueError('ZIP vazio')
        for member in members:
            with archive.open(member) as stream:
                rows = csv.reader(io.TextIOWrapper(stream, encoding='latin-1'), delimiter=';')
                batch = []
                for row in rows:
                    item = parse_row(row, since, until, source)
                    if item:
                        batch.append(item)
                    if len(batch) >= 1000:
                        persist(batch)
                        count += len(batch)
                        batch.clear()
                persist(batch)
                count += len(batch)
    # Completed only after all members and their CRCs have been read successfully.
    with db() as c:
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',
                  (key, json.dumps({'competence': competence, 'records': count, 'finished': now()})))
    return {'imported': count, 'competence': competence, 'contacts_require_review': True}


def persist(items):
    with db() as c:
        for item in items:
            cnpj = save_company(c, item)
            # Preserve operator-verified addresses; source email is only a candidate.
            c.execute('UPDATE companies SET email=? WHERE cnpj=? AND contact_verified=0',
                      (item['email'], cnpj))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--since', required=True, type=date.fromisoformat)
    parser.add_argument('--until', required=True, type=date.fromisoformat)
    parser.add_argument('--competence', required=True)
    args = parser.parse_args()
    for archive in args.archives:
        print(json.dumps(import_zip(archive, args.since, args.until, args.competence)))
