from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlsplit, urlunsplit
from typing import Literal
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = (
        "postgresql+psycopg://agentpass:local-sandbox-only@localhost:5432/agentpass"
    )
    environment: Literal["development", "sandbox", "pilot", "production"] = "sandbox"
    cookie_secure: bool = False
    web_origin: str = "http://localhost:3000"
    session_hours: int = 12
    encryption_key: str = ""
    seed_demo: bool = False
    demo_password: str = ""
    webhook_host_allowlist: str = ""
    rate_limit: int = 120
    sandbox_receiver_url: str = "http://127.0.0.1:8000/v1/sandbox/webhook-receiver"
    execution_signing_key: str = Field(default="", repr=False)
    execution_key_id: str = "local-v1"
    execution_grant_seconds: int = Field(default=120, ge=15, le=300)
    allow_public_registration: bool = True
    require_mfa: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_jwks_url: str = ""
    yookassa_sandbox_enabled: bool = False
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = Field(default="", repr=False)
    payment_return_url: str = ""

    def validate_operational(self):
        from cryptography.fernet import Fernet
        from sqlalchemy.engine import make_url

        if not self.encryption_key:
            raise RuntimeError("ENCRYPTION_KEY is required; use infra/bootstrap.py")
        Fernet(self.encryption_key.encode())
        if self.yookassa_sandbox_enabled:
            if not self.yookassa_shop_id or not self.yookassa_secret_key.startswith('test_'):
                raise RuntimeError('External sandbox requires test-shop credentials; live keys are forbidden')
            if urlsplit(self.payment_return_url).scheme != 'https':
                raise RuntimeError('External checkout requires an explicit HTTPS return URL')
        if self.environment in {"pilot", "production"}:
            if self.seed_demo or self.demo_password:
                raise RuntimeError("Pilot forbids SEED_DEMO and DEMO_PASSWORD")
            if not self.cookie_secure or urlsplit(self.web_origin).scheme != "https":
                raise RuntimeError("Pilot requires HTTPS WEB_ORIGIN and secure cookies")
            if self.allow_public_registration or not self.require_mfa:
                raise RuntimeError("Pilot requires closed registration and MFA")
            if len(self.execution_signing_key) < 32 or self.execution_signing_key == self.encryption_key:
                raise RuntimeError("Pilot requires a separate execution signing key (32+ characters)")
            database = make_url(self.database_url)
            if not database.password or len(database.password) < 24 or database.password == "local-sandbox-only":
                raise RuntimeError("Pilot requires dedicated database credentials")
            if database.query.get("sslmode") != "verify-full":
                raise RuntimeError("Pilot database requires sslmode=verify-full")
            if not self.webhook_host_allowlist.strip():
                raise RuntimeError("Pilot requires an explicit webhook hostname allowlist")
        return self

    @property
    def allowed_web_origins(self):
        origins = {self.web_origin.rstrip("/")}
        parsed = urlsplit(self.web_origin)
        if self.environment == "sandbox" and parsed.hostname in {
            "localhost", "127.0.0.1", "terminal.local"
        }:
            port = f":{parsed.port}" if parsed.port else ""
            for host in ("localhost", "127.0.0.1", "terminal.local"):
                origins.add(urlunsplit((parsed.scheme, host + port, "", "", "")))
        return origins


@lru_cache
def settings():
    result = Settings()
    result.validate_operational()
    if result.environment not in {"sandbox", "development"} and not result.cookie_secure:
        raise RuntimeError("Secure cookies required outside sandbox")
    return result
