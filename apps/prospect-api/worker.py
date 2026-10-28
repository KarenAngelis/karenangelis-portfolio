"""One worker per database. Holds an OS lock; crash ambiguity requires manual reconciliation."""
import fcntl
import logging
import os
import time
from pathlib import Path
import httpx
from core import init, db, daily_schedule, collect_page, queue
from mailer import send_one
from contact_validation import validate_batch

logging.basicConfig(level=logging.INFO)

def run():
    init()
    lock_path = Path(os.getenv('PROSPECT_DB','/data/prospect.sqlite3')).with_suffix('.worker.lock')
    with lock_path.open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        with db() as c:
            c.execute("UPDATE messages SET status='unknown',error='WorkerInterrupted' WHERE status='sending'")
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            while True:
                try:
                    if os.getenv("COLLECT_PROVIDER", "rfb") == "casa_dados":
                        daily_schedule()
                        collect_page(client)
                    validate_batch()
                    if os.getenv('AUTO_QUEUE_VERIFIED') == 'true':
                        with db() as c:
                            for r in c.execute('SELECT cnpj FROM companies WHERE contact_verified=1 AND cnpj NOT IN (SELECT cnpj FROM messages) AND email NOT IN (SELECT email FROM suppression) LIMIT 500').fetchall():
                                queue(c,r['cnpj'])
                    send_one()
                except Exception as exc:
                    logging.error('Worker iteration failed: %s',type(exc).__name__)
                time.sleep(max(1,int(os.getenv('WORKER_INTERVAL_SECONDS','10'))))

if __name__ == '__main__':
    run()
