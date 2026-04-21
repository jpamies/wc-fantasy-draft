from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "wc-fantasy-2026-dev-secret-change-in-production"
    DATABASE_PATH: str = "data/wc_fantasy.db"
    TRANSFERMARKT_DATA_DIR: str = "data/transfermarkt"
    CORS_ORIGINS: str = "*"
    JWT_ALGORITHM: str = "HS256"

    model_config = {"env_prefix": "WCF_"}


settings = Settings()
