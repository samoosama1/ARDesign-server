from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- database ---
    postgres_user: str = "myuser"
    postgres_password: str = "samet123"
    postgres_db: str = "arpatentdb"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # --- redis / celery ---
    redis_url: str = "redis://redis:6379/0"

    # --- media storage ---
    # Path inside the API / worker container
    media_root: str = "/app/media"
    # Named Docker volume that holds the media files.
    # The worker passes this directly to `docker run -v <name>:/app/media` (DooD).
    # Matches the compose project name "arpatent" + "_media_data".
    media_volume_name: str = "arpatent_media_data"

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
