"""RG Lighthouse — P2P discovery and bootstrap node for the ResonantGenesis network."""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

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


app = FastAPI(
    title="RG Lighthouse",
    description="P2P discovery and bootstrap node — the entry point for all nodes joining the ResonantGenesis network",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

if HAS_SHARED_ERRORS and setup_exception_handlers:
    setup_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"service": "rg-lighthouse", "version": "0.1.0", "role": "bootstrap-node"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rg-lighthouse"}
