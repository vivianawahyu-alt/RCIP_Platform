import io
import logging
from pathlib import Path

from app.shared.config import settings

logger = logging.getLogger("rcip.storage")
# Cadangan lokal bila MinIO tidak dijalankan (docker-compose saat ini menonaktifkan MinIO).
LOCAL_ROOT = Path(__file__).resolve().parents[2] / "storage"
_minio_down = False  # di-cache agar unggahan berikutnya tidak menunggu retry koneksi


def _client():
    import urllib3
    from minio import Minio

    http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=10), retries=urllib3.Retry(total=0))
    return Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY,
                 secret_key=settings.MINIO_SECRET_KEY, secure=False, http_client=http)


def _local_path(key: str) -> Path:
    p = (LOCAL_ROOT / key).resolve()
    if LOCAL_ROOT.resolve() not in p.parents:
        raise ValueError("object key tidak valid")
    return p


def put_object(key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    """Simpan ke MinIO; bila tidak tersedia, simpan ke folder ./storage agar bukti tetap dapat diunduh."""
    global _minio_down
    try:
        if _minio_down:
            raise ConnectionError("MinIO ditandai tidak tersedia")
        client = _client()
        if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
            client.make_bucket(settings.MINIO_BUCKET_NAME)
        client.put_object(settings.MINIO_BUCKET_NAME, key, io.BytesIO(data), len(data), content_type=content_type)
        return True
    except Exception as e:  # noqa: BLE001
        _minio_down = True
        logger.info("MinIO tidak tersedia (%s); menyimpan %s ke penyimpanan lokal", e.__class__.__name__, key)
    try:
        p = _local_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Objek %s tidak tersimpan: %s", key, e)
        return False


def get_object(key: str) -> bytes | None:
    try:
        p = _local_path(key)
        if p.exists():
            return p.read_bytes()
    except ValueError:
        return None
    if _minio_down:
        return None
    try:
        resp = _client().get_object(settings.MINIO_BUCKET_NAME, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    except Exception:  # noqa: BLE001
        return None
