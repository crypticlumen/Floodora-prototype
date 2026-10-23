"""Automated tests for Backend Drainage Risk Evaluation Service.

Verifies:
- All 4 risk categories (LOW, MEDIUM, HIGH, CRITICAL)
- Mathematical component weight accuracy (35%, 25%, 20%, 20%)
- Capping behavior for water level (> capacity) and rainfall (> 50 mm/h)
- Input validation (F-04) rejecting negative/out-of-bounds parameters
- Explainability factors and actionable recommendations
"""

import pytest
from backend.models import DrainageReadingInput, RiskLevelEnum
from backend.services.risk_service import evaluate_drainage_risk


class TestRiskServiceValidation:
    def test_valid_inputs_pass(self):
        reading = DrainageReadingInput(
            water_level_cm=30.0,
            capacity_cm=100.0,
            rainfall_mm_h=15.0,
            blockage_pct=20.0,
            flow_drop_pct=10.0,
        )
        res = evaluate_drainage_risk(reading)
        assert res.risk_score >= 0

    def test_reject_zero_or_negative_capacity(self):
        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=0, rainfall_mm_h=0, blockage_pct=0)

        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=-50, rainfall_mm_h=0, blockage_pct=0)

    def test_reject_negative_water_level(self):
        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=-5.0, capacity_cm=100, rainfall_mm_h=0, blockage_pct=0)

    def test_reject_negative_rainfall(self):
        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=100, rainfall_mm_h=-1.0, blockage_pct=0)

    def test_reject_blockage_out_of_bounds(self):
        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=100, rainfall_mm_h=0, blockage_pct=-1.0)

        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=100, rainfall_mm_h=0, blockage_pct=101.0)

    def test_reject_flow_drop_out_of_bounds(self):
        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=100, rainfall_mm_h=0, blockage_pct=0, flow_drop_pct=-5.0)

        with pytest.raises(ValueError):
            DrainageReadingInput(water_level_cm=10, capacity_cm=100, rainfall_mm_h=0, blockage_pct=0, flow_drop_pct=105.0)


class TestRiskServiceScoring:
    def test_minimum_baseline_low_risk(self):
        reading = DrainageReadingInput(
            water_level_cm=0.0,
            capacity_cm=100.0,
            rainfall_mm_h=0.0,
            blockage_pct=0.0,
            flow_drop_pct=0.0,
        )
        res = evaluate_drainage_risk(reading)
        assert res.risk_score == 0
        assert res.risk_level == RiskLevelEnum.LOW
        assert res.category == RiskLevelEnum.LOW
        assert res.risk_components.raw_score == 0.0

    def test_maximum_parameters_critical_risk(self):
        reading = DrainageReadingInput(
            water_level_cm=100.0,
            capacity_cm=100.0,
            rainfall_mm_h=50.0,
            blockage_pct=100.0,
            flow_drop_pct=100.0,
        )
        res = evaluate_drainage_risk(reading)
        assert res.risk_score == 100
        assert res.risk_level == RiskLevelEnum.CRITICAL
        assert res.category == RiskLevelEnum.CRITICAL
        assert res.risk_components.raw_score == 100.0

    def test_exact_weights_breakdown(self):
        # 1. Test 35% water level fill: 50cm / 100cm = 50% fill -> 50 * 0.35 = 17.5 pts
        r1 = DrainageReadingInput(water_level_cm=50.0, capacity_cm=100.0, rainfall_mm_h=0, blockage_pct=0, flow_drop_pct=0)
        res1 = evaluate_drainage_risk(r1)
        assert res1.risk_components.water_fill_component == 17.5
        assert res1.risk_score == 18

        # 2. Test 25% blockage: 40% blockage -> 40 * 0.25 = 10.0 pts
        r2 = DrainageReadingInput(water_level_cm=0, capacity_cm=100.0, rainfall_mm_h=0, blockage_pct=40.0, flow_drop_pct=0)
        res2 = evaluate_drainage_risk(r2)
        assert res2.risk_components.blockage_component == 10.0
        assert res2.risk_score == 10

        # 3. Test 20% rainfall: 25 mm/h / 50 mm/h = 50% norm -> 50 * 0.20 = 10.0 pts
        r3 = DrainageReadingInput(water_level_cm=0, capacity_cm=100.0, rainfall_mm_h=25.0, blockage_pct=0, flow_drop_pct=0)
        res3 = evaluate_drainage_risk(r3)
        assert res3.risk_components.rainfall_component == 10.0
        assert res3.risk_score == 10

        # 4. Test 20% flow drop: 30% flow drop -> 30 * 0.20 = 6.0 pts
        r4 = DrainageReadingInput(water_level_cm=0, capacity_cm=100.0, rainfall_mm_h=0, blockage_pct=0, flow_drop_pct=30.0)
        res4 = evaluate_drainage_risk(r4)
        assert res4.risk_components.flow_drop_component == 6.0
        assert res4.risk_score == 6

    def test_water_level_capping_above_capacity(self):
        reading = DrainageReadingInput(
            water_level_cm=140.0,
            capacity_cm=100.0,
            rainfall_mm_h=0.0,
            blockage_pct=0.0,
            flow_drop_pct=0.0,
        )
        res = evaluate_drainage_risk(reading)
        assert res.risk_components.water_fill_pct == 100.0
        assert res.risk_components.water_fill_component == 35.0
        assert "exceeds capacity" in res.input_quality_status

    def test_rainfall_normalization_capping(self):
        reading = DrainageReadingInput(
            water_level_cm=0.0,
            capacity_cm=100.0,
            rainfall_mm_h=85.0,
            blockage_pct=0.0,
            flow_drop_pct=0.0,
        )
        res = evaluate_drainage_risk(reading)
        assert res.risk_components.rainfall_normalized == 100.0
        assert res.risk_components.rainfall_component == 20.0

    def test_category_threshold_ranges(self):
        # Low boundary: fill 60% -> 21.0 pts -> LOW
        r_low = DrainageReadingInput(water_level_cm=60, capacity_cm=100, rainfall_mm_h=0, blockage_pct=0)
        assert evaluate_drainage_risk(r_low).risk_level == RiskLevelEnum.LOW

        # Medium boundary: 70% fill (24.5) + 10% blockage (2.5) = 27.0 pts -> MEDIUM
        r_med = DrainageReadingInput(water_level_cm=70, capacity_cm=100, rainfall_mm_h=0, blockage_pct=10)
        assert evaluate_drainage_risk(r_med).risk_level == RiskLevelEnum.MEDIUM

        # High boundary: 80% fill (28) + 50% blockage (12.5) + 25mm/h rain (10) = 50.5 -> 51 pts -> HIGH
        r_high = DrainageReadingInput(water_level_cm=80, capacity_cm=100, rainfall_mm_h=25, blockage_pct=50)
        assert evaluate_drainage_risk(r_high).risk_level == RiskLevelEnum.HIGH

        # Critical boundary: 90% fill (31.5) + 80% blockage (20) + 40mm/h rain (16) + 40% flow drop (8) = 75.5 -> 76 pts -> CRITICAL
        r_crit = DrainageReadingInput(water_level_cm=90, capacity_cm=100, rainfall_mm_h=40, blockage_pct=80, flow_drop_pct=40)
        assert evaluate_drainage_risk(r_crit).risk_level == RiskLevelEnum.CRITICAL

    def test_explainability_factors_and_recommendations(self):
        reading = DrainageReadingInput(
            water_level_cm=95.0,
            capacity_cm=100.0,
            rainfall_mm_h=45.0,
            blockage_pct=75.0,
            flow_drop_pct=40.0,
        )
        res = evaluate_drainage_risk(reading)
        assert len(res.factors) > 0
        assert any("drain" in f.lower() or "water" in f.lower() for f in res.factors)
        assert len(res.recommended_action) > 0
        assert res.disclaimer is not None
