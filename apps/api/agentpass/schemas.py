from datetime import datetime, timezone
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

Money = Annotated[int, Field(strict=True, gt=0, le=100_000_000_000)]
Name = Annotated[str, Field(min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class RegisterIn(LoginIn):
    name: Name
    organization_name: Name
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Некорректный email")
        return value.strip().lower()


class AgentIn(StrictModel):
    name: Name
    description: str = Field(default="", max_length=500)
    project_id: str | None = None


class MandateIn(StrictModel):
    agent_id: str
    name: Name = "Финансовые полномочия"
    currency: Literal["RUB"] = "RUB"
    categories: list[str] = Field(min_length=1, max_length=20)
    merchant_allowlist: list[str] = Field(default_factory=list, max_length=100)
    merchant_denylist: list[str] = Field(default_factory=list, max_length=100)
    per_transaction: Money
    daily_limit: Money
    weekly_limit: Money
    monthly_limit: Money
    approval_threshold: Money
    valid_from: datetime
    valid_until: datetime

    @field_validator("categories", "merchant_allowlist", "merchant_denylist")
    @classmethod
    def normalize(cls, value):
        if any(not s.strip() or len(s) > 120 for s in value):
            raise ValueError("Пустое или слишком длинное правило")
        return list(dict.fromkeys(s.strip().casefold() for s in value))

    @field_validator("valid_from", "valid_until")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Нужен часовой пояс")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def dates(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("Дата окончания должна быть после начала")
        return self


class IntentIn(StrictModel):
    agent_id: str
    mandate_id: str
    merchant: str = Field(min_length=1, max_length=120)
    merchant_id: str | None = Field(default=None, min_length=1, max_length=120)
    order_id: str | None = Field(default=None, min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    amount: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    description: str = Field(default="", max_length=500)
    idempotency_key: str = Field(
        min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_:.\-]+$"
    )
    timestamp: datetime
    structured_metadata: dict = Field(default_factory=dict)

    @field_validator('merchant_id','order_id')
    @classmethod
    def nonblank_identity(cls,value):
        if value is not None and (not value.strip() or value!=value.strip()):
            raise ValueError('Идентификатор не должен быть пустым или иметь внешние пробелы')
        return value

    @field_validator("timestamp")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Нужен часовой пояс")
        return value.astimezone(timezone.utc)

    @field_validator("structured_metadata")
    @classmethod
    def metadata_size(cls, value):
        import json

        try:
            encoded = json.dumps(value, allow_nan=False).encode()
        except (ValueError, RecursionError):
            raise ValueError("Metadata должна быть конечным JSON без NaN/Infinity")
        if len(encoded) > 4096:
            raise ValueError("Metadata превышает 4 KiB")
        forbidden = {"pan", "cvv", "cvc", "card_number", "password", "api_key"}

        def keys(v):
            if isinstance(v, dict):
                return {str(k).casefold() for k in v} | set().union(
                    *(keys(x) for x in v.values())
                )
            if isinstance(v, list):
                return set().union(*(keys(x) for x in v))
            return set()

        if keys(value) & forbidden:
            raise ValueError("Секреты и карточные данные запрещены")
        return value


class ApprovalIn(StrictModel):
    action: Literal["approve", "reject"]
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class KeyIn(StrictModel):
    name: Name
    agent_id: str
    expires_days: int = Field(default=30, ge=1, le=90)
    purpose: Literal["agent", "executor"] = "agent"


class NameIn(StrictModel):
    name: Name


class MemberIn(StrictModel):
    email: str = Field(max_length=254)
    role: Literal["developer", "viewer"]


class WebhookIn(StrictModel):
    name: Name
    url: str = Field(max_length=500)


class ConsoleIn(StrictModel):
    prompt: str = Field(min_length=2, max_length=1000)
    mandate_id: str
    idempotency_key: str = Field(min_length=8, max_length=120)


class ProfileIn(StrictModel):
    name: Name


class PasswordIn(StrictModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class GrantIn(StrictModel):
    provider: Literal["local_simulator", "yookassa_sandbox"] = "local_simulator"


class ExecutionIn(StrictModel):
    grant_token: str = Field(min_length=40, max_length=4096)


class MFACodeIn(StrictModel):
    code: str = Field(pattern=r"^\d{6}$")


class CurrentPasswordIn(StrictModel):
    password: str = Field(min_length=1, max_length=128)
