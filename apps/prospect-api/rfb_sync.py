"""Periodic official RFB discovery/download/import, isolated from the SMTP worker."""
import fcntl
import json
import logging
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
import httpx
from core import db, init, now
from rfb_import import import_zip

BASE = 'https://arquivos.receitafederal.gov.br/public.php/webdav/'
# Public Nextcloud share identifier, not a user credential.
SHARE = 'YggdBLfdninEJX9'


def listing(client, url):
    response = client.request('PROPFIND', url, headers={'Depth': '1'})
    response.raise_for_status()
    result = []
    for item in ET.fromstring(response.content).findall('{DAV:}response'):
        href = item.findtext('{DAV:}href') or ''
        target = urljoin(BASE, href)
        if urlparse(target).netloc != urlparse(BASE).netloc:
            raise ValueError('Unexpected download host')
        result.append((target, unquote(urlparse(target).path).rstrip('/').split('/')[-1],
                       int(item.findtext('.//{DAV:}getcontentlength') or 0),
                       item.findtext('.//{DAV:}getetag') or ''))
    return result


def download(client, url, path, size):
    if size <= 0 or size > 4 * 1024**3:
        raise ValueError('Invalid archive size')
    if shutil.disk_usage(path.parent).free < size + 1024**3:
        raise OSError('Insufficient disk space')
    partial = path.with_suffix('.part')
    try:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            with partial.open('wb') as output:
                total = 0
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > size:
                        raise ValueError('Archive larger than manifest')
                    output.write(chunk)
        if total != size:
            raise ValueError('Incomplete archive')
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def sync(client, cache):
    months = [r for r in listing(client, BASE) if re.fullmatch(r'20\d{2}-\d{2}', r[1])]
    if not months:
        raise ValueError('No official competence found')
    month = max(months, key=lambda r: r[1])
    first = date.fromisoformat(month[1] + '-01')
    since = date.fromisoformat(os.getenv('RFB_SINCE', (first-timedelta(days=60)).isoformat()))
    until = date.today()
    archives = [r for r in listing(client, month[0].rstrip('/')+'/')
                if re.fullmatch(r'Estabelecimentos\d\.zip', r[1])]
    if len(archives) != 10:
        raise ValueError('Incomplete official manifest')
    for url, name, size, etag in sorted(archives, key=lambda r:r[2]):
        key = 'rfb_download:' + month[1] + ':' + name
        version = json.dumps([etag, size, since.isoformat()])
        with db() as c:
            old = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if old and old[0] == version:
            continue
        with db() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES('rfb_sync_status',?)",
                      (json.dumps({'status':'downloading','file':name,'competence':month[1],'updated':now()}),))
        path = cache / name
        download(client, url, path, size)
        result = import_zip(path, since, until, month[1])
        with db() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, version))
        path.unlink()
        logging.info('Imported %s: %s', name, result)
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES('rfb_sync_status',?)",
                  (json.dumps({'status':'complete','competence':month[1],'updated':now()}),))


def run():
    interval = max(300, int(os.getenv('RFB_CHECK_INTERVAL_SECONDS', '3600')))
    init()
    cache = Path(os.getenv('PROSPECT_DB','/data/prospect.sqlite3')).parent / 'rfb-cache'
    cache.mkdir(exist_ok=True)
    with (cache/'sync.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            if os.getenv('RFB_SYNC_ENABLED') == 'true':
                try:
                    with httpx.Client(auth=(SHARE,''), timeout=120, follow_redirects=False) as client:
                        sync(client, cache)
                except Exception as exc:
                    logging.error('RFB sync failed: %s', type(exc).__name__)
                    with db() as c:
                        c.execute("INSERT OR REPLACE INTO settings VALUES('rfb_sync_status',?)",
                                  (json.dumps({'status':'error','error':type(exc).__name__,'updated':now()}),))
                    time.sleep(3600)
                    continue
            time.sleep(interval)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run()
