from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASHANA_", hide_input_in_errors=True)

    db_host: str = "127.0.0.1"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "ashana"
    db_user: str = "ashana_app"
    db_password: SecretStr
    environment: Literal["local", "test", "production"] = "production"
    demo_identity: bool = False
    cookie_secure: bool = True
    allowed_origins: list[str] = Field(default_factory=list)
    session_seconds: int = Field(default=43200, ge=60, le=86400)

    order_cutoff_minutes: int = Field(default=15, ge=1, le=1440)
    order_slot_minutes: int = Field(default=10, ge=1, le=120)
    order_slot_capacity: int = Field(default=10, ge=1, le=1000)
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str = ""

    order_max_active: int = Field(default=2, ge=1, le=20)
    order_max_portions: int = Field(default=10, ge=1, le=100)
    order_reservation_seconds: int = Field(default=300, ge=60, le=1800)
    order_pickup_grace_minutes: int = Field(default=60, ge=0, le=1440)

    @property
    def guest_cookie(self) -> str:
        return "__Host-ashana_guest" if self.cookie_secure else "ashana_guest"

    @model_validator(mode="after")
    def secure_environment(self) -> "Settings":
        if self.environment == "production" and (self.demo_identity or not self.cookie_secure):
            raise ValueError("Небезопасные настройки недоступны вне локального режима")
        return self

    @property
    def session_cookie(self) -> str:
        return "__Host-ashana_session" if self.cookie_secure else "ashana_session"

    @property
    def csrf_cookie(self) -> str:
        return "__Host-ashana_csrf" if self.cookie_secure else "ashana_csrf"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
