"""Seed data sintetis. Idempoten. Memakai SET LOCAL rcip.seeding='on' untuk melewati trigger imutabilitas."""
import argparse
import hashlib
import logging
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select, text

from app.compliance.models import OrganisationProfile
from app.corpus.models import Document, DocumentVersion, Provision, ProvisionVersion
from app.corpus.services import get_or_create_source
from app.platform.auth import hash_password
from app.platform.models import AppUser
from app.shared.database import SessionLocal
from app.shared.vocabularies import AppRole

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rcip.seed")
HERE = Path(__file__).parent

USERS = [("analyst", AppRole.REGULATORY_ANALYST), ("officer", AppRole.COMPLIANCE_OFFICER),
         ("owner", AppRole.BUSINESS_CONTROL_OWNER), ("legal", AppRole.LEGAL_REVIEWER),
         ("manager", AppRole.COMPLIANCE_MANAGER), ("auditor", AppRole.INTERNAL_AUDITOR),
         ("executive", AppRole.EXECUTIVE), ("admin", AppRole.SYSTEM_ADMINISTRATOR)]


def seed(db) -> None:
    db.execute(text("SET LOCAL rcip.seeding = 'on'"))
    for name, role in USERS:
        if not db.scalar(select(AppUser).where(AppUser.username == name)):
            db.add(AppUser(username=name, email=f"{name}@bank-sinar.example", role=role.value,
                           hashed_password=hash_password("demo1234")))

    for spec in yaml.safe_load((HERE / "corpus_manifest.yaml").read_text(encoding="utf-8")):
        if db.scalar(select(Document).where(Document.canonical_number == spec["canonical_number"])):
            continue
        src = get_or_create_source(db, "OJK", "OJK", spec["issuer"], "https://www.ojk.go.id")
        doc = Document(source_id=src.id, canonical_number=spec["canonical_number"], instrument_type=spec["instrument_type"],
                       issuer=spec["issuer"], title_id=spec["title_id"], status="IN_FORCE")
        db.add(doc)
        db.flush()
        for v in spec["versions"]:
            body = "\n".join(p["text"] for p in v["provisions"])
            dv = DocumentVersion(document_id=doc.id, version_number=v["version_number"],
                                 sha256=hashlib.sha256(body.encode()).hexdigest(), origin_url="seed://synthetic",
                                 canonical_text_ref=f"seed/{spec['canonical_number']}/v{v['version_number']}",
                                 effective_date=date.fromisoformat(v["effective_date"]), state="PUBLISHED")
            db.add(dv)
            db.flush()
            for seq, p in enumerate(v["provisions"], start=1):
                key = "PASAL-" + p["label"].split()[-1]
                prov = db.scalar(select(Provision).where(Provision.document_id == doc.id, Provision.provision_key == key))
                if not prov:
                    prov = Provision(document_id=doc.id, provision_key=key, provision_type="PASAL",
                                     number_label=p["label"], hierarchical_path=p["label"])
                    db.add(prov)
                    db.flush()
                db.add(ProvisionVersion(provision_id=prov.id, document_version_id=dv.id, sequence=seq, text=p["text"],
                                        segmentation_confidence=0.95))

    org = yaml.safe_load((HERE / "organisation.yaml").read_text(encoding="utf-8"))
    if not db.scalar(select(OrganisationProfile).where(OrganisationProfile.organisation_name == org["organisation_name"])):
        db.add(OrganisationProfile(**org))


def main() -> None:
    argparse.ArgumentParser().parse_args()
    db = SessionLocal()
    try:
        seed(db)
        db.commit()
        log.info("SEED OK — login: analyst/officer/owner/legal/manager/auditor/executive/admin, password demo1234")
    except Exception:
        db.rollback()
        log.exception("SEED FAILED")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
