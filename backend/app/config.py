from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://amby:amby@localhost:5432/ambycrm"
    DATABASE_URL_SYNC: str = "postgresql://amby:amby@localhost:5432/ambycrm"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Clerk
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_JWKS_URL: str = "https://api.clerk.com/v1/jwks"

    # Encryption key for OAuth tokens (Fernet 32-byte base64)
    ENCRYPTION_KEY: str = ""

    # LLM
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "gpt-4o"

    # Email (Resend)
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "noreply@ambycrm.com"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"


settings = Settings()
