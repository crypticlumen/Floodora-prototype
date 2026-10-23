"""Main FastAPI application entrypoint for Floodora Backend.

Smart Drainage Monitoring & Early Flood-Risk Awareness Backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes_risk import router as risk_router
from backend.api.routes_sensors import router as sensors_router
from backend.api.routes_weather import router as weather_router

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

APP_METADATA = {
    "title": "Floodora Backend API",
    "description": (
        "Backend REST API for Floodora: Smart Drainage Monitoring & Early Flood-Risk Awareness.\n\n"
        "Features:\n"
        "- Rule-based explainable drainage risk assessment (F-01, F-02, F-04)\n"
        "- What-if scenario simulator for rainfall and blockage overrides (F-03)\n"
        "- Pre-configured Mumbai flood hotspots and demonstration scenarios\n"
        "- Historical assessment session logging\n\n"
        "Important: Floodora provides decision-support prototype indicators and does not replace official emergency services."
    ),
    "version": "1.0.0",
}

app = FastAPI(
    title=APP_METADATA["title"],
    description=APP_METADATA["description"],
    version=APP_METADATA["version"],
    docs_url="/docs",
    redoc_url="/redoc",
)

# Same-origin dashboard requests need no CORS. Optional origins are for separately
# hosted clients and are configured explicitly by the operator.
cors_origins = [origin.strip() for origin in os.getenv("FLOODORA_CORS_ORIGINS", "").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(risk_router, prefix="/api")
app.include_router(sensors_router, prefix="/api")
app.include_router(weather_router, prefix="/api")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the integrated operator dashboard from the same origin as the API."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    """Open the operator dashboard at the deployment's main URL."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api", summary="API service status", tags=["System"])
def api_root() -> Dict[str, Any]:
    return {
        "name": "Floodora Backend API",
        "version": APP_METADATA["version"],
        "status": "online",
        "dashboard": "/dashboard",
        "documentation": "/docs",
    }


@app.get("/api/health", summary="Health check endpoint", tags=["System"])
def health_check() -> Dict[str, Any]:
    return {
        "name": "Floodora API",
        "status": "healthy",
        "risk_engine": "operational",
        "scenario_simulator": "operational",
        "weather_provider": "Open-Meteo",
        "sensor_feed": "configured" if os.getenv("FLOODORA_SENSOR_URL") else "not_configured",
        "dashboard": "/dashboard",
        "version": APP_METADATA["version"],
    }
