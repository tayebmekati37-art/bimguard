import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (register tables)
from app.api import admin, ai, audit, auth, bim, comparisons, dependencies, documents, impact, insights, notifications, permissions, profiles, projects, reports, rules, validation
from app.core.config import get_settings
from app.core.security import ensure_encryption_declared, ensure_secret_is_safe
from app.db.session import SessionLocal
from app.models.document import ImmutableRevisionError
from app.services import extraction

logging.basicConfig(
    level=get_settings().log_level,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("bimguard.request")


def _requeue_pending() -> None:
    try:
        count = extraction.requeue_pending(SessionLocal)
        if count:
            log.info("Re-queued %s revisions whose model extraction was interrupted", count)
    except Exception:  # noqa: BLE001 - e.g. migrations not applied yet; never block startup
        log.exception("Could not re-queue pending extractions")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_requeue_pending, name="requeue-pending", daemon=True).start()
    yield


def create_app() -> FastAPI:
    ensure_secret_is_safe()
    ensure_encryption_declared()
    app = FastAPI(title="BIMGuard API", version="1.0.0", lifespan=lifespan,
                  description="BIM change-impact and information-consistency engine (prototype).")

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )

    @app.exception_handler(ImmutableRevisionError)
    async def immutable_handler(_request: Request, exc: ImmutableRevisionError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        log.info("request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                 request_id, request.method, request.url.path, response.status_code, ms)
        return response

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    for router in (auth.router, projects.router, documents.router, bim.router, comparisons.router, dependencies.router, impact.router, validation.router, rules.router, insights.router, reports.router, notifications.router, profiles.router, audit.router, ai.router, permissions.router, admin.router):
        app.include_router(router)
    return app


app = create_app()
