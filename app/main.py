"""CourtVision FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import agent, nba, roster, simulation
from app.config import settings
from app.gateway.cache import cache

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await cache.connect()
    logger.info("CourtVision v%s started", __version__)
    yield
    await cache.disconnect()
    logger.info("CourtVision shut down")


app = FastAPI(
    title="CourtVision",
    description=(
        "Autonomous NBA GM Agent — AI-driven predictive analytics platform "
        "that evaluates NBA rosters and models team win distributions."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(nba.router, prefix="/api/v1")
app.include_router(roster.router, prefix="/api/v1")
app.include_router(simulation.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api")
async def api_info():
    return {
        "name": "CourtVision",
        "version": __version__,
        "description": "Autonomous NBA GM Agent",
        "docs": "/docs",
        "endpoints": {
            "nba_gateway": "/api/v1/nba",
            "roster": "/api/v1/roster",
            "simulation": "/api/v1/simulate",
            "agent": "/api/v1/agent",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "version": __version__}


# Serve the frontend (static SPA) at the root
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def frontend():
    return FileResponse(STATIC_DIR / "index.html")
