"""RG Lighthouse — P2P discovery and bootstrap node for the ResonantGenesis network."""

import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ── Environment ──
IS_PRODUCTION = os.getenv("RG_ENV", "development") == "production"

# Optional shared imports for Docker compatibility
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from shared.errors import setup_exception_handlers
    HAS_SHARED_ERRORS = True
except ImportError:
    HAS_SHARED_ERRORS = False
    setup_exception_handlers = None

from .routers import router
from .discovery_server import discovery_server
from .config import settings


# ── Security Headers Middleware ──
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start discovery TCP server on startup, stop on shutdown."""
    logger.info("RG Lighthouse starting...")
    discovery_server.node_id = settings.NODE_ID
    discovery_server.port = settings.P2P_PORT
    await discovery_server.start()
    yield
    await discovery_server.stop()
    logger.info("RG Lighthouse stopped")


# ── CORS: env-configurable allowed origins ──
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _cors_origins:
    ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(",") if o.strip()]
elif IS_PRODUCTION:
    ALLOWED_ORIGINS = [
        "https://dev-swat.com",
        "https://www.dev-swat.com",
    ]
else:
    ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

app = FastAPI(
    title="RG Lighthouse",
    description="P2P discovery and bootstrap node — the entry point for all nodes joining the ResonantGenesis network",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

if HAS_SHARED_ERRORS and setup_exception_handlers:
    setup_exception_handlers(app)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Internal-Key"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"service": "rg-lighthouse", "version": "0.1.0", "role": "bootstrap-node"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rg-lighthouse"}
