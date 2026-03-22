"""
Garage Radar — FastAPI application factory.

Run dev server:
    uvicorn garage_radar.api:app --reload --port 8000

Endpoints:
    GET  /listings              paginated + filtered listing search
    GET  /listings/{id}         detail with price_history + alerts
    GET  /comps                 paginated + filtered completed sales
    GET  /comps/clusters        pre-computed price bands per spec cluster
    GET  /alerts                paginated alert list (default: open)
    GET  /alerts/{id}           single alert
    PATCH /alerts/{id}/status   transition status (open→read→dismissed)
    POST  /alerts/dismiss-all   bulk dismiss

    GET  /health                service health check
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from garage_radar.api.routers.alerts import router as alerts_router
from garage_radar.api.routers.comps import router as comps_router
from garage_radar.api.routers.listings import router as listings_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Garage Radar",
        description="Air-cooled 911 market intelligence API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_methods=["GET", "PATCH", "POST"],
        allow_headers=["*"],
    )

    app.include_router(listings_router)
    app.include_router(comps_router)
    app.include_router(alerts_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
