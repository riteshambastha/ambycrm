from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),   # look in project root first, then cwd
        env_file_encoding="utf-8",
        env_ignore_empty=True,          # empty OS env vars fall back to .env values
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://amby:amby@localhost:5432/ambycrm"
    DATABASE_URL_SYNC: str = "postgresql://amby:amby@localhost:5432/ambycrm"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Member profile cache TTLs (in seconds)
    CACHE_TTL_EMAILS: int = 4 * 3600       # 4 hours
    CACHE_TTL_FILES: int = 12 * 3600       # 12 hours
    CACHE_TTL_SALESFORCE: int = 6 * 3600   # 6 hours
    CACHE_TTL_MEETINGS: int = 24 * 3600    # 24 hours
    CACHE_MAX_ITEMS: int = 50              # always cache this many items

    # Clerk
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_JWKS_URL: str = "https://api.clerk.com/v1/jwks"

    # Encryption key for OAuth tokens (Fernet 32-byte base64)
    ENCRYPTION_KEY: str = ""

    # Member (OrgEmployee) JWT auth — separate from Clerk
    MEMBER_JWT_SECRET: str = "change-me-member-jwt-secret"
    MEMBER_JWT_EXPIRY_DAYS: int = 30

    # LLM
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "gpt-4o"

    # Email (Resend)
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "noreply@ambycrm.com"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # Recall.ai
    RECALL_API_KEY: str = ""
    RECALL_BASE_URL: str = "https://us-west-2.recall.ai"

    # Apify (LinkedIn enrichment)
    APIFY_API_TOKEN: str = ""


settings = Settings()
