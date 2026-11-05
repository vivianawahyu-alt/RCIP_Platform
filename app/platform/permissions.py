"""Lapisan FastAPI di atas matriks RBAC (app/shared/rbac_matrix.py).

Pemakaian di endpoint — pilih kapabilitas + huruf aksi dari tabel, BUKAN daftar peran:

    @router.post("/findings")
    def create_finding(..., user: AppUser = Depends(require("finding", "C"))):

Bila satu aksi di tabel boleh dipegang beberapa peran tetapi secara alur kerja hanya satu yang bermakna
(mis. menjawab pertanyaan hukum = Peninjau Hukum), persempit dengan `only=`: izin tetap harus lolos matriks DAN
peran harus termasuk `only` (irisan, tidak pernah memperluas hak akses di luar tabel).
"""
from typing import Iterable, Optional

from fastapi import Depends

from app.platform.auth import current_user
from app.platform.models import AppUser
from app.shared import rbac_matrix as M
from app.shared.errors import AppError

ACTION_ID = {"C": "membuat", "R": "membaca", "U": "mengubah", "D": "menghapus", "A": "menyetujui/menolak",
             "X": "menjalankan aksi"}


def _deny(user: AppUser, capability: str, action: str) -> AppError:
    return AppError(403, "FORBIDDEN",
                    f"Peran {user.role} tidak diizinkan {ACTION_ID.get(action, action)} "
                    f"pada '{M.LABEL_ID.get(capability, capability)}'")


def require(capability: str, action: str, only: Optional[Iterable] = None):
    """Dependency otorisasi server-side berbasis matriks. Mengembalikan AppUser bila lolos, 403 FORBIDDEN bila tidak."""
    assert capability in M.MATRIX, f"kapabilitas tidak dikenal: {capability}"
    assert action in M.VALID_LETTERS, f"huruf aksi tidak dikenal: {action}"
    narrow = {str(r) for r in only} if only is not None else None

    def dep(user: AppUser = Depends(current_user)) -> AppUser:
        if not M.allows(user.role, capability, action) or (narrow is not None and user.role not in narrow):
            raise _deny(user, capability, action)
        return user

    return dep


def require_any(*pairs: tuple[str, str]):
    """Lolos bila peran memenuhi SALAH SATU pasangan (kapabilitas, aksi). Dipakai untuk endpoint gabungan."""
    for cap, act in pairs:
        assert cap in M.MATRIX and act in M.VALID_LETTERS, (cap, act)

    def dep(user: AppUser = Depends(current_user)) -> AppUser:
        if not any(M.allows(user.role, c, a) for c, a in pairs):
            raise _deny(user, pairs[0][0], pairs[0][1])
        return user

    return dep


def allows(user: AppUser, capability: str, action: str) -> bool:
    return M.allows(user.role, capability, action)


def own_only(user: AppUser, capability: str, action: str = "R") -> bool:
    """True bila peran ini hanya boleh menyentuh objek miliknya sendiri untuk aksi tsb (lingkup '/own')."""
    return M.scope_of(user.role, capability, action) == "own"


def ensure_owner(user: AppUser, capability: str, action: str, owner_id, what: str = "objek ini") -> None:
    """Terapkan lingkup 'own': Pemilik Bisnis/Kontrol hanya boleh pada objek miliknya. Peran lain tidak dibatasi."""
    if own_only(user, capability, action) and str(owner_id) != str(user.id):
        raise AppError(403, "OUT_OF_SCOPE", f"{what.capitalize()} bukan milik Anda")