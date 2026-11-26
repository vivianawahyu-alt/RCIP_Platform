"""Membuat nilai rahasia acak untuk file .env.

    python scripts/gen_secret_key.py
    docker compose run --rm --no-deps api python scripts/gen_secret_key.py   (lewat Docker)

Salin baris hasilnya ke file .env. Jangan bagikan/commit nilainya.
"""
import secrets

print(f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}")
print("# Opsional, hanya untuk database BARU (samakan juga password di DATABASE_URL):")
print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")