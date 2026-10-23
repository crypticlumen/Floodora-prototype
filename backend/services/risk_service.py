"""Backend Drainage Risk Evaluation Service.

Calculates the prototype weighted heuristic risk score (0-100) and category:
- Water-level fill percentage (35% weight, capped at 100%)
- Blockage percentage (25% weight)
- Normalized rainfall score (20% weight, normalized against 50 mm/h)
- Flow-drop percentage (20% weight, default 0%)

Categories:
- 0–24:   LOW
- 25–49:  MEDIUM
- 50–74:  HIGH
- 75–100: CRITICAL
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from backend.models import (
    DrainageReadingInput,
    RiskAssessmentResponse,
    RiskComponentsModel,
    RiskLevelEnum,
)

CATEGORY_THRESHOLDS: List[Tuple[int, int, RiskLevelEnum]] = [
    (0, 24, RiskLevelEnum.LOW),
    (25, 49, RiskLevelEnum.MEDIUM),
    (50, 74, RiskLevelEnum.HIGH),
    (75, 100, RiskLevelEnum.CRITICAL),
]

PROTOTYPE_DISCLAIMER = (
    "Prototype heuristic risk score for decision support only. "
    "Rainfall is normalized against 50 mm/h and water level fill is capped at 100%. "
    "These weights are uncalibrated against field outcomes and must not replace official "
    "warnings, certified hydrological models, or human operational review."
)


def determine_risk_category(score: int) -> RiskLevelEnum:
    clamped_score = max(0, min(100, score))
    for lower, upper, cat in CATEGORY_THRESHOLDS:
        if lower <= clamped_score <= upper:
            return cat
    return RiskLevelEnum.CRITICAL


def generate_factors(
    fill_pct: float,
    blockage_pct: float,
    rainfall_mm_h: float,
    rainfall_normalized: float,
    flow_drop_pct: float,
    water_fill_comp: float,
    blockage_comp: float,
    rainfall_comp: float,
    flow_drop_comp: float,
) -> List[str]:
    factors: List[str] = []

    # Water fill factor
    if fill_pct >= 90:
        factors.append(f"Near full/overflowing drain: water level is {fill_pct:.1f}% of capacity (+{water_fill_comp:.1f} pts)")
    elif fill_pct >= 60:
        factors.append(f"Substantial water accumulation: water level is {fill_pct:.1f}% of capacity (+{water_fill_comp:.1f} pts)")
    elif fill_pct >= 30:
        factors.append(f"Moderate water fill: {fill_pct:.1f}% of capacity (+{water_fill_comp:.1f} pts)")
    else:
        factors.append(f"Safe water fill level: {fill_pct:.1f}% of capacity (+{water_fill_comp:.1f} pts)")

    # Blockage factor
    if blockage_pct >= 75:
        factors.append(f"Severe physical drain blockage at {blockage_pct:.1f}% (+{blockage_comp:.1f} pts)")
    elif blockage_pct >= 40:
        factors.append(f"Moderate debris / grate constriction at {blockage_pct:.1f}% (+{blockage_comp:.1f} pts)")
    elif blockage_pct > 10:
        factors.append(f"Minor blockage detected at {blockage_pct:.1f}% (+{blockage_comp:.1f} pts)")
    else:
        factors.append(f"Drain pathway clear with {blockage_pct:.1f}% blockage (+{blockage_comp:.1f} pts)")

    # Rainfall factor
    if rainfall_mm_h >= 50:
        factors.append(f"Extreme torrential rainfall ({rainfall_mm_h:.1f} mm/h >= 50 mm/h benchmark, capped at +{rainfall_comp:.1f} pts)")
    elif rainfall_mm_h >= 25:
        factors.append(f"Heavy rain intensity at {rainfall_mm_h:.1f} mm/h ({rainfall_normalized:.1f}% benchmark, +{rainfall_comp:.1f} pts)")
    elif rainfall_mm_h > 5:
        factors.append(f"Moderate precipitation at {rainfall_mm_h:.1f} mm/h (+{rainfall_comp:.1f} pts)")
    else:
        factors.append(f"Minimal or no active rainfall ({rainfall_mm_h:.1f} mm/h, +{rainfall_comp:.1f} pts)")

    # Flow drop factor
    if flow_drop_pct >= 50:
        factors.append(f"Critical discharge restriction: flow reduced by {flow_drop_pct:.1f}% (+{flow_drop_comp:.1f} pts)")
    elif flow_drop_pct >= 20:
        factors.append(f"Partial outflow impedance: flow drop at {flow_drop_pct:.1f}% (+{flow_drop_comp:.1f} pts)")
    elif flow_drop_pct > 0:
        factors.append(f"Slight flow attenuation at {flow_drop_pct:.1f}% (+{flow_drop_comp:.1f} pts)")

    return factors


def generate_recommendations(
    category: RiskLevelEnum,
    fill_pct: float,
    blockage_pct: float,
    rainfall_mm_h: float,
    flow_drop_pct: float,
) -> List[str]:
    recs: List[str] = []

    if category == RiskLevelEnum.CRITICAL:
        recs.append("IMMEDIATE ACTION: Dispatch emergency drainage maintenance crew to site.")
        recs.append("Deploy auxiliary mobile dewatering pumps to avert street-level inundation.")
        if blockage_pct > 30:
            recs.append("Emergency jetting/clearing of intake grates and culvert barrel required.")
        recs.append("Coordinate with local ward traffic control for potential road diversion.")
        recs.append("Maintain continuous radio contact with facility coordinators.")

    elif category == RiskLevelEnum.HIGH:
        recs.append("PRIORITY: Schedule rapid inspection crew within 30-60 minutes.")
        if blockage_pct >= 40:
            recs.append("Clear trash screens and remove silt accumulation from culvert mouth.")
        if fill_pct >= 70:
            recs.append("Prepare backup pumping units and inspect downstream outfall discharge.")
        recs.append("Increase telemetry monitoring frequency and monitor radar storm track.")

    elif category == RiskLevelEnum.MEDIUM:
        recs.append("ROUTINE INSPECTION: Queue inspection during regular operational shift.")
        if blockage_pct >= 30:
            recs.append("Schedule debris clearance at drain entrance before next rain event.")
        recs.append("Verify outfall tidal gate or gravity flap is functioning properly.")
        recs.append("Monitor localized rainfall forecasts for convective cell development.")

    else:  # LOW
        recs.append("NOMINAL STATUS: Continue standard automated monitoring cycle.")
        recs.append("No immediate physical dispatch needed.")
        if blockage_pct > 15:
            recs.append("Log minor blockage for next scheduled preventive maintenance round.")

    return recs


def evaluate_drainage_risk(reading: DrainageReadingInput) -> RiskAssessmentResponse:
    # 1. Validation check
    if reading.capacity_cm <= 0:
        raise ValueError("Drain capacity must be greater than 0 cm.")
    if reading.water_level_cm < 0:
        raise ValueError("Water level cannot be negative.")
    if reading.rainfall_mm_h < 0:
        raise ValueError("Rainfall intensity cannot be negative.")
    if reading.blockage_pct < 0 or reading.blockage_pct > 100:
        raise ValueError("Blockage percentage must be between 0 and 100.")
    flow_drop = reading.flow_drop_pct or 0.0
    if flow_drop < 0 or flow_drop > 100:
        raise ValueError("Flow drop percentage must be between 0 and 100.")

    # 2. Heuristic component scoring
    raw_fill_pct = (reading.water_level_cm / reading.capacity_cm) * 100.0
    fill_pct = min(100.0, raw_fill_pct)
    water_fill_component = 0.35 * fill_pct

    blockage_pct = float(reading.blockage_pct)
    blockage_component = 0.25 * blockage_pct

    rainfall_normalized = min(100.0, (reading.rainfall_mm_h / 50.0) * 100.0)
    rainfall_component = 0.20 * rainfall_normalized

    flow_drop_component = 0.20 * flow_drop

    raw_score = (
        water_fill_component
        + blockage_component
        + rainfall_component
        + flow_drop_component
    )
    risk_score = int(min(100, round(raw_score)))

    # 3. Category
    risk_level = determine_risk_category(risk_score)

    # 4. Status
    if raw_fill_pct > 100.0:
        input_quality_status = f"warning: water level ({reading.water_level_cm:.1f}cm) exceeds capacity ({reading.capacity_cm:.1f}cm), capped for risk scoring"
    else:
        input_quality_status = "valid"

    timestamp = reading.timestamp or datetime.now(timezone.utc).isoformat()

    components = RiskComponentsModel(
        water_fill_pct=round(fill_pct, 2),
        water_fill_component=round(water_fill_component, 2),
        blockage_pct=round(blockage_pct, 2),
        blockage_component=round(blockage_component, 2),
        rainfall_normalized=round(rainfall_normalized, 2),
        rainfall_component=round(rainfall_component, 2),
        flow_drop_pct=round(flow_drop, 2),
        flow_drop_component=round(flow_drop_component, 2),
        raw_score=round(raw_score, 2),
    )

    factors = generate_factors(
        fill_pct=fill_pct,
        blockage_pct=blockage_pct,
        rainfall_mm_h=reading.rainfall_mm_h,
        rainfall_normalized=rainfall_normalized,
        flow_drop_pct=flow_drop,
        water_fill_comp=water_fill_component,
        blockage_comp=blockage_component,
        rainfall_comp=rainfall_component,
        flow_drop_comp=flow_drop_component,
    )

    recs = generate_recommendations(
        category=risk_level,
        fill_pct=fill_pct,
        blockage_pct=blockage_pct,
        rainfall_mm_h=reading.rainfall_mm_h,
        flow_drop_pct=flow_drop,
    )

    return RiskAssessmentResponse(
        risk_score=risk_score,
        risk_level=risk_level,
        category=risk_level,
        risk_components=components,
        factors=factors,
        recommended_action=recs,
        data_mode=reading.data_mode.value if reading.data_mode else "simulated",
        assessment_timestamp=timestamp,
        location_id=reading.location_id or "LOC-01",
        location_name=reading.location_name or "Monitored Culvert",
        input_quality_status=input_quality_status,
        disclaimer=PROTOTYPE_DISCLAIMER,
    )
