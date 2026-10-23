"""Automated tests for Backend What-If Scenario Simulation Service.

Verifies:
- Preservation of original baseline inputs (immutability)
- Score delta calculation and direction ('increased', 'decreased', 'unchanged')
- Category transition detection
- Component delta tracking
"""

from backend.models import (
    DrainageReadingInput,
    RiskLevelEnum,
    ScenarioOverridesInput,
)
from backend.services.simulation_service import run_scenario_simulation


class TestSimulator:
    def test_preserves_original_baseline_readings(self):
        baseline = DrainageReadingInput(
            water_level_cm=30.0,
            capacity_cm=100.0,
            rainfall_mm_h=10.0,
            blockage_pct=20.0,
            flow_drop_pct=0.0,
        )

        overrides = ScenarioOverridesInput(
            rainfall_mm_h=50.0,
            blockage_pct=90.0,
            water_level_cm=95.0,
            flow_drop_pct=60.0,
            scenario_name="Stress Test",
        )

        sim_res = run_scenario_simulation(baseline, overrides)

        # Baseline object attributes must remain strictly unchanged
        assert baseline.water_level_cm == 30.0
        assert baseline.capacity_cm == 100.0
        assert baseline.rainfall_mm_h == 10.0
        assert baseline.blockage_pct == 20.0
        assert baseline.flow_drop_pct == 0.0

        # Scenario assessment reflects overrides
        assert sim_res.scenario.risk_score > sim_res.baseline.risk_score

    def test_rainfall_increase_triggers_increased_direction(self):
        baseline = DrainageReadingInput(
            water_level_cm=20.0,
            capacity_cm=100.0,
            rainfall_mm_h=0.0,
            blockage_pct=10.0,
            flow_drop_pct=0.0,
        )
        overrides = ScenarioOverridesInput(
            rainfall_mm_h=35.0,
            scenario_name="Monsoon Surge",
        )

        res = run_scenario_simulation(baseline, overrides)
        assert res.score_delta > 0
        assert res.direction == "increased"
        assert res.component_deltas["rainfall_component_delta"] > 0
        assert res.component_deltas["blockage_component_delta"] == 0.0

    def test_blockage_decrease_triggers_decreased_direction(self):
        baseline = DrainageReadingInput(
            water_level_cm=40.0,
            capacity_cm=100.0,
            rainfall_mm_h=20.0,
            blockage_pct=70.0,
            flow_drop_pct=30.0,
        )
        overrides = ScenarioOverridesInput(
            blockage_pct=10.0,
            flow_drop_pct=5.0,
            scenario_name="Culvert Unblocking",
        )

        res = run_scenario_simulation(baseline, overrides)
        assert res.score_delta < 0
        assert res.direction == "decreased"
        assert res.component_deltas["blockage_component_delta"] < 0

    def test_zero_change_triggers_unchanged_direction(self):
        baseline = DrainageReadingInput(
            water_level_cm=30.0,
            capacity_cm=100.0,
            rainfall_mm_h=15.0,
            blockage_pct=25.0,
            flow_drop_pct=10.0,
        )
        overrides = ScenarioOverridesInput(scenario_name="Identity Scenario")

        res = run_scenario_simulation(baseline, overrides)
        assert res.score_delta == 0
        assert res.direction == "unchanged"
        assert not res.category_changed
        assert res.component_deltas["raw_score_delta"] == 0.0

    def test_category_transition_tracking(self):
        baseline = DrainageReadingInput(
            water_level_cm=15.0,
            capacity_cm=100.0,
            rainfall_mm_h=0.0,
            blockage_pct=10.0,
            flow_drop_pct=0.0,
        )
        overrides = ScenarioOverridesInput(
            water_level_cm=80.0,
            rainfall_mm_h=40.0,
            blockage_pct=60.0,
            scenario_name="Escalation to High Risk",
        )

        res = run_scenario_simulation(baseline, overrides)
        assert res.baseline.risk_level == RiskLevelEnum.LOW
        assert res.scenario.risk_level in (RiskLevelEnum.HIGH, RiskLevelEnum.CRITICAL)
        assert res.category_changed is True
        assert "Risk category transitioned" in res.summary
