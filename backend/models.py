"""Pydantic schemas and data contracts for Floodora Backend API.

Enforces strict input validation according to PRD F-04 and provides structured
responses according to PRD Section 10.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class DataModeEnum(str, Enum):
    SIMULATED = "simulated"
    HISTORICAL = "historical"
    LIVE = "live"
    MIXED = "mixed"


class RiskLevelEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DrainageReadingInput(BaseModel):
    water_level_cm: float = Field(
        ...,
        ge=0.0,
        description="Current water level measured in centimetres (non-negative numeric).",
        examples=[35.0],
    )
    capacity_cm: float = Field(
        ...,
        gt=0.0,
        description="Drain cross-sectional reference depth or capacity in centimetres (positive numeric).",
        examples=[100.0],
    )
    rainfall_mm_h: float = Field(
        ...,
        ge=0.0,
        description="Rainfall intensity in millimetres per hour (non-negative numeric).",
        examples=[22.5],
    )
    blockage_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Drain blockage percentage from debris or siltation (0 to 100).",
        examples=[40.0],
    )
    flow_drop_pct: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Optional outflow reduction percentage (0 to 100). Defaults to 0.0.",
        examples=[15.0],
    )
    location_id: Optional[str] = Field(
        default="LOC-01",
        description="Monitored drain location identifier.",
        examples=["LOC-01"],
    )
    location_name: Optional[str] = Field(
        default="Monitored Culvert",
        description="Human readable name of the drainage point.",
        examples=["Dadar TT Culvert #4"],
    )
    data_mode: Optional[DataModeEnum] = Field(
        default=DataModeEnum.SIMULATED,
        description="Data ingestion mode: simulated, historical, or live.",
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Optional ISO 8601 reading timestamp.",
    )

    @field_validator("capacity_cm")
    @classmethod
    def check_capacity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Drain capacity must be greater than 0 cm.")
        return v


class RiskComponentsModel(BaseModel):
    water_fill_pct: float = Field(..., description="Calculated water fill percentage, capped at 100%.")
    water_fill_component: float = Field(..., description="Weighted contribution from water fill (weight 35%).")
    blockage_pct: float = Field(..., description="Blockage percentage (0-100).")
    blockage_component: float = Field(..., description="Weighted contribution from blockage (weight 25%).")
    rainfall_normalized: float = Field(..., description="Rainfall score normalized against 50 mm/h benchmark.")
    rainfall_component: float = Field(..., description="Weighted contribution from rainfall (weight 20%).")
    flow_drop_pct: float = Field(..., description="Flow drop percentage (0-100).")
    flow_drop_component: float = Field(..., description="Weighted contribution from flow drop (weight 20%).")
    raw_score: float = Field(..., description="Unrounded sum of all 4 weighted components.")


class RiskAssessmentResponse(BaseModel):
    risk_score: int = Field(..., ge=0, le=100, description="Heuristic risk score from 0 to 100.")
    risk_level: RiskLevelEnum = Field(..., description="Risk category: LOW, MEDIUM, HIGH, or CRITICAL.")
    category: RiskLevelEnum = Field(..., description="Alias for risk_level.")
    risk_components: RiskComponentsModel = Field(..., description="Detailed breakdown of individual factors.")
    factors: List[str] = Field(..., description="Human-explainable factors driving the score.")
    recommended_action: List[str] = Field(..., description="Operational inspection and preparedness actions.")
    data_mode: str = Field(..., description="Indicates whether data is simulated, historical, or live.")
    assessment_timestamp: str = Field(..., description="ISO 8601 timestamp of evaluation.")
    location_id: str = Field(..., description="Monitored drainage location ID.")
    location_name: str = Field(..., description="Name of the monitored location.")
    input_quality_status: str = Field(..., description="Quality flag (e.g. valid, warning if level exceeds capacity).")
    disclaimer: str = Field(..., description="Prototype assumptions and limitations note.")


class ScenarioOverridesInput(BaseModel):
    rainfall_mm_h: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Override rainfall intensity in mm/h.",
        examples=[45.0],
    )
    blockage_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Override drain blockage percentage (0-100).",
        examples=[70.0],
    )
    water_level_cm: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Override water level in cm.",
    )
    flow_drop_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Override flow drop percentage (0-100).",
    )
    scenario_name: Optional[str] = Field(
        default="What-If Scenario",
        description="Descriptive name for the scenario.",
    )


class SimulationRequest(BaseModel):
    baseline: DrainageReadingInput = Field(
        ...,
        description="Baseline drainage reading before hypothetical modification.",
    )
    overrides: ScenarioOverridesInput = Field(
        ...,
        description="Hypothetical parameter changes (rainfall, blockage, etc.).",
    )


class SimulationResponse(BaseModel):
    scenario_name: str
    baseline: RiskAssessmentResponse
    scenario: RiskAssessmentResponse
    score_delta: int = Field(..., description="Numeric difference: scenario_score - baseline_score.")
    direction: str = Field(..., description="'increased', 'decreased', or 'unchanged'.")
    category_changed: bool = Field(..., description="True if the risk category changed.")
    summary: str = Field(..., description="Summary explanation of the delta.")
    component_deltas: Dict[str, float] = Field(..., description="Delta for each weighted component.")


class MonitoredLocation(BaseModel):
    location_id: str
    name: str
    ward: str
    city: str = "Mumbai"
    latitude: float
    longitude: float
    capacity_cm: float
    drain_type: str
    critical_threshold_cm: float
    current_readings: DrainageReadingInput


class DemoScenarioPreset(BaseModel):
    id: str
    title: str
    description: str
    suggested_role: str
    readings: DrainageReadingInput
    default_overrides: ScenarioOverridesInput
