"""Backend What-If Scenario Simulation Service.

Implements immutable scenario comparison: evaluates baseline readings and hypothetical
overrides (rainfall, blockage, etc.) without mutating the original input.
Reports score difference, direction, and component transitions.
"""

from __future__ import annotations

from backend.models import (
    DrainageReadingInput,
    ScenarioOverridesInput,
    SimulationResponse,
)
from backend.services.risk_service import evaluate_drainage_risk


def run_scenario_simulation(
    baseline: DrainageReadingInput,
    overrides: ScenarioOverridesInput,
) -> SimulationResponse:
    # 1. Evaluate baseline first (ensures baseline is validated)
    baseline_assessment = evaluate_drainage_risk(baseline)

    # 2. Construct new reading object with overrides (guarantees immutability)
    scenario_water_level = (
        overrides.water_level_cm
        if overrides.water_level_cm is not None
        else baseline.water_level_cm
    )
    scenario_rainfall = (
        overrides.rainfall_mm_h
        if overrides.rainfall_mm_h is not None
        else baseline.rainfall_mm_h
    )
    scenario_blockage = (
        overrides.blockage_pct
        if overrides.blockage_pct is not None
        else baseline.blockage_pct
    )
    scenario_flow_drop = (
        overrides.flow_drop_pct
        if overrides.flow_drop_pct is not None
        else baseline.flow_drop_pct
    )

    scenario_reading = DrainageReadingInput(
        water_level_cm=scenario_water_level,
        capacity_cm=baseline.capacity_cm,
        rainfall_mm_h=scenario_rainfall,
        blockage_pct=scenario_blockage,
        flow_drop_pct=scenario_flow_drop,
        location_id=baseline.location_id,
        location_name=baseline.location_name,
        data_mode=baseline.data_mode,
        timestamp=None,
    )

    scenario_assessment = evaluate_drainage_risk(scenario_reading)

    # 3. Calculate deltas
    score_delta = scenario_assessment.risk_score - baseline_assessment.risk_score

    if score_delta > 0:
        direction = "increased"
    elif score_delta < 0:
        direction = "decreased"
    else:
        direction = "unchanged"

    cat_baseline = baseline_assessment.risk_level.value
    cat_scenario = scenario_assessment.risk_level.value
    category_changed = cat_baseline != cat_scenario

    base_comp = baseline_assessment.risk_components
    scen_comp = scenario_assessment.risk_components
    component_deltas = {
        "water_fill_component_delta": round(scen_comp.water_fill_component - base_comp.water_fill_component, 2),
        "blockage_component_delta": round(scen_comp.blockage_component - base_comp.blockage_component, 2),
        "rainfall_component_delta": round(scen_comp.rainfall_component - base_comp.rainfall_component, 2),
        "flow_drop_component_delta": round(scen_comp.flow_drop_component - base_comp.flow_drop_component, 2),
        "raw_score_delta": round(scen_comp.raw_score - base_comp.raw_score, 2),
    }

    if score_delta > 0:
        summary_text = (
            f"Risk score increased by +{score_delta} points "
            f"({baseline_assessment.risk_score} -> {scenario_assessment.risk_score})."
        )
    elif score_delta < 0:
        summary_text = (
            f"Risk score decreased by {score_delta} points "
            f"({baseline_assessment.risk_score} -> {scenario_assessment.risk_score})."
        )
    else:
        summary_text = f"Risk score remained unchanged at {baseline_assessment.risk_score} points."

    if category_changed:
        summary_text += f" Risk category transitioned from {cat_baseline} to {cat_scenario}."
    else:
        summary_text += f" Risk category remained {cat_scenario}."

    return SimulationResponse(
        scenario_name=overrides.scenario_name or "What-If Scenario",
        baseline=baseline_assessment,
        scenario=scenario_assessment,
        score_delta=score_delta,
        direction=direction,
        category_changed=category_changed,
        summary=summary_text,
        component_deltas=component_deltas,
    )
