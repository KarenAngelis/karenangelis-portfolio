"""Owner-only Google OAuth, Gmail and Calendar integration.

The caller owns session/CSRF cookies. OAuth verifiers and provider tokens never
leave server storage. An uncertain Gmail POST is reconciled in SENT, not retried.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cryptography.fernet import Fernet, InvalidToken


IDENTITY_SCOPES = ("openid", "email", "profile")
GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events.owned"
CONNECTED_SCOPES = (*IDENTITY_SCOPES, GMAIL_READ, GMAIL_SEND, CALENDAR_EVENTS)
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class IntegrationError(Exception):
    """A deliberately sanitized, safe-to-display integration error."""

    def __init__(self, message: str, *, code: str = "google_integration_error"):
        super().__init__(message)
        self.code = code


class GoogleIntegration:
    def __init__(self, store, settings):
        self.store = store
        self.settings = settings
        self._oauth_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._client_factory = httpx.AsyncClient
        try:
            key = settings.encryption_key
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError, AttributeError):
            self._fernet = None

    def _configured(self) -> bool:
        return bool(
            getattr(self.settings, "google_client_id", "")
            and getattr(self.settings, "google_client_secret", "")
            and getattr(self.settings, "owner_email", "")
            and self._fernet
        )

    def _require_configuration(self):
        if not self._configured():
            raise IntegrationError("Conexão Google ainda não configurada.", code="not_configured")

    def _encrypt(self, value: dict) -> str:
        self._require_configuration()
        return self._fernet.encrypt(json.dumps(value).encode()).decode()

    def _decrypt(self, value: str) -> dict:
        self._require_configuration()
        try:
            data = json.loads(self._fernet.decrypt(value.encode()))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (InvalidToken, ValueError, TypeError, AttributeError):
            raise IntegrationError("Conexão Google precisa ser refeita.", code="reconnect_required") from None

    def _tokens(self) -> dict:
        encrypted = self.store.get_secret("google_tokens")
        return self._decrypt(encrypted) if encrypted else {}

    def _save_tokens(self, tokens: dict):
        self.store.set_secret("google_tokens", self._encrypt(tokens))

    def _redirect_uri(self) -> str:
        return self.settings.public_url.rstrip("/") + "/api/career/auth/google/callback"

    async def _request(self, method: str, url: str, *, token=None, allowed=(200,), **kwargs) -> dict:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._client_factory(timeout=25.0, follow_redirects=False) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise IntegrationError("Não foi possível confirmar a operação no Google.", code="google_unavailable") from None
        if response.status_code not in allowed:
            code = "reconnect_required" if response.status_code in (401, 403) else "google_request_failed"
            raise IntegrationError("Google não confirmou a operação solicitada.", code=code)
        if response.status_code in (404, 409):
            return {"_status": response.status_code}
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, TypeError):
            raise IntegrationError("Google retornou uma resposta inválida.", code="invalid_google_response") from None

    async def authorization_url(self, session_state: str, connect: bool = False) -> str:
        self._require_configuration()
        if not session_state or len(session_state) > 1024:
            raise IntegrationError("Sessão de autorização inválida.", code="invalid_oauth_state")
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        scopes = list(CONNECTED_SCOPES if connect else IDENTITY_SCOPES)
        key = "google_oauth_state:" + hashlib.sha256(session_state.encode()).hexdigest()
        self.store.set_setting(key, self._encrypt({"verifier": verifier, "expires_at": time.time() + 600, "scopes": scopes}))
        parameters = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": session_state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "include_granted_scopes": "true",
            "login_hint": self.settings.owner_email,
        }
        if connect:
            parameters.update(access_type="offline", prompt="consent")
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(parameters)

    async def complete_oauth(self, code: str, state: str) -> dict:
        self._require_configuration()
        if not code or not state or len(state) > 1024:
            raise IntegrationError("Sessão de autorização inválida.", code="invalid_oauth_state")
        key = "google_oauth_state:" + hashlib.sha256(state.encode()).hexdigest()
        async with self._oauth_lock:
            encrypted = self.store.get_setting(key)
            if not encrypted:
                raise IntegrationError("Autorização expirada ou já utilizada.", code="invalid_oauth_state")
            self.store.set_setting(key, "")  # Consume before any external request.
            pending = self._decrypt(encrypted)
        if pending.get("expires_at", 0) < time.time():
            raise IntegrationError("Autorização expirada.", code="invalid_oauth_state")
        exchanged = await self._request("POST", TOKEN_URL, data={
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "code": code,
            "code_verifier": pending["verifier"],
            "grant_type": "authorization_code",
            "redirect_uri": self._redirect_uri(),
        })
        if not exchanged.get("access_token"):
            raise IntegrationError("Google não confirmou o acesso.", code="invalid_google_response")
        identity = await self._request("GET", "https://openidconnect.googleapis.com/v1/userinfo", token=exchanged["access_token"])
        email = str(identity.get("email", "")).strip().lower()
        if identity.get("email_verified") is not True or not identity.get("sub") or email != self.settings.owner_email.strip().lower():
            raise IntegrationError("Esta conta não está autorizada para o piloto.", code="owner_required")
        try:
            previous = self._tokens()
        except IntegrationError:
            previous = {}
        refresh_token = exchanged.get("refresh_token")
        if not refresh_token and previous.get("email") == email and previous.get("sub") == identity["sub"]:
            refresh_token = previous.get("refresh_token")
        # Only a returned grant establishes Gmail/Calendar permissions. A missing
        # scope field establishes identity through userinfo, not requested extras.
        scopes = str(exchanged.get("scope", " ".join(IDENTITY_SCOPES))).split()
        self._save_tokens({
            "access_token": exchanged["access_token"],
            "refresh_token": refresh_token,
            "expires_at": time.time() + max(0, int(exchanged.get("expires_in", 3600))),
            "email": email, "name": identity.get("name", ""), "sub": identity["sub"], "scopes": scopes,
        })
        return {"email": email, "name": identity.get("name", ""), "sub": identity["sub"], "email_verified": True, "scopes": scopes}

    async def status(self) -> dict:
        result = {"configured": self._configured(), "connected": False, "gmail_connected": False, "calendar_connected": False}
        if not result["configured"]:
            return result
        try:
            tokens = self._tokens()
        except IntegrationError:
            return {**result, "reconnect_required": True}
        if not tokens:
            return result
        scopes = tokens.get("scopes", [])
        connected = bool(tokens.get("refresh_token") or tokens.get("expires_at", 0) > time.time())
        return {**result, "connected": connected, "email": tokens.get("email"), "scopes": scopes,
                "gmail_connected": connected and {GMAIL_READ, GMAIL_SEND}.issubset(scopes),
                "calendar_connected": connected and CALENDAR_EVENTS in scopes}

    def _require_scopes(self, *required: str):
        if not set(required).issubset(self._tokens().get("scopes", [])):
            raise IntegrationError("Conecte Gmail e Agenda para habilitar esta operação.", code="missing_scopes")

    async def access_token(self) -> str:
        self._require_configuration()
        async with self._refresh_lock:
            tokens = self._tokens()
            if tokens.get("access_token") and tokens.get("expires_at", 0) > time.time() + 60:
                return tokens["access_token"]
            if not tokens.get("refresh_token"):
                raise IntegrationError("Conexão Google precisa ser refeita.", code="reconnect_required")
            refreshed = await self._request("POST", TOKEN_URL, data={
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
            })
            if not refreshed.get("access_token"):
                raise IntegrationError("Conexão Google precisa ser refeita.", code="reconnect_required")
            tokens.update(access_token=refreshed["access_token"], expires_at=time.time() + max(0, int(refreshed.get("expires_in", 3600))))
            if refreshed.get("refresh_token"):
                tokens["refresh_token"] = refreshed["refresh_token"]
            if refreshed.get("scope"):
                tokens["scopes"] = refreshed["scope"].split()
            self._save_tokens(tokens)
            return tokens["access_token"]

    async def search_messages(self, query: str, max_results: int = 30) -> list[dict]:
        self._require_scopes(GMAIL_READ)
        if not isinstance(max_results, int) or not 1 <= max_results <= 500:
            raise IntegrationError("Limite de mensagens inválido.", code="invalid_input")
        token = await self.access_token()
        messages, seen, pages = [], set(), set()
        page_token = None
        while len(messages) < max_results:
            params = {"q": query, "maxResults": min(100, max_results - len(messages))}
            if page_token:
                params["pageToken"] = page_token
            listed = await self._request("GET", GMAIL_URL, token=token, params=params)
            for item in listed.get("messages", []):
                message_id = item.get("id")
                if not message_id or message_id in seen:
                    continue
                seen.add(message_id)
                message = await self._request("GET", f"{GMAIL_URL}/{message_id}", token=token, params={"format": "full"})
                messages.append(message)
                if len(messages) >= max_results:
                    break
            page_token = listed.get("nextPageToken")
            if not page_token or page_token in pages:
                break
            pages.add(page_token)
        return messages

    async def send_application(self, application: dict, profile: dict) -> dict:
        self._require_scopes(GMAIL_READ, GMAIL_SEND)
        application_id = str(application.get("id", "")).strip()
        recipient = str(application.get("contact_email", "")).strip()
        subject = str(application.get("email_subject", "")).strip()
        body = str(application.get("email_body", "")).strip()
        if not application_id or not subject or not body or not self._valid_email(recipient):
            raise IntegrationError("Candidatura sem destinatário, assunto ou texto válido.", code="invalid_input")
        sender = profile.get("facts", {}).get("email") or self.settings.owner_email
        if not isinstance(sender, str) or sender.strip().lower() != self.settings.owner_email.strip().lower():
            raise IntegrationError("Remetente não autorizado.", code="owner_required")
        digest, message_id = self._message_identity(application_id)
        receipt_key = "google_send:" + digest
        try:
            mime = EmailMessage()
            mime["From"], mime["To"], mime["Subject"] = sender, recipient, subject
            mime["Message-ID"] = f"<{message_id}>"
            mime.set_content(body)
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        except (ValueError, TypeError):
            raise IntegrationError("Cabeçalhos da candidatura inválidos.", code="invalid_input") from None
        async with self._send_lock:
            receipt = self.store.get_setting(receipt_key) or {}
            if receipt.get("status") == "sent":
                return {"message_id": receipt["message_id"], "thread_id": receipt.get("thread_id")}
            token = await self.access_token()
            listed = await self._request("GET", GMAIL_URL, token=token, params={"q": f"in:sent rfc822msgid:{message_id}", "maxResults": 1})
            if listed.get("messages"):
                found = listed["messages"][0]
                result = {"message_id": found["id"], "thread_id": found.get("threadId")}
            else:
                if receipt.get("status") == "uncertain":
                    raise IntegrationError("Envio anterior ainda não confirmado. Reconciliação necessária antes de novo envio.", code="send_unconfirmed")
                self.store.set_setting(receipt_key, {"status": "uncertain", "rfc_message_id": message_id})
                sent = await self._request("POST", GMAIL_URL + "/send", token=token, json={"raw": raw})
                if not sent.get("id"):
                    raise IntegrationError("Envio ainda não confirmado.", code="send_unconfirmed")
                result = {"message_id": sent["id"], "thread_id": sent.get("threadId")}
            self.store.set_setting(receipt_key, {"status": "sent", **result})
            return result

    def _message_identity(self, application_id: str) -> tuple[str, str]:
        if not isinstance(application_id, str) or not application_id.strip():
            raise IntegrationError("Candidatura inválida para reconciliação.", code="invalid_input")
        digest = hashlib.sha256(application_id.strip().encode()).hexdigest()
        domain = urlsplit(self.settings.public_url).hostname or "karenangelis.com"
        return digest, f"career.{digest}@{domain}"

    async def reconcile_application(self, application_id: str) -> dict | None:
        """Recover a receipt from SENT; never submit or resubmit a message.

        List results contain IDs only. Fetch metadata and verify both SENT and
        the exact deterministic Message-ID before marking an uncertain send done.
        """
        self._require_scopes(GMAIL_READ)
        digest, expected_id = self._message_identity(application_id)
        async with self._send_lock:
            token = await self.access_token()
            listed = await self._request("GET", GMAIL_URL, token=token,
                                         params={"q": f"in:sent rfc822msgid:{expected_id}", "maxResults": 5})
            candidates = listed.get("messages", [])
            if not isinstance(candidates, list):
                return None
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                message_id = candidate.get("id")
                if not isinstance(message_id, str) or not message_id:
                    continue
                message = await self._request("GET", f"{GMAIL_URL}/{quote(message_id, safe='')}", token=token,
                                              params={"format": "metadata", "metadataHeaders": "Message-ID"})
                payload = message.get("payload", {})
                headers = payload.get("headers", []) if isinstance(payload, dict) else []
                if not isinstance(headers, list):
                    headers = []
                labels = message.get("labelIds", [])
                if not isinstance(labels, list):
                    labels = []
                exact_header = any(
                    isinstance(header, dict)
                    and str(header.get("name", "")).casefold() == "message-id"
                    and str(header.get("value", "")).strip().strip("<>") == expected_id
                    for header in headers
                )
                if (message.get("id") != message_id or "SENT" not in labels
                        or not exact_header or not isinstance(message.get("threadId"), str) or not message["threadId"]):
                    continue
                receipt = {"message_id": message_id, "thread_id": message["threadId"]}
                self.store.set_setting("google_send:" + digest, {"status": "sent", **receipt})
                return receipt
            return None

    @staticmethod
    def _valid_email(value: str) -> bool:
        if "\n" in value or "\r" in value or any(c in value for c in ",;<>"):
            return False
        _, parsed = parseaddr(value)
        return parsed == value and value.count("@") == 1 and bool(value.split("@")[0]) and "." in value.split("@")[1]

    async def create_interview(self, application_id: str, interview: dict) -> dict:
        self._require_scopes(CALENDAR_EVENTS)
        try:
            zone = ZoneInfo(interview["time_zone"])
            start = datetime.fromisoformat(interview["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(interview["end"].replace("Z", "+00:00"))
            if not application_id or not interview.get("title") or start.tzinfo is None or end.tzinfo is None or end <= start:
                raise ValueError
            if any(moment.utcoffset() != moment.astimezone(zone).utcoffset() for moment in (start, end)):
                raise ValueError
            meeting_url = interview.get("meeting_url", "")
            if meeting_url:
                parsed = urlsplit(meeting_url)
                if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                    raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, ZoneInfoNotFoundError):
            raise IntegrationError("Entrevista exige título, início, fim e fuso horário válidos e explícitos.", code="invalid_interview") from None
        # One application may have multiple rounds. Duplicate confirmations of
        # the same slot share an event even when their email IDs or titles differ.
        slot = f"{start.astimezone(timezone.utc).isoformat()}:{end.astimezone(timezone.utc).isoformat()}"
        event_id = hashlib.sha256(f"career:{application_id}:{slot}".encode()).hexdigest()
        token = await self.access_token()
        existing = await self._request("GET", f"{CALENDAR_URL}/{event_id}", token=token, allowed=(200, 404))
        if existing.get("_status") != 404:
            return {"id": existing.get("id", event_id), "htmlLink": existing.get("htmlLink")}
        event = {
            "id": event_id, "summary": interview["title"],
            "description": "Entrevista vinculada à candidatura " + str(application_id) + ("\n" + meeting_url if meeting_url else ""),
            "start": {"dateTime": start.isoformat(), "timeZone": zone.key},
            "end": {"dateTime": end.isoformat(), "timeZone": zone.key},
            "extendedProperties": {"private": {"career_application_id": str(application_id)}},
        }
        if interview.get("source_message_id"):
            event["extendedProperties"]["private"]["career_source_message_id"] = str(interview["source_message_id"])[:1024]
        created = await self._request("POST", CALENDAR_URL, token=token, allowed=(200, 201, 409), params={"sendUpdates": "none"}, json=event)
        if created.get("_status") == 409:
            created = await self._request("GET", f"{CALENDAR_URL}/{event_id}", token=token)
        if not created.get("id"):
            raise IntegrationError("Registro da entrevista ainda não confirmado.", code="invalid_google_response")
        return {"id": created["id"], "htmlLink": created.get("htmlLink")}
