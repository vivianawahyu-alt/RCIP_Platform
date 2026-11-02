import logging

from celery import Celery
from sqlalchemy import select, update

from app.compliance.models import Obligation
from app.platform.models import Outbox
from app.shared.config import settings
from app.shared.database import SessionLocal
from app.shared.vocabularies import ObligationState
from datetime import datetime, timezone

logger = logging.getLogger("rcip.worker")
celery_app = Celery("rcip_tasks", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.beat_schedule = {"outbox-every-10s": {"task": "app.worker.publish_outbox_events", "schedule": 10.0}}


def process_outbox(db) -> int:
    """Perambatan dampak: perubahan material pada pasal -> kewajiban ACTIVE yang mensitasinya jadi REVIEW_REQUIRED."""
    events = db.scalars(select(Outbox).where(Outbox.delivered_at.is_(None)).order_by(Outbox.occurred_at)
                        .limit(50).with_for_update(skip_locked=True)).all()
    for ev in events:
        ev.attempts += 1
        if ev.event_type == "DOCUMENT_CHANGE_MATERIAL":
            ids = ev.payload.get("base_pv_ids", [])
            if ids:
                db.execute(update(Obligation).where(Obligation.primary_citation_id.in_(ids),
                                                    Obligation.state == ObligationState.ACTIVE.value)
                           .values(state=ObligationState.REVIEW_REQUIRED.value))
        ev.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return len(events)


@celery_app.task
def publish_outbox_events() -> int:
    db = SessionLocal()
    try:
        return process_outbox(db)
    finally:
        db.close()
