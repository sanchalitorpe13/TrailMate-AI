"""TrailMate AI application entry point.

Run with:  python -m uvicorn app.main:app --reload
"""

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.routers import journal, missions, stats
from app.schemas import HealthOut
from app.services import ai_service

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("trailmate")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # creates data/trailmate.db and its tables on first run
    logger.info("Database ready at %s", get_settings().database_path)
    yield


app = FastAPI(
    title="TrailMate AI",
    description="A local, open-weight AI nature companion. Read the mission. Lock your phone. Go be here.",
    version="1.0.0",
    lifespan=lifespan,
)

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if not request.url.path.startswith(_DOC_PATHS):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'",
        )
    return response


@app.exception_handler(sqlite3.Error)
async def database_error_handler(request: Request, exc: sqlite3.Error):
    logger.error("Database error on %s: %s", request.url.path, exc, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "A database error occurred. Check the server log for details."},
    )


@app.get("/api/health", response_model=HealthOut, tags=["health"])
def health():
    """App status plus whether local Ollama (and the configured model) is reachable."""
    available, ready = ai_service.check_status()
    return HealthOut(
        status="ok",
        ollama_available=available,
        model_ready=ready,
        model=get_settings().ollama_model,
    )


app.include_router(missions.router)
app.include_router(journal.router)
app.include_router(stats.router)
app.mount("/static", StaticFiles(directory=get_settings().static_dir), name="static")


@app.get("/", include_in_schema=False)
def index():
    page = get_settings().static_dir / "index.html"
    if not page.is_file():
        return HTMLResponse(
            "<h1>TrailMate AI</h1><p>The API is running, but <code>static/index.html</code> "
            "was not found. See the setup instructions.</p>",
            status_code=404,
        )
    return FileResponse(page)