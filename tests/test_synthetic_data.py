"""Generator data sintetis: reproducible, idempoten, dan seluruh invarian terpenuhi (proposal hal. 20)."""
import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.shared.config import settings

DIGEST = """SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
  SELECT id::text||text AS x FROM corpus.provision_version UNION ALL
  SELECT id::text||state||coalesce(plain_language_summary,'') FROM compliance.obligation UNION ALL
  SELECT id::text||state||severity FROM compliance.finding UNION ALL
  SELECT id::text||outcome FROM platform.approval) t"""


def _run(args, url):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, *args], env=env, capture_output=True, text=True, timeout=300)


@pytest.fixture()
def fresh_dbs():
    base = make_url(settings.DATABASE_URL)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    names = [f"rcip_gen_{uuid.uuid4().hex[:8]}" for _ in range(2)]
    try:
        with admin.connect() as c:
            for n in names:
                c.execute(text(f'CREATE DATABASE "{n}"'))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Tidak dapat membuat database uji: {e}")
    yield [base.set(database=n).render_as_string(hide_password=False) for n in names]
    with admin.connect() as c:
        for n in names:
            c.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{n}'"))
            c.execute(text(f'DROP DATABASE IF EXISTS "{n}"'))


def test_generator_reproducible_and_valid(fresh_dbs):
    digests = []
    for url in fresh_dbs:
        assert _run(["-m", "alembic", "upgrade", "head"], url).returncode == 0
        g = _run(["-m", "seed.generate", "--seed", "7", "--anchor", "2026-10-01"], url)
        assert g.returncode == 0 and "GENERATE OK" in g.stderr + g.stdout, g.stderr[-2000:]
        v = _run(["-m", "seed.validate"], url)
        assert v.returncode == 0, v.stdout
        eng = create_engine(url)
        with eng.connect() as c:
            digests.append(c.execute(text(DIGEST)).scalar())
            assert c.execute(text("SELECT count(*) FROM compliance.finding")).scalar() >= 10
            assert c.execute(text("SELECT count(*) FROM compliance.finding WHERE state='CLOSED'")).scalar() >= 3
            states = {r[0] for r in c.execute(text("SELECT DISTINCT state FROM compliance.obligation"))}
            assert {"ACTIVE", "AI_DRAFT", "REVIEW_REQUIRED"} <= states
        eng.dispose()
    assert digests[0] == digests[1], "seed + anchor yang sama harus menghasilkan data identik"
    # Gate G4: evaluasi copilot (SM-09/SM-10) di atas korpus sintetis
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ev = _run(["-m", "app.ai.evaluate", "--out", tmp], fresh_dbs[0])
        assert ev.returncode == 0 and "ALL TARGETS MET" in ev.stdout, ev.stdout + ev.stderr[-1500:]
    again = _run(["-m", "seed.generate", "--seed", "7"], fresh_dbs[0])
    assert again.returncode == 0 and "sudah ada" in again.stderr + again.stdout
