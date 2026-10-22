"""Deployment settings. Credentials are supplied by the host, never by the browser."""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass
class Settings:
    data_dir: str = "/data"
    public_url: str = "https://karenangelis.com"
    owner_email: str = "karen.denich@gmail.com"
    google_client_id: str = ""
    google_client_secret: str = ""
    encryption_key: str = ""
    codex_binary: str = "codex"
    codex_home: str = "/data/codex"
    codex_model: str = ""
    siwc_credentials_file: str = ""
    worker_interval: int = 600
    worker_enabled: bool = True
    cookie_secure: bool = True
    public_data_dir: str = "/app/profile-data"

    @property
    def db_path(self):
        return str(Path(self.data_dir) / "career.sqlite3")

    @classmethod
    def from_env(cls):
        base = os.getenv("CAREER_PUBLIC_URL", "https://karenangelis.com").rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.path:
            raise ValueError("CAREER_PUBLIC_URL deve ser uma origem HTTP(S).")
        local = parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not local:
            raise ValueError("HTTPS obrigatório fora do computador local.")
        data_dir = os.getenv("CAREER_DATA_DIR", "/data")
        return cls(
            data_dir=data_dir, public_url=base,
            owner_email=os.getenv("CAREER_OWNER_EMAIL", "karen.denich@gmail.com").lower(),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
            encryption_key=os.getenv("CAREER_ENCRYPTION_KEY", ""),
            codex_binary=os.getenv("CAREER_CODEX_BINARY", "codex"),
            codex_home=str(Path(data_dir) / "codex"),
            codex_model=os.getenv("CAREER_CODEX_MODEL", ""),
            siwc_credentials_file=os.getenv("CAREER_SIWC_CREDENTIALS_FILE", ""),
            worker_interval=max(60, int(os.getenv("CAREER_WORKER_INTERVAL", "600"))),
            worker_enabled=os.getenv("CAREER_WORKER_ENABLED", "true").lower() == "true",
            cookie_secure=not local,
            public_data_dir=os.getenv("CAREER_PROFILE_DATA_DIR", "/app/profile-data"),
        )
