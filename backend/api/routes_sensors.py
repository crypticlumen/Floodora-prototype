"""Drain sensor feed endpoints."""

from __future__ import annotations

import re
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from backend.services.sensor_provider import get_sensor_reading, sensor_status

router = APIRouter(prefix="/sensors", tags=["Drain Sensors"])


@router.get("/status", summary="Check drain sensor feed configuration")
def get_sensor_status() -> Dict[str, Any]:
    return sensor_status()


@router.get("/current", summary="Fetch current drain telemetry for an Indian PIN")
async def current_sensor_reading(
    pincode: str = Query(pattern=r"^\d{6}$", description="Six-digit Indian PIN mapped to a sensor device"),
) -> Dict[str, Any]:
    if not re.fullmatch(r"\d{6}", pincode):
        raise HTTPException(status_code=422, detail="A six-digit Indian PIN is required.")
    return await get_sensor_reading(pincode)
