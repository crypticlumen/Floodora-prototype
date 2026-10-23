"""Automated end-to-end API tests for Floodora FastAPI backend."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestSystemEndpoints:
    def test_root_endpoint(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Floodora Backend API"
        assert data["status"] == "online"

    def test_health_check(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["risk_engine"] == "operational"
        assert data["scenario_simulator"] == "operational"


class TestRiskAssessmentAPI:
    def test_assess_valid_reading(self):
        payload = {
            "water_level_cm": 60.0,
            "capacity_cm": 120.0,
            "rainfall_mm_h": 25.0,
            "blockage_pct": 30.0,
            "flow_drop_pct": 10.0,
            "location_id": "LOC-01",
            "location_name": "Dadar Culvert",
            "data_mode": "simulated",
        }
        resp = client.post("/api/assess", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
        assert data["risk_score"] >= 0 and data["risk_score"] <= 100
        assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert "risk_components" in data
        assert len(data["factors"]) > 0
        assert len(data["recommended_action"]) > 0
        assert data["data_mode"] == "simulated"

    def test_assess_rejects_negative_water_level(self):
        payload = {
            "water_level_cm": -10.0,
            "capacity_cm": 100.0,
            "rainfall_mm_h": 0.0,
            "blockage_pct": 20.0,
        }
        resp = client.post("/api/assess", json=payload)
        assert resp.status_code == 422

    def test_assess_rejects_zero_capacity(self):
        payload = {
            "water_level_cm": 10.0,
            "capacity_cm": 0.0,
            "rainfall_mm_h": 0.0,
            "blockage_pct": 20.0,
        }
        resp = client.post("/api/assess", json=payload)
        assert resp.status_code == 422

    def test_assess_rejects_out_of_bounds_blockage(self):
        payload = {
            "water_level_cm": 10.0,
            "capacity_cm": 100.0,
            "rainfall_mm_h": 0.0,
            "blockage_pct": 120.0,
        }
        resp = client.post("/api/assess", json=payload)
        assert resp.status_code == 422


class TestSimulatorAPI:
    def test_simulate_what_if_scenario(self):
        payload = {
            "baseline": {
                "water_level_cm": 30.0,
                "capacity_cm": 100.0,
                "rainfall_mm_h": 5.0,
                "blockage_pct": 20.0,
                "flow_drop_pct": 0.0,
            },
            "overrides": {
                "rainfall_mm_h": 40.0,
                "blockage_pct": 65.0,
                "scenario_name": "Heavy Storm Surge",
            },
        }
        resp = client.post("/api/simulate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_name"] == "Heavy Storm Surge"
        assert data["score_delta"] > 0
        assert data["direction"] == "increased"
        assert "component_deltas" in data
        assert "baseline" in data
        assert "scenario" in data


class TestLocationsAndScenariosAPI:
    def test_get_locations_list(self):
        resp = client.get("/api/locations")
        assert resp.status_code == 200
        locations = resp.json()
        assert isinstance(locations, list)
        assert len(locations) >= 4
        assert any(l["location_id"] == "LOC-01" for l in locations)

    def test_get_location_detail_success(self):
        resp = client.get("/api/locations/LOC-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Dadar TT Culvert #4"
        assert data["capacity_cm"] == 120.0

    def test_get_location_detail_not_found(self):
        resp = client.get("/api/locations/NON-EXISTENT-999")
        assert resp.status_code == 404

    def test_get_scenarios_preset_list(self):
        resp = client.get("/api/scenarios")
        assert resp.status_code == 200
        presets = resp.json()
        assert len(presets) >= 4
        assert presets[0]["id"] == "SCEN-01"

    def test_history_logging(self):
        # Trigger an assessment
        client.post("/api/assess", json={
            "water_level_cm": 25.0,
            "capacity_cm": 100.0,
            "rainfall_mm_h": 10.0,
            "blockage_pct": 15.0,
            "location_id": "LOC-AUDIT",
        })
        resp = client.get("/api/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) > 0
        assert any(h.get("location_id") == "LOC-AUDIT" for h in history)
