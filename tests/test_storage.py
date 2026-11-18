import pytest

from app.shared import storage


def test_put_and_get_object_local(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", True)

    content = b"RCIP storage test"

    assert storage.put_object("test/document.pdf", content) is True
    assert (tmp_path / "test" / "document.pdf").read_bytes() == content
    assert storage.get_object("test/document.pdf") == content


def test_get_missing_object_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", True)

    assert storage.get_object("missing/document.pdf") is None


def test_invalid_path_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", True)

    assert storage.put_object("../outside.txt", b"invalid") is False


def test_put_object_falls_back_to_local(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", False)

    def fail_client():
        raise ConnectionError("MinIO unavailable")

    monkeypatch.setattr(storage, "_client", fail_client)

    content = b"local fallback test"
    assert storage.put_object("fallback/document.pdf", content) is True
    assert (tmp_path / "fallback" / "document.pdf").read_bytes() == content
    assert storage.get_object("fallback/document.pdf") == content
    assert storage._minio_down is True

def test_get_object_rejects_path_traversal(tmp_path, monkeypatch):
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    outside_file = tmp_path / "outside.txt"
    outside_file.write_bytes(b"must not be accessible")

    monkeypatch.setattr(storage, "LOCAL_ROOT", storage_root)
    monkeypatch.setattr(storage, "_minio_down", True)

    assert storage.get_object("../outside.txt") is None

def test_object_exists_local(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", True)

    file_path = tmp_path / "test" / "document.pdf"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"test PDF")

    assert storage.object_exists("test/document.pdf") is True


def test_object_exists_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", True)

    assert storage.object_exists("missing/document.pdf") is False


def test_object_exists_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(storage, "_minio_down", True)

    assert storage.object_exists("../outside.txt") is False