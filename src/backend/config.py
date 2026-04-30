from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "wc-fantasy-2026-dev-secret-change-in-production"
    # Postgres connection URL, e.g. postgresql://user:pass@host:5432/wc_fantasy
    DATABASE_URL: str = "postgresql://wcadmin:wc2026pg!dune@localhost:5432/wc_fantasy"
    # Legacy SQLite path kept for migration scripts; not used at runtime
    DATABASE_PATH: str = "data/wc_fantasy.db"
    SIMULATOR_API_URL: str = ""
    SIMULATOR_ADMIN_KEY: str = ""
    SIMULATOR_TOURNAMENT_ID: int = 1
    CORS_ORIGINS: str = "*"
    JWT_ALGORITHM: str = "HS256"

    model_config = {"env_prefix": "WCF_"}


settings = Settings()
DATABASE_URL = settings.DATABASE_URL
