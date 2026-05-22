from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "wc-fantasy-local-dev-secret-change-me"
    # Use env var in real environments. Local fallback intentionally has no credentials.
    DATABASE_URL: str = "postgresql://localhost:5432/wc_fantasy"
    # Legacy SQLite path kept for migration scripts; not used at runtime
    DATABASE_PATH: str = "data/wc_fantasy.db"
    SIMULATOR_API_URL: str = ""
    CORS_ORIGINS: str = "*"
    JWT_ALGORITHM: str = "HS256"

    model_config = {"env_prefix": "WCF_"}


settings = Settings()
DATABASE_URL = settings.DATABASE_URL
