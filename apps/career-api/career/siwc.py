"""Protected SIWC registration for the owner's self-hosted open-source runtime.

OAuth registration/ID-token validation happen locally in the official flow. This
adapter consumes only that selected, already-validated registration file. It does
not read Codex auth.json or turn website identity scopes into inference access.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any
import uuid

import httpx

TOKEN_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
DIRECT_SCOPE = "chatgpt.tokens.use.direct"
SETUP_DOCUMENTATION = "https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms"
_INVALID_REFRESH = {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
                    "refresh_token_invalidated", "refresh_token_reused"}


class SiwcError(RuntimeError):
    """Public, sanitized connection error. Never include endpoint response text."""


def _timestamp(value: Any) -> float:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return float(value)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        pass
    raise SiwcError("O registro Sign in with ChatGPT contém uma validade inválida.")


class SiwcCredentials:
    def __init__(self, settings: Any, client: httpx.AsyncClient | None = None):
        default = str(Path(getattr(settings, "data_dir", "/data")) / "siwc" / "credentials.json")
        self.path = Path(getattr(settings, "siwc_credentials_file", default) or default)
        self.host_path = self.path.parent / "host-id"
        self._client = client
        self._lock = asyncio.Lock()

    @staticmethod
    def _read_protected(path: Path, *, json_file=True):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            if path.is_symlink():
                raise SiwcError("O registro Sign in with ChatGPT deve ser um arquivo protegido, sem link simbólico.")
            with os.fdopen(os.open(path, flags), "r", encoding="utf-8") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                    raise SiwcError("Proteja o registro Sign in with ChatGPT com permissão 0600.")
                if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
                    raise SiwcError("O registro Sign in with ChatGPT precisa pertencer ao usuário do serviço.")
                text = stream.read(128001)
                if len(text) > 128000:
                    raise SiwcError("O registro Sign in with ChatGPT excedeu o tamanho permitido.")
                return json.loads(text) if json_file else text.strip()
        except FileNotFoundError:
            raise SiwcError("Conclua o pareamento Sign in with ChatGPT local e importe o registro protegido para a VPS.") from None
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise SiwcError("Não foi possível ler o registro protegido Sign in with ChatGPT.") from None

    def _read(self) -> dict:
        if self.path.name == "auth.json":
            raise SiwcError("Use o registro próprio Sign in with ChatGPT; auth.json do Codex não é aceito.")
        value = self._read_protected(self.path)
        if not isinstance(value, dict):
            raise SiwcError("O registro Sign in with ChatGPT está em formato inválido.")
        if (value.get("issuer") != "https://auth.openai.com" or not value.get("subject")
                or not isinstance(value.get("client_id"), str) or not value["client_id"].strip()
                or value["client_id"] == "dynamic_agent_client"):
            raise SiwcError("Importe o registro validado com identidade e client_id emitido no OAuth oficial.")
        return value

    @staticmethod
    def _scopes(data: dict) -> set[str]:
        value = data.get("scopes", data.get("scope", []))
        if isinstance(value, str):
            return set(value.split())
        return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()

    @staticmethod
    def _expiry(data: dict) -> float:
        if data.get("expires_at") is not None:
            return _timestamp(data["expires_at"])
        duration = data.get("expires_in")
        if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0:
            raise SiwcError("O registro Sign in with ChatGPT contém uma validade inválida.")
        return _timestamp(data.get("saved_at")) + float(duration)

    def metadata(self) -> dict:
        """No token, subject, client id or credential path is exposed to the UI."""
        try:
            data = self._read()
            scopes = self._scopes(data)
            granted = {DIRECT_SCOPE, "resource.invoke"}.issubset(scopes)
            expiry = self._expiry(data)
            renewable = bool(data.get("refresh_token")) and "offline_access" in scopes
            configured = granted and bool(data.get("access_token")) and not data.get("needs_reauth")
            ready = configured and (expiry > time.time() or renewable)
            return {"configured": bool(configured), "pairing_required": not ready,
                    "token_ready": bool(ready), "requires_refresh": expiry <= time.time() + 60,
                    "account": {"email": data.get("email")},
                    "reason": "" if ready else "Autorize o uso do plano ChatGPT no pareamento local e importe o registro atualizado.",
                    "documentation_url": SETUP_DOCUMENTATION}
        except SiwcError as exc:
            return {"configured": False, "pairing_required": True, "token_ready": False,
                    "reason": str(exc), "documentation_url": SETUP_DOCUMENTATION}

    def _write(self, data: dict) -> None:
        """Replace the complete rotating token set atomically, with mode 0600."""
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise SiwcError("O diretório do registro Sign in with ChatGPT não pode ser um link simbólico.")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".credentials-", dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(data, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except (OSError, ValueError, TypeError):
            raise SiwcError("Não foi possível atualizar o registro protegido Sign in with ChatGPT.") from None
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def host_id(self) -> str:
        """VM host identity remains separate from an imported laptop identity."""
        if self.host_path.exists() or self.host_path.is_symlink():
            identity = self._read_protected(self.host_path, json_file=False)
            if not identity.startswith("urn:uuid:"):
                raise SiwcError("O identificador do host Sign in with ChatGPT é inválido.")
            try:
                uuid.UUID(identity.removeprefix("urn:uuid:"))
            except ValueError:
                raise SiwcError("O identificador do host Sign in with ChatGPT é inválido.") from None
            return identity
        self.host_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        identity = "urn:uuid:" + str(uuid.uuid4())
        try:
            descriptor = os.open(self.host_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(identity + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            return self.host_id()
        except OSError:
            raise SiwcError("Não foi possível preparar o identificador protegido do host.") from None
        return identity

    async def access_token(self) -> str:
        # One uvicorn worker is required. This lock serializes refreshes within
        # the single service process; do not share this registration across replicas.
        async with self._lock:
            data = self._read()
            scopes = self._scopes(data)
            if not {DIRECT_SCOPE, "resource.invoke"}.issubset(scopes) or data.get("needs_reauth"):
                raise SiwcError("O registro não autoriza usar o plano ChatGPT. Conclua novamente o pareamento local.")
            host = self.host_id()
            if data.get("ext_agent_host_id") != host:
                data["ext_agent_host_id"] = host
                self._write(data)
            expiry = self._expiry(data)
            access = data.get("access_token")
            if not isinstance(access, str) or not access:
                raise SiwcError("O registro não contém um token de acesso Sign in with ChatGPT válido.")
            if expiry > time.time() + 60:
                return access
            if data.get("earliest_refresh_at") and _timestamp(data["earliest_refresh_at"]) > time.time():
                if expiry > time.time():
                    return access
                raise SiwcError("A renovação Sign in with ChatGPT ainda não está disponível.")
            if not data.get("refresh_token") or "offline_access" not in scopes:
                raise SiwcError("O registro precisa de novo pareamento local para continuar em segundo plano.")
            own_client = self._client is None
            client = self._client or httpx.AsyncClient(timeout=20, follow_redirects=False)
            try:
                response = await client.post(TOKEN_ENDPOINT, data={
                    "grant_type": "refresh_token", "client_id": data["client_id"],
                    "refresh_token": data["refresh_token"], "resource": RESOURCE,
                })
                try:
                    result = response.json()
                except (ValueError, UnicodeError):
                    result = {}
                if not isinstance(result, dict):
                    result = {}
                if response.status_code != 200:
                    code = result.get("error")
                    if isinstance(code, dict):
                        code = code.get("code")
                    if isinstance(code, str) and code in _INVALID_REFRESH:
                        for key in ("access_token", "refresh_token", "id_token"):
                            data.pop(key, None)
                        data["needs_reauth"] = True
                        self._write(data)
                        raise SiwcError("A conexão ChatGPT foi encerrada. Conclua novamente o pareamento local.")
                    raise SiwcError("Não foi possível renovar a conexão ChatGPT. O registro foi preservado.")
                if (not isinstance(result.get("access_token"), str) or not result["access_token"]
                        or not isinstance(result.get("refresh_token"), str) or not result["refresh_token"]):
                    raise SiwcError("A renovação ChatGPT não retornou o conjunto de credenciais esperado.")
                replacement = {**data, **{key: result[key] for key in
                    ("access_token", "refresh_token", "id_token", "token_type", "expires_in", "earliest_refresh_at") if key in result}}
                replacement.pop("expires_at", None)
                replacement.pop("needs_reauth", None)
                replacement["saved_at"] = datetime.now(timezone.utc).isoformat()
                if "scope" in result:
                    replacement["scopes"] = sorted(self._scopes({"scope": result["scope"]}))
                # Validate expiry and retained grant before accepting inference.
                self._expiry(replacement)
                self._write(replacement)
                if not {DIRECT_SCOPE, "resource.invoke"}.issubset(self._scopes(replacement)):
                    raise SiwcError("A conexão renovada não autoriza usar o plano ChatGPT.")
                return replacement["access_token"]
            except httpx.HTTPError:
                raise SiwcError("A renovação ChatGPT está indisponível. O registro foi preservado.") from None
            finally:
                if own_client:
                    await client.aclose()
