from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    DEV_MODE: bool = False
    DATABASE_URL: str = "sqlite:///./data/autoflow.db"
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""
    MAILER_DELAY_MIN: int = 30
    MAILER_DELAY_MAX: int = 90
    MAX_TG_ACCOUNTS: int = 5
    ADMIN_TELEGRAM_USERNAME: str = "Cxentrall"
    ADMIN_TELEGRAM_ID: int | None = None
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    # AI helper (OpenAI-compatible). Leave AI_API_KEY empty to use the built-in
    # keyword fallback for free. Default provider: Groq (free tier).
    AI_API_KEY: str = ""
    AI_API_BASE: str = "https://api.groq.com/openai/v1"
    AI_MODEL: str = "llama-3.3-70b-versatile"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
if not settings.DEV_MODE and settings.SECRET_KEY == "dev-secret":
    raise ValueError("SECRET_KEY must be set! openssl rand -hex 32")
