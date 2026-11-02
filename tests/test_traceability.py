import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def test_traceability_invariant(db):
    """TC-TRACE-01: tidak ada kewajiban tanpa provision_version valid."""
    orphans = db.execute(text("""SELECT o.id FROM compliance.obligation o
        LEFT JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id WHERE pv.id IS NULL""")).fetchall()
    assert orphans == []


def test_published_version_is_immutable(db):
    with pytest.raises(DBAPIError) as e:
        db.execute(text("UPDATE corpus.document_version SET sha256 = repeat('0',64) WHERE state = 'PUBLISHED'"))
    assert "VERSION_IMMUTABLE" in str(e.value)


def test_published_provision_text_is_immutable(db):
    with pytest.raises(DBAPIError) as e:
        db.execute(text("UPDATE corpus.provision_version SET text = 'diubah'"))
    assert "VERSION_IMMUTABLE" in str(e.value)


def test_audit_is_append_only(db):
    db.execute(text("""INSERT INTO platform.audit_event (actor_type, action, object_type, correlation_id)
                       VALUES ('SYSTEM','TEST','test', gen_random_uuid())"""))
    with pytest.raises(DBAPIError) as e:
        db.execute(text("DELETE FROM platform.audit_event"))
    assert "APPEND_ONLY" in str(e.value)
