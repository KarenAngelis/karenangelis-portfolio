"""Read-only adapters for public company job boards and public GitHub repositories."""
import base64
import html
import re
from html.parser import HTMLParser

import httpx

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = Text()
    parser.feed(html.unescape(str(value or "")))
    return " ".join(parser.parts)[:40000]


def source_spec(data):
    kind, identifier = data.get("kind"), data.get("identifier", "")
    if kind not in {"greenhouse", "lever"} or not IDENTIFIER.fullmatch(identifier):
        raise ValueError("Escolha Greenhouse ou Lever e informe o identificador da empresa.")
    return {"kind": kind, "identifier": identifier}


async def fetch_jobs(source, client=None):
    source = source_spec(source)
    kind, identifier = source["kind"], source["identifier"]
    url = (f"https://boards-api.greenhouse.io/v1/boards/{identifier}/jobs?content=true"
           if kind == "greenhouse" else f"https://api.lever.co/v0/postings/{identifier}?mode=json")
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=25, follow_redirects=False)
    try:
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        if len(response.content) > 8_000_000:
            raise ValueError("Fonte excedeu o tamanho permitido.")
        payload = response.json()
        entries = payload.get("jobs", []) if kind == "greenhouse" else payload
        if not isinstance(entries, list):
            raise ValueError("Fonte retornou formato inválido.")
        result = []
        for item in entries[:2000]:
            categories = item.get("categories") or {}
            sections = " ".join(str(block.get("text", "")) + " " + str(block.get("content", ""))
                                for block in item.get("lists", []) if isinstance(block, dict))
            description = plain(item.get("content") if kind == "greenhouse" else
                                str(item.get("descriptionPlain", "")) + " " + sections + " " + str(item.get("additionalPlain", "")))
            emails = EMAIL.findall(description)
            result.append({
                "source": f"{kind}:{identifier}", "external_id": str(item["id"]),
                "company": identifier, "title": item.get("title", item.get("text", "Vaga")),
                "url": item.get("absolute_url", item.get("hostedUrl", "")),
                "apply_url": item.get("applyUrl", item.get("absolute_url", "")),
                "description": description,
                "location": (item.get("location") or {}).get("name", "") if kind == "greenhouse" else categories.get("location", ""),
                "workplace_type": item.get("workplaceType", ""),
                "apply_email": emails[0] if len(set(emails)) == 1 else None,
                "contact_source": "official_job_description" if len(set(emails)) == 1 else None,
            })
        return result
    finally:
        if own_client:
            await client.aclose()


async def github_projects(username, client=None):
    if not isinstance(username, str) or not IDENTIFIER.fullmatch(username):
        raise ValueError("Usuário GitHub inválido.")
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=False)
    try:
        projects = []
        for page in range(1, 6):
            response = await client.get(f"https://api.github.com/users/{username}/repos",
                                        params={"per_page": 100, "page": page, "sort": "updated"},
                                        headers={"Accept": "application/vnd.github+json"})
            response.raise_for_status()
            repos = response.json()
            for repo in repos:
                if repo.get("fork") or repo.get("archived"):
                    continue
                projects.append({"name": repo["name"], "url": repo["html_url"],
                                 "description": repo.get("description"), "language": repo.get("language"),
                                 "updated_at": repo.get("pushed_at"), "source": "github_public_metadata"})
            if len(repos) < 100:
                break
        # Read representative current READMEs, without interpreting them as proof of production use.
        for project in projects[:12]:
            name = project["name"]
            response = await client.get(f"https://api.github.com/repos/{username}/{name}/readme",
                                        headers={"Accept": "application/vnd.github+json"})
            if response.status_code == 200:
                data = response.json()
                if data.get("encoding") == "base64":
                    project["readme"] = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")[:10000]
        return projects
    finally:
        if own_client:
            await client.aclose()
