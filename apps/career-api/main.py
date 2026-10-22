"""HTTP boundary for the private career manager; one owner and one worker process."""
import asyncio
import hashlib
import hmac
import json
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from career.codex import CodexClient, CodexError
from career.config import Settings
from career.google import GoogleIntegration, IntegrationError
from career.pipeline import Pipeline, now
from career.sources import EMAIL, github_projects, source_spec
from career.store import Store

COOKIE = "career_session"
STATE_COOKIE = "career_oauth_state"
API = "/api/career"


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preferences(Payload):
    roles: list[str] = Field(default_factory=list, max_length=30)
    countries: list[str] = Field(default_factory=list, max_length=30)
    remote_only: bool = True
    min_score: int = Field(default=80, ge=0, le=100)
    auto_apply: bool = False


class ProfileInput(Payload):
    resume_text: str = Field(default="", max_length=100000)
    skills: list[str] = Field(default_factory=list, max_length=500)
    facts: dict = Field(default_factory=dict)
    preferences: Preferences = Field(default_factory=Preferences)


class AnswerInput(Payload):
    intent: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=12000)
    source: str = Field(default="owner", max_length=500)


class JobInput(Payload):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2000)
    description: str = Field(min_length=1, max_length=40000)
    location: str = Field(default="", max_length=500)
    apply_email: str | None = Field(default=None, max_length=254)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Informe o link HTTP(S) original da vaga.")
        return value

    @field_validator("apply_email")
    @classmethod
    def validate_email(cls, value):
        if value and not EMAIL.fullmatch(value):
            raise ValueError("E-mail de candidatura inválido.")
        return value or None


class SourceInput(Payload):
    kind: str
    identifier: str


class ApplicationInput(Payload):
    job_id: str


class GithubInput(Payload):
    username: str = "KarenAngelis"


class InterviewInput(Payload):
    application_id: str
    title: str = Field(min_length=1, max_length=300)
    start: str
    end: str
    time_zone: str = "America/Sao_Paulo"
    meeting_url: str = Field(default="", max_length=2000)


def create_app(settings=None, store=None, google=None, codex=None):
    settings = settings or Settings.from_env()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
    store = store or Store(settings.db_path)
    google = google or GoogleIntegration(store, settings)
    codex = codex or CodexClient(settings)
    pipeline = Pipeline(store, google, codex, settings)
    running_tasks = set()

    def schedule(coroutine):
        task = asyncio.create_task(coroutine)
        running_tasks.add(task)
        def finished(result):
            running_tasks.discard(result)
            if not result.cancelled():
                # Consume exceptions without logging email text, OAuth codes or credentials.
                result.exception()
        task.add_done_callback(finished)
        return task

    @asynccontextmanager
    async def lifespan(app):
        background = schedule(pipeline.serve()) if settings.worker_enabled else None
        yield
        for task in list(running_tasks):
            task.cancel()
        for task in list(running_tasks):
            with suppress(asyncio.CancelledError, Exception):
                await task
        await codex.close()

    app = FastAPI(title="Gestor de Carreira", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store, app.state.pipeline = store, pipeline

    @app.middleware("http")
    async def private_headers(request, call_next):
        if request.url.path.startswith(API):
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Tamanho inválido."}, status_code=400)
            if length > 300000:
                return JSONResponse({"detail": "Conteúdo grande demais."}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.exception_handler(IntegrationError)
    @app.exception_handler(CodexError)
    async def integration_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def read_session(request):
        token = request.cookies.get(COOKIE, "")
        if not token:
            return None
        key = "session:" + hashlib.sha256(token.encode()).hexdigest()
        session = store.get_setting(key)
        if not session or session.get("expires", 0) <= time.time() or session.get("email") != settings.owner_email:
            return None
        return session

    async def authorized(request: Request):
        session = read_session(request)
        if not session:
            raise HTTPException(401, "Entre com sua conta Google para acessar o gestor.")
        if request.method not in {"GET", "HEAD"}:
            supplied = request.headers.get("x-csrf-token", "")
            origin = request.headers.get("origin")
            if (not hmac.compare_digest(supplied, session["csrf"]) or
                    (origin is not None and origin != settings.public_url)):
                raise HTTPException(403, "Atualize a página para confirmar sua sessão.")
        return session

    @app.get(API + "/health")
    def health():
        return {"status": "ok"}

    @app.get(API + "/session")
    async def session_info(request: Request):
        session = read_session(request)
        configured = (await google.status()).get("configured", False)
        return {"authenticated": bool(session), "user": {"email": session["email"], "name": session.get("name")} if session else None,
                "csrf_token": session["csrf"] if session else None, "setup_required": not configured, "google_configured": configured}

    @app.get(API + "/auth/google/start")
    async def login(request: Request, connect: int = 0):
        if connect and not read_session(request):
            raise HTTPException(401, "Entre antes de conectar Gmail e Agenda.")
        if not (await google.status()).get("configured"):
            raise HTTPException(503, "O login Google precisa ser configurado no servidor deste site.")
        state = secrets.token_urlsafe(32)
        response = RedirectResponse(await google.authorization_url(state, connect=bool(connect)), status_code=303)
        response.set_cookie(STATE_COOKIE, state, secure=settings.cookie_secure, httponly=True, samesite="lax", max_age=600, path=API + "/auth/google")
        return response

    @app.get(API + "/auth/google/callback")
    async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
        saved = request.cookies.get(STATE_COOKIE, "")
        if error or not code or not state or not saved or not hmac.compare_digest(saved, state):
            raise HTTPException(400, "A conexão não foi concluída. Inicie o login novamente.")
        identity = await google.complete_oauth(code, state)
        if identity.get("email", "").lower() != settings.owner_email or not identity.get("email_verified"):
            raise HTTPException(403, "Esta área é exclusiva da proprietária do site.")
        token = secrets.token_urlsafe(48)
        store.set_setting("session:" + hashlib.sha256(token.encode()).hexdigest(), {
            "email": identity["email"].lower(), "name": identity.get("name"),
            "csrf": secrets.token_urlsafe(32), "expires": time.time() + 7 * 24 * 3600,
        })
        response = RedirectResponse("/carreira/", status_code=303)
        response.set_cookie(COOKIE, token, secure=settings.cookie_secure, httponly=True, samesite="lax", max_age=7 * 24 * 3600, path=API)
        response.delete_cookie(STATE_COOKIE, path=API + "/auth/google")
        return response

    @app.post(API + "/logout")
    def logout(request: Request, session=Depends(authorized)):
        token = request.cookies.get(COOKIE, "")
        store.set_setting("session:" + hashlib.sha256(token.encode()).hexdigest(), None)
        response = JSONResponse({"status": "signed_out"})
        response.delete_cookie(COOKIE, path=API)
        return response

    @app.get(API + "/dashboard")
    async def dashboard(session=Depends(authorized)):
        applications, jobs, events = store.list_applications(), store.list_jobs(), store.list_events()
        return {"profile": store.get_profile(), "answers": store.list_answers(), "jobs": jobs,
                "applications": applications, "events": events,
                "interviews": [{"application_id": e.get("application_id"), **e.get("detail", {})} for e in events if e["kind"] == "interview_created"],
                "connections": {"google": await google.status(), "codex": await codex.status()},
                "worker": {"enabled": settings.worker_enabled, **store.get_setting("worker_state", {})},
                "stats": {"jobs": len(jobs), "applications": len(applications), "sent": sum(a.get("status") in {"sent", "received", "interested", "interview", "offer"} for a in applications), "interviews": sum(e["kind"] == "interview_created" for e in events)}}

    @app.put(API + "/profile")
    def save_profile(data: ProfileInput, session=Depends(authorized)):
        current = store.get_profile()
        return store.save_profile({**current, **data.model_dump()})

    @app.post(API + "/profile/import-site")
    def import_profile(session=Depends(authorized)):
        base = Path(settings.public_data_dir)
        files = {}
        for name in ("profile", "career", "evidence"):
            try:
                files[name] = json.loads((base / f"{name}.json").read_text())
            except (OSError, ValueError) as exc:
                raise HTTPException(503, "Arquivos do perfil público não disponíveis neste servidor.") from exc
        public = files["profile"]
        current = store.get_profile()
        skills = [skill for group in public.get("skillGroups", []) for skill in group.get("items", [])]
        return store.save_profile({**current, "resume_text": current.get("resume_text") or json.dumps(files, ensure_ascii=False, indent=2),
                                   "skills": current.get("skills") or skills, "portfolio_sources": files,
                                   "facts": {"name": public.get("name"), "email": settings.owner_email, "github": public.get("github"), "portfolio": settings.public_url, **current.get("facts", {})},
                                   "preferences": current.get("preferences") or Preferences().model_dump()})

    @app.post(API + "/profile/sync-github")
    async def sync_github(data: GithubInput, session=Depends(authorized)):
        try:
            projects = await github_projects(data.username)
        except Exception as exc:
            raise HTTPException(502, "Não foi possível atualizar o GitHub agora.") from exc
        profile = store.get_profile()
        return store.save_profile({**profile, "github_projects": projects, "github_synced_at": now()})

    @app.post(API + "/answers")
    def answer(data: AnswerInput, session=Depends(authorized)):
        return store.save_answer(data.model_dump())

    @app.delete(API + "/answers/{answer_id}")
    def remove_answer(answer_id: str, session=Depends(authorized)):
        store.delete_answer(answer_id)
        return {"status": "deleted"}

    @app.post(API + "/jobs")
    def add_job(data: JobInput, session=Depends(authorized)):
        payload = data.model_dump()
        key = hashlib.sha256(payload["url"].encode()).hexdigest()
        return store.upsert_job({**payload, "source": "owner", "external_id": key,
                                 "contact_source": "owner" if payload.get("apply_email") else None})

    @app.get(API + "/sources")
    def list_sources(session=Depends(authorized)):
        return store.get_setting("sources", [])

    @app.post(API + "/sources")
    def add_source(data: SourceInput, session=Depends(authorized)):
        source = source_spec(data.model_dump())
        sources = store.get_setting("sources", [])
        if source not in sources:
            sources.append(source)
        store.set_setting("sources", sources)
        return source

    @app.post(API + "/applications")
    def add_application(data: ApplicationInput, session=Depends(authorized)):
        job = store.get_job(data.job_id)
        if not job:
            raise HTTPException(404, "Vaga não encontrada.")
        return store.create_application(data.job_id, {"status": "draft", "company": job["company"], "title": job["title"]})

    @app.post(API + "/applications/{application_id}/prepare")
    async def prepare(application_id: str, session=Depends(authorized)):
        return await pipeline.prepare(application_id)

    @app.post(API + "/interviews")
    async def interview(data: InterviewInput, session=Depends(authorized)):
        payload = data.model_dump(exclude={"application_id"})
        # A person can enter local clock times with an explicit timezone. Model results cannot.
        try:
            zone = ZoneInfo(data.time_zone)
            for field in ("start", "end"):
                moment = datetime.fromisoformat(payload[field])
                if moment.tzinfo is None:
                    first, second = moment.replace(tzinfo=zone, fold=0), moment.replace(tzinfo=zone, fold=1)
                    if first.utcoffset() != second.utcoffset() or first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != moment:
                        raise ValueError
                    moment = first
                payload[field] = moment.isoformat()
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, "Horário ou fuso inválido/ambíguo. Informe um horário com offset explícito.") from None
        return await pipeline.add_interview(data.application_id, payload)

    @app.post(API + "/codex/login")
    async def codex_login(session=Depends(authorized)):
        return await codex.login()

    @app.post(API + "/run")
    async def run(session=Depends(authorized)):
        if store.get_setting("worker_state", {}).get("running"):
            return {"status": "already_running"}
        schedule(pipeline.run())
        return {"status": "started"}

    @app.post(API + "/sync-mail")
    async def sync_mail(session=Depends(authorized)):
        lock = store.try_lock("pipeline", ttl=1800)
        if not lock.get("acquired"):
            return {"status": "already_running"}
        try:
            return await pipeline.sync_mail()
        finally:
            store.release_lock("pipeline")

    # Also supports a local smoke test with no external proxy; private data is only in the API.
    web = Path(__file__).resolve().parents[2] / "web" / "carreira"
    if web.exists():
        app.mount("/carreira", StaticFiles(directory=web, html=True), name="career-ui")
    return app


app = create_app()
