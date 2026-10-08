import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (register tables)
from app.api import audit, auth, bim, documents, projects
from app.core.config import get_settings
from app.models.document import ImmutableRevisionError

logging.basicConfig(
    level=get_settings().log_level,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("bimguard.request")


def create_app() -> FastAPI:
    app = FastAPI(title="BIMGuard API", version="0.3.0",
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

    for router in (auth.router, projects.router, documents.router, bim.router, audit.router):
        app.include_router(router)
    return app


app = create_app()
