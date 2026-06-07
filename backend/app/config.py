from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    SECRET_KEY: str
    FERNET_MASTER_KEY: str
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # AI — change LLM_MODEL to swap models without code changes
    OPENROUTER_API_KEY: str = ""
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "nvidia/nemotron-3-ultra-550b-a55b:free"

    # Multi-tenancy
    BASE_DOMAIN: str = "panopta.app"

    # Email
    APP_BASE_URL: str = "http://localhost:5173"
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = "alerts@panopta.app"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    SMTP_TIMEOUT: int = 10

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
