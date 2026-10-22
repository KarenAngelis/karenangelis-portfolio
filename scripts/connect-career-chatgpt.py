#!/usr/bin/env python3
"""Pair this OSS career manager with ChatGPT using the official local SIWC flow.

Install apps/career-api/requirements-chatgpt-setup.txt, then run this on the computer
with your browser. Credentials stay in app-specific user configuration storage.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import uuid
import webbrowser

import httpx
import jwt

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
DIRECT_SCOPES = {"offline_access", "resource.invoke", "chatgpt.tokens.use.direct"}
CALLBACK_PATH = "/auth/callback"
APP_NAME = "karen_career_manager"  # Matches app-server initialize.clientInfo.name.
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class SetupError(RuntimeError):
    """Safe console error: never include OAuth codes, URLs with hints or tokens."""


def safe_destination(path: Path) -> None:
    if path.resolve().is_relative_to(REPOSITORY_ROOT):
        raise SetupError("Salve as credenciais fora do repositório, em configuração privada do usuário.")
    if path.name.casefold() == "auth.json":
        raise SetupError("Escolha um registro próprio desta aplicação; auth.json do Codex não é aceito.")


def default_output() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "karen-career-manager" / "credentials.json"


def protected_read(path: Path, *, as_json=True):
    if path.is_symlink():
        raise SetupError("Use um arquivo regular protegido, sem link simbólico.")
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "r", encoding="utf-8") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise SetupError("Use um arquivo regular protegido.")
            if os.name != "nt" and (metadata.st_mode & 0o077 or metadata.st_uid != os.getuid()):
                raise SetupError("O arquivo deve pertencer a você e ter permissão 0600.")
            text = stream.read(128001)
            if len(text) > 128000:
                raise SetupError("O arquivo de registro excedeu o tamanho permitido.")
            return json.loads(text) if as_json else text.strip()
    except (OSError, UnicodeError, ValueError):
        raise SetupError("Não foi possível ler o registro local protegido.") from None


def load_existing(path: Path, replace=False) -> dict | None:
    safe_destination(path)
    if not path.exists() and not path.is_symlink():
        return None
    if not replace:
        raise SetupError("Já existe um registro nesse destino. Use --replace para reautorizar a mesma conta.")
    existing = protected_read(path)
    if (not isinstance(existing, dict) or existing.get("issuer") != ISSUER or not existing.get("subject")
            or not existing.get("client_id") or existing["client_id"] == "dynamic_agent_client"):
        raise SetupError("O destino existente não contém um registro SIWC próprio válido.")
    return existing


def prepare_host(output: Path) -> str:
    path = output.parent / "host-id"
    if path.exists() or path.is_symlink():
        value = protected_read(path, as_json=False)
        try:
            if not value.startswith("urn:uuid:"):
                raise ValueError()
            uuid.UUID(value.removeprefix("urn:uuid:"))
            return value
        except (ValueError, TypeError):
            raise SetupError("O identificador local do host é inválido; preserve o arquivo original.") from None
    try:
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if output.parent.is_symlink():
            raise SetupError("O diretório do registro não pode ser um link simbólico.")
        value = "urn:uuid:" + str(uuid.uuid4())
        with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="utf-8") as stream:
            stream.write(value + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return value
    except FileExistsError:
        return prepare_host(output)
    except OSError:
        raise SetupError("Não foi possível preparar o diretório privado de configuração.") from None


def transaction(redirect_uri: str, host_id: str, existing: dict | None = None) -> dict:
    parsed = urlsplit(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path != CALLBACK_PATH or not parsed.port:
        raise SetupError("O callback deve usar HTTP loopback em 127.0.0.1 e /auth/callback.")
    verifier = secrets.token_urlsafe(64)
    return {"state": secrets.token_urlsafe(32), "nonce": secrets.token_urlsafe(32), "verifier": verifier,
            "challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="),
            "redirect_uri": redirect_uri, "host_id": host_id,
            "client_id": existing["client_id"] if existing else "dynamic_agent_client",
            "created_at": time.monotonic(), "consumed": False}


def authorization_url(attempt: dict, existing: dict | None = None) -> str:
    parameters = {"client_id": attempt["client_id"], "ext_agent_host_id": attempt["host_id"],
                  "response_type": "code", "redirect_uri": attempt["redirect_uri"], "scope": SCOPES,
                  "resource": RESOURCE, "state": attempt["state"], "nonce": attempt["nonce"],
                  "code_challenge_method": "S256", "code_challenge": attempt["challenge"]}
    if existing:
        if existing.get("id_token"):
            parameters["id_token_hint"] = existing["id_token"]
        if existing.get("email"):
            parameters["login_hint"] = existing["email"]
    else:
        parameters["agent_name_hint"] = APP_NAME
    return AUTHORIZE + "?" + urlencode(parameters)


def consume_callback(attempt: dict, query: dict) -> tuple[str, str]:
    if attempt.get("consumed"):
        raise SetupError("Este retorno de autenticação já foi utilizado.")
    attempt["consumed"] = True
    returned_state = query.get("state", "")
    if (time.monotonic() - attempt["created_at"] > 300 or not isinstance(returned_state, str)
            or not hmac.compare_digest(attempt["state"], returned_state)):
        raise SetupError("O retorno de autenticação não pôde ser validado.")
    if query.get("error"):
        raise SetupError("A autorização não foi concluída. Nenhuma credencial foi salva.")
    code = query.get("code")
    if not isinstance(code, str) or not code:
        raise SetupError("O retorno não contém o código de autorização esperado.")
    selected = attempt["client_id"]
    issued = query.get("client_id")
    if selected == "dynamic_agent_client":
        if not isinstance(issued, str) or not issued or issued == "dynamic_agent_client":
            raise SetupError("O registro não retornou um client_id emitido pela OpenAI.")
        selected = issued
    elif issued and issued != selected:
        raise SetupError("O registro retornado difere da conta selecionada.")
    return code, selected


def response_json(response) -> dict:
    if response.status_code != 200:
        raise SetupError("A OpenAI não concluiu a operação de autenticação. Tente novamente pelo fluxo oficial.")
    try:
        result = response.json()
    except (ValueError, UnicodeError):
        raise SetupError("A autenticação retornou um formato inesperado.") from None
    if not isinstance(result, dict):
        raise SetupError("A autenticação retornou um formato inesperado.")
    return result


def validate_identity(client, id_token: str, client_id: str, nonce: str) -> dict:
    configuration = response_json(client.get(DISCOVERY))
    jwks_url = configuration.get("jwks_uri", "")
    parsed = urlsplit(jwks_url)
    if (configuration.get("issuer") != ISSUER or parsed.scheme != "https" or parsed.hostname != "auth.openai.com"
            or parsed.username or parsed.password or parsed.fragment):
        raise SetupError("A configuração oficial de identidade não pôde ser validada.")
    keys = response_json(client.get(jwks_url)).get("keys", [])
    try:
        header = jwt.get_unverified_header(id_token)
        algorithm = header.get("alg")
        if algorithm not in {"RS256", "ES256"} or not header.get("kid"):
            raise ValueError()
        candidates = [key for key in keys if isinstance(key, dict) and key.get("kid") == header["kid"]
                      and key.get("use", "sig") == "sig" and key.get("alg", algorithm) == algorithm]
        if len(candidates) != 1:
            raise ValueError()
        key = jwt.PyJWK.from_dict(candidates[0], algorithm=algorithm).key
        identity = jwt.decode(id_token, key, algorithms=[algorithm], issuer=ISSUER, audience=client_id,
                              leeway=5, options={"require": ["sub", "exp", "iat", "nonce"]})
        if not isinstance(identity.get("sub"), str) or not identity["sub"]:
            raise ValueError()
        if not isinstance(identity.get("nonce"), str) or not hmac.compare_digest(identity["nonce"], nonce):
            raise ValueError()
        audiences = identity.get("aud")
        if identity.get("azp") not in (None, client_id) or (isinstance(audiences, list) and len(audiences) > 1 and identity.get("azp") != client_id):
            raise ValueError()
        return identity
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise SetupError("A assinatura ou a identidade retornada pela OpenAI não pôde ser validada.") from None


def exchange_registration(client, attempt: dict, query: dict, existing: dict | None = None) -> dict:
    code, client_id = consume_callback(attempt, query)
    tokens = response_json(client.post(TOKEN, data={"grant_type": "authorization_code", "client_id": client_id,
        "code": code, "code_verifier": attempt["verifier"], "redirect_uri": attempt["redirect_uri"], "resource": RESOURCE}))
    if not isinstance(tokens.get("id_token"), str):
        raise SetupError("A autenticação não retornou um ID token verificável.")
    identity = validate_identity(client, tokens["id_token"], client_id, attempt["nonce"])
    if existing and (identity["sub"] != existing["subject"] or client_id != existing["client_id"]):
        raise SetupError("A conta autenticada difere do registro selecionado. O arquivo anterior foi preservado.")
    scopes = tokens.get("scope", "")
    granted = set(scopes.split()) if isinstance(scopes, str) else set()
    if not DIRECT_SCOPES.issubset(granted):
        raise SetupError("Autorize o uso do plano ChatGPT e o acesso offline para concluir o pareamento.")
    if any(not isinstance(tokens.get(key), str) or not tokens[key] for key in ("access_token", "refresh_token")):
        raise SetupError("A autenticação não retornou as credenciais necessárias ao runtime próprio.")
    duration = tokens.get("expires_in")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise SetupError("A validade das credenciais retornadas não pôde ser validada.")
    result = {"issuer": ISSUER, "subject": identity["sub"], "client_id": client_id,
              "email": identity.get("email"), "ext_agent_host_id": attempt["host_id"],
              "scopes": sorted(granted), "saved_at": datetime.now(timezone.utc).isoformat()}
    result.update({key: tokens[key] for key in ("id_token", "access_token", "refresh_token", "expires_in", "token_type", "earliest_refresh_at") if key in tokens})
    return result


def save_registration(path: Path, data: dict, replace=False) -> None:
    safe_destination(path)
    if path.name.casefold() == "auth.json" or path.is_symlink() or path.parent.is_symlink():
        raise SetupError("Escolha um arquivo próprio protegido para esta aplicação.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".siwc-", dir=path.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), 0o600)
            else:
                os.chmod(temporary, 0o600)
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Atomic no-overwrite creation, even if another process created the
            # destination after our initial check. Both files share a directory.
            os.link(temporary, path)
            os.unlink(temporary)
        temporary = None
    except FileExistsError:
        raise SetupError("O destino já existe. O arquivo anterior foi preservado.") from None
    except (OSError, ValueError, TypeError):
        raise SetupError("Não foi possível salvar o registro no destino protegido.") from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def connect(output: Path, replace=False, client=None, browser_open=None) -> dict:
    existing = load_existing(output, replace=replace)
    host_id = prepare_host(output)
    captured = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # HTTP request URLs include authorization codes; never log them.

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != CALLBACK_PATH or captured:
                self.send_error(404)
                return
            values = parse_qs(parsed.query, keep_blank_values=True)
            if any(len(value) != 1 for value in values.values()):
                captured["error"] = SetupError("O retorno de autenticação contém parâmetros ambíguos.")
            else:
                captured["query"] = {key: value[0] for key, value in values.items()}
            body = "Retorno recebido. Volte ao terminal para conferir o resultado do pareamento.".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        with HTTPServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = 1
            attempt = transaction(f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}", host_id, existing)
            opener = browser_open or webbrowser.open
            try:
                opened = opener(authorization_url(attempt, existing), new=1)
            except webbrowser.Error:
                opened = False
            if not opened:
                raise SetupError("Não foi possível abrir o navegador. Execute o helper no computador com seu navegador padrão.")
            deadline = time.monotonic() + 300
            while not captured and time.monotonic() < deadline:
                server.handle_request()
            if not captured:
                raise SetupError("O pareamento expirou após cinco minutos. Execute novamente para iniciar outra tentativa.")
            if captured.get("error"):
                raise captured["error"]
        own_client = client is None
        client = client or httpx.Client(timeout=20, follow_redirects=False)
        try:
            registration = exchange_registration(client, attempt, captured["query"], existing)
            save_registration(output, registration, replace=replace)
            return {"path": str(output), "email": registration.get("email"), "scopes": registration["scopes"]}
        finally:
            if own_client:
                client.close()
    except httpx.HTTPError:
        raise SetupError("Não foi possível concluir o pareamento com a OpenAI. Nenhuma credencial foi exibida.") from None
    except OSError:
        raise SetupError("Não foi possível iniciar ou concluir o callback local de autenticação.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Conectar o Gestor de Carreira ao ChatGPT no navegador local.")
    parser.add_argument("--output", type=Path, default=default_output(), help="Arquivo próprio de credenciais fora do repositório.")
    parser.add_argument("--replace", action="store_true", help="Reautorizar e substituir um registro existente da mesma identidade.")
    options = parser.parse_args(argv)
    try:
        result = connect(options.output.expanduser().absolute(), replace=options.replace)
        print("Registro salvo:", result["path"])
        print("Conta:", result.get("email") or "identidade validada")
        print("Escopos:", " ".join(result["scopes"]))
        return 0
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Pareamento cancelado. O registro anterior foi preservado.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
