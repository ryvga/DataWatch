from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    SECRET_KEY: str
    FERNET_MASTER_KEY: str
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Multi-tenancy
    BASE_DOMAIN: str = "datawatch.io"
    ADMIN_SUBDOMAIN: str = "admin"  # admin.datawatch.io

    # Database
    DATABASE_URL: str

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # AI — global fallback; per-org key takes priority
    OPENROUTER_API_KEY: str = ""
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # Staff seed — first staff account bootstrapped on startup
    STAFF_EMAIL: str = "admin@datawatch.io"
    STAFF_PASSWORD: str = ""  # must be set in .env for seeding to run
    STAFF_FULL_NAME: str = "DataWatch Admin"

    # Email
    APP_BASE_URL: str = "http://localhost:5173"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    SMTP_TIMEOUT: int = 10
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = "alerts@datawatch.io"

    # PayPal billing
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_WEBHOOK_ID: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def admin_origin(self) -> str:
        return f"https://{self.ADMIN_SUBDOMAIN}.{self.BASE_DOMAIN}"


settings = Settings()
