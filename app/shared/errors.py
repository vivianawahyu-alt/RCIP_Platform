"""Amplop error konsisten (TRD §8.2): RFC 7807 + field lama (error_code/message) agar klien lama tetap jalan."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.observability import correlation_id

log = logging.getLogger("rcip.error")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, offending: dict | None = None):
        self.status, self.code, self.message, self.offending = status, code, message, offending
        super().__init__(f"{code}: {message}")


def _body(request: Request, status: int, code: str, message: str, offending=None) -> dict:
    return {"success": False, "error_code": code, "message": message, "data": None,
            "type": f"https://rcip.ukdw.ac.id/errors/{code.lower().replace('_', '-')}",
            "title": code.replace("_", " ").title(), "status": status, "code": code, "detail": message,
            "instance": request.url.path, "correlation_id": correlation_id.get(), "offending": offending}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content=_body(request, exc.status, exc.code, exc.message, exc.offending))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errs = exc.errors()
        first = errs[0] if errs else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "body"
        msg = f"{field}: {first.get('msg', 'tidak valid')}"
        return JSONResponse(status_code=422, content=_body(request, 422, "VALIDATION_ERROR", msg,
                                                           {"field": field, "errors": len(errs)}))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error correlation_id=%s", correlation_id.get())
        return JSONResponse(status_code=500, content=_body(request, 500, "INTERNAL_ERROR",
                                                           "Terjadi kesalahan internal; laporkan correlation_id ini"))
