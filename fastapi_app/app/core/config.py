from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- database ---
    postgres_user: str = "myuser"
    postgres_password: str  # required — must come from .env
    postgres_db: str = "arpatentdb"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # --- redis / celery ---
    redis_url: str = "redis://redis:6379/0"

    # --- media storage ---
    media_root: str = "/app/media"
    media_volume_name: str = "arpatent_media_data"

    # --- JWT ---
    jwt_secret_key: str  # required — must come from .env
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # --- CORS ---
    cors_origins: str = "http://localhost:5173"

    # --- debug ---
    debug: bool = False

    @property
    def database_url(self) -> str:
        """Async URL for FastAPI (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync URL for Celery workers (psycopg2 driver)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
