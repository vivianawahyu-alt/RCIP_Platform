from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "RCIP Platform"
    ENVIRONMENT: str = "development"

    # Kredensial WAJIB dari environment variable / file .env — tidak ada nilai cadangan di kode.
    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""  
    MINIO_BUCKET_NAME: str = "rcip-corpus"
 

    JWT_SECRET_KEY: str = ""    
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    OPENAI_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gpt-4o-mini"

    # Sinkronisasi korpus tim lewat Git (app/corpus/sync.py): ekspor otomatis saat korpus berubah
    # & impor otomatis saat api menyala. Set false di .env untuk mematikan.
    CORPUS_SYNC_AUTO: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def check_required(self) -> None:
        """Hentikan aplikasi dengan pesan jelas bila kredensial wajib belum diisi di .env."""
        missing = [k for k in ("DATABASE_URL", "JWT_SECRET_KEY") if not getattr(self, k).strip()]
        if missing:
            raise RuntimeError(
                f"Environment variable wajib belum diisi: {', '.join(missing)}. "
                "Salin .env.example menjadi .env lalu lengkapi nilainya (lihat README bagian Keamanan).")

    def assert_safe_for_environment(self) -> None:
        """Tolak start di produksi dengan secret bawaan; peringatan di pengembangan."""
        import logging
        weak = len(self.JWT_SECRET_KEY) < 32 or self.JWT_SECRET_KEY.startswith(("change_this", "dev_only", "ganti"))
        if weak and self.ENVIRONMENT.lower() == "production":
            raise RuntimeError("JWT_SECRET_KEY bawaan/lemah tidak boleh dipakai di production")
        if weak:
            logging.getLogger("rcip.config").warning("JWT_SECRET_KEY bawaan dipakai — hanya untuk pengembangan")


settings = Settings()
settings.check_required()