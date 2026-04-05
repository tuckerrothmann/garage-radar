"""
Garage Radar — FastAPI application factory.

Run dev server:
    uvicorn garage_radar.api:app --reload --port 8000

Endpoints:
    GET  /listings              paginated + filtered listing search
    GET  /listings/{id}         detail with price_history + alerts
    GET  /comps                 paginated + filtered completed sales
    GET  /comps/clusters        pre-computed price bands per spec cluster
    GET  /vehicles/profile      curated + inferred make/model profile
    GET  /alerts                paginated alert list (default: open)
    GET  /alerts/{id}           single alert
    PATCH /alerts/{id}/status   transition status (open→read→dismissed)
    POST  /alerts/dismiss-all   bulk dismiss

    GET  /health                service health check
    GET  /scheduler/status      scheduler job status

The APScheduler instance is started/stopped via the FastAPI lifespan so it
shares the same event loop as the ASGI server. Set the DISABLE_SCHEDULER=1
environment variable to skip scheduler startup (useful in test/staging).
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from garage_radar.api.routers.alerts import router as alerts_router
from garage_radar.api.routers.comps import router as comps_router
from garage_radar.api.routers.listings import router as listings_router
from garage_radar.api.routers.vehicles import router as vehicles_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start scheduler on startup; stop it on shutdown."""
    scheduler = None
    if not os.getenv("DISABLE_SCHEDULER"):
        from garage_radar.scheduler import start_scheduler, stop_scheduler
        scheduler = start_scheduler()

    yield

    if scheduler is not None:
        from garage_radar.scheduler import stop_scheduler
        stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Garage Radar",
        description="Collector vehicle market intelligence API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_methods=["GET", "PATCH", "POST"],
        allow_headers=["*"],
    )

    app.include_router(listings_router)
    app.include_router(comps_router)
    app.include_router(vehicles_router)
    app.include_router(alerts_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/scheduler/status", tags=["meta"])
    async def scheduler_status() -> dict:
        """Return the next scheduled run times for each job."""
        if os.getenv("DISABLE_SCHEDULER"):
            return {"scheduler": "disabled", "jobs": []}
        from garage_radar.scheduler import get_scheduler
        sched = get_scheduler()
        jobs = [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in sched.get_jobs()
        ]
        return {"scheduler": "running" if sched.running else "stopped", "jobs": jobs}

    return app


app = create_app()
