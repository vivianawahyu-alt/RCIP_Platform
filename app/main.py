from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.compliance.applicability import router as applicability_router
from app.compliance.findings import router as findings_router
from app.compliance.reporting import router as reporting_router
from app.compliance.router import router as compliance_router
from app.copilot.router import router as copilot_router
from app.corpus.review import router as review_router
from app.corpus.router import router as corpus_router
from app.corpus.sources import router as sources_router  # FR-RKM-001 registri sumber
from app.platform.router import router as platform_router
from app.shared.config import settings
from app.shared.errors import register_error_handlers
from app.shared.schemas import ResponseWrapper

import logging

from app.shared.observability import RequestContextMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings.assert_safe_for_environment()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Saat api menyala: tambahkan korpus dari data/korpus (hasil Pull dari tim) ke database laptop ini.
    Gagal impor tidak menghentikan aplikasi; cukup tercatat di log."""
    if settings.CORPUS_SYNC_AUTO:
        try:
            from app.corpus.sync import import_all
            s = import_all()
            logging.getLogger("rcip.corpus_sync").info("Impor korpus tim: %s", {k: v for k, v in s.items() if v})
        except Exception:  # noqa: BLE001
            logging.getLogger("rcip.corpus_sync").exception(
                "Impor korpus tim gagal; jalankan alembic upgrade head lalu docker compose restart api")
    yield


app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0", docs_url="/docs", lifespan=lifespan,
              description="RCIP API — kontrak v1. Semua endpoint (kecuali /auth/login dan /health) memerlukan Bearer JWT.")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
register_error_handlers(app)

app.include_router(platform_router, prefix="/api/v1")
app.include_router(corpus_router)
app.include_router(sources_router)
app.include_router(review_router)
app.include_router(compliance_router)
app.include_router(applicability_router)
app.include_router(findings_router)
app.include_router(reporting_router)
app.include_router(copilot_router)


@app.get("/health", response_model=ResponseWrapper[dict])
def health():
    return ResponseWrapper(message="RCIP API online", data={"status": "healthy", "environment": settings.ENVIRONMENT})
