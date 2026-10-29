"""Public employer feeds. No search broker, paid key, or Google credentials.

Sources are an operator-maintained allowlist, not arbitrary spreadsheet URLs.
Imported listings are untrusted data and always require application triage.
"""
import hashlib
import html
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit, urljoin
import httpx

ROOT = Path(__file__).parent
USER_AGENT = 'KarenJobs/1.0 (+https://karenangelis.com/api/jobs/oauth/privacy)'
MAX_BYTES = 12_000_000
PAGE_SIZE = 200
MAX_PAGES = 15


class SourceError(Exception):
    pass


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if not self.hidden and tag in ('p', 'li', 'br', 'div', 'h1', 'h2', 'h3', 'section'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in ('p', 'li', 'div', 'h1', 'h2', 'h3', 'section'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value):
    parser = TextParser()
    # Greenhouse can return entity-escaped HTML.
    parser.feed(html.unescape(str(value or '')))
    return '\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip())


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


def fingerprint(company, title):
    return normalized(company), normalized(title)


def endpoint(source):
    board = quote(source.get('board', ''), safe='')
    if source['type'] == 'lever':
        return 'https://api.lever.co/v0/postings/' + board
    if source['type'] == 'greenhouse':
        return 'https://boards-api.greenhouse.io/v1/boards/' + board + '/jobs'
    if source['type'] == 'ashby':
        return 'https://api.ashbyhq.com/posting-api/job-board/' + board
    if source['type'] == 'html':
        url = source['url']
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in {'apto.vc', 'www.devinterface.com', 'www.remediagroup.it'}:
            raise SourceError('Unapproved career host')
        return url
    raise SourceError('Unknown source type')


def download(client, url, params=None):
    """Do not follow off-host redirects or retry throttling/challenges."""
    origin = urlsplit(url).hostname
    for _ in range(4):
        with client.stream('GET', url, params=params) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                next_url = urljoin(str(response.url), response.headers.get('location', ''))
                target = urlsplit(next_url)
                if target.scheme != 'https' or target.hostname != origin:
                    raise SourceError('Off-host redirect')
                url, params = next_url, None
                continue
            if response.status_code != 200:
                raise SourceError('HTTP ' + str(response.status_code))
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise SourceError('Response too large')
                chunks.append(chunk)
            return b''.join(chunks).decode('utf-8')
    raise SourceError('Redirect limit')


class Sections(HTMLParser):
    """Extract visible h2/h3 job sections from employer career pages."""
    def __init__(self, level, title_tag=None):
        super().__init__()
        self.level = level
        self.title_tag = title_tag
        self.title_parts = []
        self.in_title = False
        self.heading = None
        self.title = None
        self.body = []
        self.items = []
        self.hidden = 0

    def finish(self):
        if self.title:
            self.items.append({'title': ' '.join(self.title.split()), 'description': ''.join(self.body)})
        self.title, self.body = None, []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if self.hidden:
            return
        if tag == self.level:
            self.finish()
            self.heading = []
            self.title_parts = []
        elif self.heading is not None and tag == self.title_tag:
            self.in_title = True
        elif tag in ('p', 'li', 'br', 'div', 'h3', 'h4', 'section'):
            self.body.append('\n')
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith('mailto:'):
                self.body.append(' ' + href[7:].split('?')[0] + ' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden-1)
            return
        if tag == self.level and self.heading is not None:
            self.title = ' '.join(self.title_parts or self.heading)
            self.body.append(' '.join(self.heading) + '\n')
            self.heading = None
            self.in_title = False
        elif tag == self.title_tag:
            self.in_title = False
        elif tag in ('p', 'li', 'div', 'section'):
            self.body.append('\n')

    def handle_data(self, data):
        if self.hidden:
            return
        if self.heading is not None:
            self.heading.append(data)
            if self.in_title:
                self.title_parts.append(data)
        elif self.title is not None:
            self.body.append(data)


def parse_jobs(source, payload):
    kind = source['type']
    if kind == 'html':
        parser = Sections(source['heading'], source.get('title_tag'))
        parser.feed(payload)
        parser.finish()
        if not parser.items:
            raise SourceError('Career page has no recognizable sections')
        for entry in parser.items:
            yield {**entry, 'id': normalized(entry['title']), 'url': source['url'],
                   'location': source['country'], 'workplace': '', 'contract': ''}
        return
    data = json.loads(payload)
    items = data if kind == 'lever' else data.get('jobs')
    if not isinstance(items, list):
        raise SourceError('Unexpected feed schema')
    for item in items:
        if kind == 'lever':
            cat = item.get('categories') or {}
            details = '\n'.join(str(p.get('text', '')) + '\n' + plain(p.get('content', '')) for p in item.get('lists', []))
            yield {'id': str(item['id']), 'title': item['text'],
                   'description': '\n'.join([item.get('descriptionPlain') or plain(item.get('description')), details,
                                              item.get('additionalPlain') or plain(item.get('additional'))]),
                   'location': ' / '.join(cat.get('allLocations') or [cat.get('location', '')]) + ' / ' + (item.get('country') or ''),
                   'url': item.get('applyUrl') or item.get('hostedUrl', ''),
                   'workplace': item.get('workplaceType', ''), 'contract': cat.get('commitment', '')}
        elif kind == 'greenhouse':
            yield {'id': str(item['id']), 'title': item['title'], 'description': plain(item.get('content')),
                   'location': (item.get('location') or {}).get('name', ''), 'url': item.get('absolute_url', ''),
                   'workplace': '', 'contract': ''}
        elif kind == 'ashby':
            if item.get('isListed') is False:
                continue
            locations = [item.get('location', '')] + [p.get('location', '') for p in item.get('secondaryLocations', [])]
            yield {'id': item.get('id') or item['jobUrl'], 'title': item['title'],
                   'description': item.get('descriptionPlain') or plain(item.get('descriptionHtml')),
                   'location': ' / '.join(locations), 'url': item.get('applyUrl') or item.get('jobUrl', ''),
                   'workplace': 'remote' if item.get('isRemote') else item.get('workplaceType', ''),
                   'contract': item.get('employmentType', '')}


def fetch_jobs(source, client):
    url = endpoint(source)
    if source['type'] != 'lever':
        params = {'content': 'true'} if source['type'] == 'greenhouse' else None
        return list(parse_jobs(source, download(client, url, params)))
    result, seen = [], set()
    for page in range(MAX_PAGES):
        payload = download(client, url, {'mode': 'json', 'limit': PAGE_SIZE, 'skip': page * PAGE_SIZE})
        jobs = list(parse_jobs(source, payload))
        if jobs and all(j['id'] in seen for j in jobs):
            raise SourceError('Pagination repeated a page')
        for job in jobs:
            if job['id'] not in seen:
                result.append(job)
                seen.add(job['id'])
        if len(jobs) < PAGE_SIZE:
            return result
    raise SourceError('Pagination capacity reached; increase explicitly')


def countries(location):
    text = normalized(location)
    result = []
    aliases = {
        'BR': r'\b(br|brazil|brasil|sao paulo|rio de janeiro|belo horizonte|latam|latin america)\b',
        'PT': r'\b(pt|portugal|lisbon|lisboa|porto)\b',
        'IT': r'\b(it|italy|italia|milan|milano|rome|roma|bologna|torino|genova)\b',
    }
    for country, pattern in aliases.items():
        if re.search(pattern, text):
            result.append(country)
    if not result and re.search(r'\b(worldwide|anywhere|global|emea|europe)\b', text):
        # Market scope only, never proof of work authorization or cross-border hiring.
        result = ['BR', 'PT', 'IT'] if re.search(r'worldwide|anywhere|global', text) else ['PT', 'IT']
    return result


def role_matches(title):
    text = normalized(title)
    if re.search(r'\b(senior|sr|staff|principal|lead|manager|director|head|master|junior|jr|intern|trainee|estagio|graduate)\b', text):
        # Include explicitly mixed Mid/Senior opportunities for review, not senior-only.
        if not re.search(r'\b(pleno|mid|middle|intermediate)\b', text):
            return False
    return bool(re.search(r'\b(full\s?stack|front\s?end|back\s?end|database|banco de dados|sql developer|web developer|sviluppatore web)\b', text))


def email_candidates(description):
    matches = []
    for match in re.finditer(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', description):
        context = normalized(description[max(0, match.start()-140):match.end()+100])
        email = match.group().lower()
        if re.search(r'privac|gdpr|accommodat|accessib|dpo|support|suporte', context):
            continue
        if re.search(r'candidat|curricul|resume|apply|application|cv|recrut|recruit|carreir|jobs', context):
            matches.append(email)
    return sorted(set(matches))


def to_row(source, job, now=None):
    now = now or datetime.now(timezone.utc).isoformat()
    if not role_matches(job['title']):
        return None
    markets = countries(job['location'])
    if not markets:
        return None
    text = job['description']
    if not text.strip() or not job['url'].startswith('https://'):
        return None
    place = normalized(job.get('workplace', '') + ' ' + job['location'])
    if re.search(r'\b(hybrid|hibrid|on site|onsite|presencial)\b', place):
        return None
    remote = bool(re.search(r'\b(remote|remoto|remota|telecommute)\b', place))
    if not remote:
        lead = normalized(text[:1500])
        if re.search(r'\b(hybrid|hibrid|on site|onsite|presencial)\b', lead):
            return None
        remote = bool(re.search(r'\b(remote|remoto|remota|telecommute)\b', lead))
    emails = email_candidates(text)
    country = markets[0]
    notes = ('Coleta direta; TRIAGEM PENDENTE. Confirmar vigência, requisitos, idioma, anexos, '
             'canal e contratação a partir do Brasil. Mercados indicados: ' + ', '.join(markets) +
             '. Localização original: ' + job['location'])
    if emails:
        notes += '. E-mail candidato extraído do anúncio, sujeito a confirmação.'
    return {
        'ID': 'direct-' + hashlib.sha256((source['id'] + ':' + job['id']).encode()).hexdigest(),
        'Empresa': source['company'], 'Vaga': job['title'], 'País': country,
        'Contrato': job.get('contract') or 'A confirmar',
        'Modalidade': 'Remoto' if remote else 'A confirmar',
        'Nível': 'Pleno' if re.search(r'\b(pleno|mid|middle|intermediate)\b', normalized(job['title'])) else 'A confirmar',
        'Idioma': {'BR': 'pt-BR', 'PT': 'pt-PT', 'IT': 'it'}[country],
        'Canal': 'E-mail' if len(emails) == 1 else 'Link',
        'E-mail': emails[0] if len(emails) == 1 else '', 'Link da candidatura': job['url'],
        'Status': 'Triagem', 'Fonte': source['url'], 'Descrição': text[:45000],
        'Observações': notes, 'Atualizado em': now,
        'Próxima ação': 'Validar elegibilidade e instruções antes de candidatar',
    }


def collect_direct(sheet, sources=None, client=None, now=None, force=False):
    """Import each source independently; history is restart-safe schedule state."""
    now = time.time() if now is None else now
    sources = sources if sources is not None else json.loads((ROOT/'sources.json').read_text())
    history = sheet.history()
    existing = sheet.read_jobs()
    seen = {r['ID'] for r in existing}
    fingerprints = {fingerprint(r['Empresa'], r['Vaga']) for r in existing}
    report = []
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False,
                                   headers={'User-Agent': USER_AGENT})
    try:
        for source in sources:
            if source.get('enabled', True) is False:
                continue
            marker = 'direct-source-' + source['id']
            last = [datetime.fromisoformat(r[0]).timestamp() for r in history
                    if r[1] == marker and r[3] == 'DIRECT_ATTEMPT']
            interval = max(3600, int(source.get('interval_seconds', 21600)))
            if not force and last and max(last) > now - interval:
                continue
            timestamp = datetime.now(timezone.utc).isoformat()
            sheet.append_history(timestamp, marker, 'DIRECT_ATTEMPT', '', '', source['url'])
            try:
                jobs = fetch_jobs(source, client)
                rows, pending_ids, pending_fingerprints = [], set(), set()
                for job in jobs:
                    row = to_row(source, job)
                    if not row:
                        continue
                    key = fingerprint(row['Empresa'], row['Vaga'])
                    if row['ID'] in seen or row['ID'] in pending_ids or key in fingerprints or key in pending_fingerprints:
                        continue
                    rows.append(row)
                    pending_ids.add(row['ID'])
                    pending_fingerprints.add(key)
                sheet.append_jobs(rows)
                seen.update(pending_ids)
                fingerprints.update(pending_fingerprints)
                summary = {'source': source['id'], 'fetched': len(jobs), 'imported': len(rows)}
                sheet.append_history(datetime.now(timezone.utc).isoformat(), marker, 'DIRECT_COMPLETE', '', '', json.dumps(summary))
                report.append(summary)
            except Exception as exc:
                # Public diagnostic only; never log private response bodies or credentials.
                reason = str(exc) if isinstance(exc, SourceError) else type(exc).__name__
                summary = {'source': source['id'], 'error': reason}
                sheet.append_history(datetime.now(timezone.utc).isoformat(), marker, 'DIRECT_ERROR', '', '', json.dumps(summary))
                report.append(summary)
    finally:
        if owns_client:
            client.close()
    return report


if __name__ == '__main__':
    # Read-only live probe: no OAuth, Sheet writes, e-mails or source API keys.
    for source in json.loads((ROOT/'sources.json').read_text()):
        if not source.get('enabled', True):
            continue
        try:
            with httpx.Client(timeout=35, headers={'User-Agent': USER_AGENT}) as client:
                jobs = fetch_jobs(source, client)
            rows = [row for job in jobs if (row := to_row(source, job))]
            print(json.dumps({'source': source['id'], 'fetched': len(jobs), 'matched': len(rows),
                              'examples': [{'title': r['Vaga'], 'country': r['País'], 'channel': r['Canal'],
                                            'url': r['Link da candidatura']} for r in rows[:3]]}), flush=True)
        except Exception as exc:
            print(json.dumps({'source': source['id'], 'error': str(exc) if isinstance(exc, SourceError) else type(exc).__name__}), flush=True)
