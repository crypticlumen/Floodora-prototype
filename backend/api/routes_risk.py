"""Drainage risk assessment and what-if simulation API routes."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.data_store import DEMO_SCENARIOS, MONITORED_LOCATIONS, history_store
from backend.models import (
    DemoScenarioPreset,
    DrainageReadingInput,
    MonitoredLocation,
    RiskAssessmentResponse,
    SimulationRequest,
    SimulationResponse,
)
from backend.services.risk_service import evaluate_drainage_risk
from backend.services.simulation_service import run_scenario_simulation

router = APIRouter(tags=["Drainage Risk & Simulator"])


@router.post(
    "/assess",
    response_model=RiskAssessmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess drainage risk from sensor/simulated readings",
    description=(
        "Computes a transparent weighted heuristic risk score (0-100) and risk category "
        "(LOW, MEDIUM, HIGH, CRITICAL) from water level, capacity, rainfall, blockage, "
        "and optional flow-drop percentage. Returns explainable factors and recommended actions."
    ),
)
@router.post("/risk/assess", response_model=RiskAssessmentResponse, include_in_schema=False)
def assess_drainage_risk(reading: DrainageReadingInput) -> RiskAssessmentResponse:
    try:
        assessment = evaluate_drainage_risk(reading)
        # Log to in-memory history store for session audit trail
        history_store.add(assessment.model_dump())
        return assessment
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation error: {str(ve)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Risk evaluation failure: {str(e)}",
        )


@router.post(
    "/simulate",
    response_model=SimulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate what-if scenario against baseline readings",
    description=(
        "Applies hypothetical overrides (e.g. increase in rainfall or blockage) to a baseline "
        "reading without mutating the original input. Returns score difference, direction, "
        "category changes, and component comparisons."
    ),
)
@router.post("/risk/simulate", response_model=SimulationResponse, include_in_schema=False)
def simulate_what_if_scenario(req: SimulationRequest) -> SimulationResponse:
    try:
        return run_scenario_simulation(req.baseline, req.overrides)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Simulation validation error: {str(ve)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulation failure: {str(e)}",
        )


@router.get(
    "/locations",
    response_model=List[MonitoredLocation],
    summary="List monitored drainage locations",
    description="Returns pre-configured monitored drainage culverts, subway drains, and outfalls.",
)
def get_locations() -> List[MonitoredLocation]:
    return MONITORED_LOCATIONS


@router.get(
    "/locations/{location_id}",
    response_model=MonitoredLocation,
    summary="Get monitored location details",
)
def get_location_detail(location_id: str) -> MonitoredLocation:
    for loc in MONITORED_LOCATIONS:
        if loc.location_id.upper() == location_id.upper():
            return loc
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Location '{location_id}' not found.",
    )


@router.get(
    "/scenarios",
    response_model=List[DemoScenarioPreset],
    summary="List preset demonstration scenarios",
    description="Returns baseline scenarios and suggested what-if overrides for hackathon demonstration.",
)
def get_scenarios() -> List[DemoScenarioPreset]:
    return DEMO_SCENARIOS


@router.get(
    "/history",
    summary="Get recent assessment history",
    description="Returns recent drainage assessments stored during this session.",
)
def get_assessment_history(
    limit: int = Query(default=20, ge=1, le=100),
    location_id: Optional[str] = Query(default=None),
) -> List[dict]:
    if location_id:
        items = history_store.get_by_location(location_id)
        return items[:limit]
    return history_store.get_all(limit=limit)
