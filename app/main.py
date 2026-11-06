"""Application factory: wires configuration, database, routers, error handling and static pages."""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app import __version__
from app.api import api_router
from app.config import BASE_DIR, get_settings
from app.database import (
    ensure_database_exists,
    get_engine,
    session_scope,
    wait_for_database,
)
from app.errors import AppError
from app.migrate import upgrade_to_head
from app.services.config import config_service, ensure_defaults
from app.workers.outbox import OutboxWorker

log = logging.getLogger("app")
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    ensure_database_exists()
    wait_for_database()
    if settings.auto_migrate:
        upgrade_to_head()
    with session_scope() as db:
        ensure_defaults(db)
    config_service.invalidate()

    app.state.admin_password = settings.admin_password
    if not app.state.admin_password:
        app.state.admin_password = secrets.token_urlsafe(9)
        print(f"\n  No ADMIN_PASSWORD set. Temporary admin password for this run: {app.state.admin_password}\n")

    worker = OutboxWorker(settings.worker_interval_seconds) if settings.worker_enabled else None
    if worker:
        worker.start()
    log.info("Checkout %s ready", __version__)
    try:
        yield
    finally:
        if worker:
            worker.stop()
        get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Hosted Checkout", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.state.admin_password = None  # set in lifespan

    app.include_router(api_router)
    register_error_handlers(app)
    register_middleware(app)
    register_pages(app)
    return app


# ---------------------------------------------------------------- errors
def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"error": exc.message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"] if part not in ("body", "query"))
        message = first["msg"].removeprefix("Value error, ")
        return JSONResponse({"error": f"{where}: {message}" if where else message}, status_code=400)

    @app.exception_handler(OperationalError)
    async def database_unavailable(_: Request, exc: OperationalError) -> JSONResponse:
        log.error("Database error: %s", exc)
        return JSONResponse({"error": "Database unavailable, please retry"}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


# ---------------------------------------------------------------- middleware
def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def common_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        response.headers["X-Content-Type-Options"] = "nosniff"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if path.startswith("/api/public"):  # the checkout page may be embedded in / called from other origins
            response.headers["Access-Control-Allow-Origin"] = "*"
        if path in ("/admin", "/checkout"):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.options("/api/public/{path:path}", include_in_schema=False)
    async def public_preflight(path: str) -> JSONResponse:
        return JSONResponse(
            {},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )


# ---------------------------------------------------------------- pages
def register_pages(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/admin")

    @app.get("/admin", include_in_schema=False)
    def admin_page() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "admin" / "index.html")

    @app.get("/checkout", include_in_schema=False)
    def checkout_page() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "checkout" / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
