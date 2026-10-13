"""Acrescenta as rotas e o script de estatísticas a uma publicação já existente.

Executar na VPS após transferir os arquivos novos. Sem --apply, mostra o plano.
Não altera o proxy externo nem cria a senha do painel.
"""

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


TRACK = '<script type="module" src="/assets/track.js"></script>'
TRUSTED_PROXIES = """{
    servers {
        trusted_proxies static private_ranges
    }
}
"""
STATS_ROUTE = """    handle /api/stats/* {
        reverse_proxy stats-api:8001
    }
"""
STATS_SERVICE = """  stats-api:
    build:
      context: .
      dockerfile: apps/stats-api/Dockerfile
    restart: unless-stopped
    volumes:
      - stats_data:/data
volumes:
  stats_data:
"""


def insert_once(body: str, marker: str, addition: str, label: str) -> str:
    if body.count(marker) != 1:
        raise ValueError(f"{label}: marcador encontrado {body.count(marker)} vezes")
    return body.replace(marker, addition + marker, 1)


def changes(root: Path) -> dict[Path, str]:
    planned = {}
    compose = root / "compose.vps.yaml"
    original = compose.read_text(encoding="utf-8")
    body = original
    if "  stats-api:" not in body:
        if "\nvolumes:" in body:
            raise ValueError("compose.vps.yaml já tem volumes; revisar manualmente")
        body = insert_once(body, "      - resume-api\n", "      - stats-api\n", str(compose))
        body = body.rstrip("\n") + "\n" + STATS_SERVICE
    else:
        body = body.replace("    environment:\n      STATS_TOKEN: ${STATS_TOKEN:-}\n", "")
    if body != original:
        planned[compose] = body

    caddy = root / "infra/Caddyfile"
    body = caddy.read_text(encoding="utf-8")
    if "handle /api/stats/*" not in body:
        body = insert_once(body, "    handle /api/profile {", STATS_ROUTE, str(caddy))
        if "trusted_proxies static private_ranges" not in body:
            if body.lstrip().startswith("{\n"):
                raise ValueError("Caddyfile já tem opções globais; revisar manualmente")
            body = TRUSTED_PROXIES + body
        planned[caddy] = body

    pages = sorted((root / "web").rglob("index.html"))
    app_source = root / "apps/resume-compose/shared/src/wasmJsMain/resources/index.html"
    if app_source.exists():
        pages.append(app_source)
    for page in pages:
        if page.parent.name == "painel":
            continue
        body = page.read_text(encoding="utf-8")
        if TRACK not in body:
            planned[page] = insert_once(body, "</head>", TRACK, str(page))
    return planned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/opt/karenangelis-portfolio"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    planned = changes(root)
    print(f"{len(planned)} arquivos a alterar:")
    for path in planned:
        print(" ", path.relative_to(root))
    if not args.apply or not planned:
        return
    backup = root.parent / f"{root.name}-stats-backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    backup.mkdir(mode=0o700)
    for path, body in planned.items():
        saved = backup / path.relative_to(root)
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
        path.write_text(body, encoding="utf-8")
    print("Backup:", backup)


if __name__ == "__main__":
    main()
