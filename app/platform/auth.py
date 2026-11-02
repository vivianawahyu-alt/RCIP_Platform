import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.platform.models import AppUser
from app.shared.config import settings
from app.shared.database import get_db
from app.shared.errors import AppError

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, iterations: int = 120_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(calc.hex(), digest)
    except ValueError:
        return False


def create_token(user: AppUser) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp},
                      settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> AppUser:
    if cred is None:
        raise AppError(401, "UNAUTHENTICATED", "Token tidak ditemukan")
    try:
        claims = jwt.decode(cred.credentials, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user = db.get(AppUser, uuid.UUID(claims["sub"]))
    except (JWTError, ValueError, KeyError):
        raise AppError(401, "UNAUTHENTICATED", "Token tidak valid atau kedaluwarsa")
    if user is None:
        raise AppError(401, "UNAUTHENTICATED", "Pengguna tidak ditemukan")
    return user


def require_roles(*roles):
    """Otorisasi server-side. Tanpa argumen = cukup terautentikasi."""
    allowed = {str(r) for r in roles}

    def dep(user: AppUser = Depends(current_user)) -> AppUser:
        if allowed and user.role not in allowed:
            raise AppError(403, "FORBIDDEN", f"Peran {user.role} tidak diizinkan untuk aksi ini")
        return user

    return dep
