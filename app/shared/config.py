from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "RCIP Platform"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+psycopg://rcip:rcip_dev_password@localhost:5432/rcip_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "rcip_minio"
    MINIO_SECRET_KEY: str = "rcip_minio_secret"
    MINIO_BUCKET_NAME: str = "rcip-corpus"

    JWT_SECRET_KEY: str = "dev_only_secret_change_in_prod_32chars_min"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    OPENAI_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def assert_safe_for_environment(self) -> None:
        """Tolak start di produksi dengan secret bawaan; peringatan di pengembangan."""
        import logging
        weak = len(self.JWT_SECRET_KEY) < 32 or self.JWT_SECRET_KEY.startswith(("change_this", "dev_only"))
        if weak and self.ENVIRONMENT.lower() == "production":
            raise RuntimeError("JWT_SECRET_KEY bawaan/lemah tidak boleh dipakai di production")
        if weak:
            logging.getLogger("rcip.config").warning("JWT_SECRET_KEY bawaan dipakai — hanya untuk pengembangan")


settings = Settings()
