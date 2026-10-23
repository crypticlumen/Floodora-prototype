"""Data store and mock inventory for monitored drainage locations and demo scenarios.

Supports the Proposed User Journey (PRD Section 6) allowing operators to select
monitored locations, view demo scenarios, and inspect assessment history.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime, timezone

from backend.models import (
    DataModeEnum,
    DemoScenarioPreset,
    DrainageReadingInput,
    MonitoredLocation,
    ScenarioOverridesInput,
)

# Monitored locations across Mumbai flood vulnerability points
MONITORED_LOCATIONS: List[MonitoredLocation] = [
    MonitoredLocation(
        location_id="LOC-01",
        name="Dadar TT Culvert #4",
        ward="F/North",
        city="Mumbai",
        latitude=19.0178,
        longitude=72.8478,
        capacity_cm=120.0,
        drain_type="Box Culvert / Storm Interceptor",
        critical_threshold_cm=95.0,
        current_readings=DrainageReadingInput(
            water_level_cm=35.0,
            capacity_cm=120.0,
            rainfall_mm_h=12.0,
            blockage_pct=25.0,
            flow_drop_pct=10.0,
            location_id="LOC-01",
            location_name="Dadar TT Culvert #4",
            data_mode=DataModeEnum.SIMULATED,
        ),
    ),
    MonitoredLocation(
        location_id="LOC-02",
        name="Hindmata Sump Station Culvert",
        ward="F/South",
        city="Mumbai",
        latitude=19.0084,
        longitude=72.8423,
        capacity_cm=150.0,
        drain_type="Underground Retention Sump Inflow",
        critical_threshold_cm=125.0,
        current_readings=DrainageReadingInput(
            water_level_cm=75.0,
            capacity_cm=150.0,
            rainfall_mm_h=38.0,
            blockage_pct=40.0,
            flow_drop_pct=25.0,
            location_id="LOC-02",
            location_name="Hindmata Sump Station Culvert",
            data_mode=DataModeEnum.SIMULATED,
        ),
    ),
    MonitoredLocation(
        location_id="LOC-03",
        name="Andheri Subway Storm Drain",
        ward="K/East",
        city="Mumbai",
        latitude=19.1197,
        longitude=72.8464,
        capacity_cm=100.0,
        drain_type="Depressed Vehicular Subway Drain",
        critical_threshold_cm=75.0,
        current_readings=DrainageReadingInput(
            water_level_cm=88.0,
            capacity_cm=100.0,
            rainfall_mm_h=45.0,
            blockage_pct=65.0,
            flow_drop_pct=50.0,
            location_id="LOC-03",
            location_name="Andheri Subway Storm Drain",
            data_mode=DataModeEnum.SIMULATED,
        ),
    ),
    MonitoredLocation(
        location_id="LOC-04",
        name="Kurla LBS Marg Primary Collector",
        ward="L Ward",
        city="Mumbai",
        latitude=19.0726,
        longitude=72.8845,
        capacity_cm=140.0,
        drain_type="Open Masonry Channel / Mithi Tributary",
        critical_threshold_cm=110.0,
        current_readings=DrainageReadingInput(
            water_level_cm=20.0,
            capacity_cm=140.0,
            rainfall_mm_h=5.0,
            blockage_pct=15.0,
            flow_drop_pct=0.0,
            location_id="LOC-04",
            location_name="Kurla LBS Marg Primary Collector",
            data_mode=DataModeEnum.SIMULATED,
        ),
    ),
    MonitoredLocation(
        location_id="LOC-05",
        name="Milan Subway Gravity Drain",
        ward="H/East",
        city="Mumbai",
        latitude=19.0912,
        longitude=72.8450,
        capacity_cm=110.0,
        drain_type="Gravity Outfall with Flap Valve",
        critical_threshold_cm=85.0,
        current_readings=DrainageReadingInput(
            water_level_cm=105.0,
            capacity_cm=110.0,
            rainfall_mm_h=58.0,
            blockage_pct=80.0,
            flow_drop_pct=70.0,
            location_id="LOC-05",
            location_name="Milan Subway Gravity Drain",
            data_mode=DataModeEnum.SIMULATED,
        ),
    ),
]

# Preset scenarios designed for hackathon demonstration (PRD Section 15)
DEMO_SCENARIOS: List[DemoScenarioPreset] = [
    DemoScenarioPreset(
        id="SCEN-01",
        title="Dry Weather / Normal Base Flow",
        description="Low water level with clean grates and no rainfall. Nominal baseline status.",
        suggested_role="Campus / Facility Operations",
        readings=DrainageReadingInput(
            water_level_cm=12.0,
            capacity_cm=100.0,
            rainfall_mm_h=0.0,
            blockage_pct=5.0,
            flow_drop_pct=0.0,
            location_id="LOC-01",
            location_name="Dadar TT Culvert #4",
            data_mode=DataModeEnum.SIMULATED,
        ),
        default_overrides=ScenarioOverridesInput(
            rainfall_mm_h=25.0,
            blockage_pct=15.0,
            scenario_name="Simulate Monsoon Shower Impact",
        ),
    ),
    DemoScenarioPreset(
        id="SCEN-02",
        title="Debris Accumulation Before Rain",
        description="Silt and trash screen blockage at 50% under dry skies. Highlights proactive cleaning value.",
        suggested_role="Municipal Drainage Maintenance",
        readings=DrainageReadingInput(
            water_level_cm=25.0,
            capacity_cm=100.0,
            rainfall_mm_h=2.0,
            blockage_pct=50.0,
            flow_drop_pct=15.0,
            location_id="LOC-02",
            location_name="Hindmata Sump Station Culvert",
            data_mode=DataModeEnum.SIMULATED,
        ),
        default_overrides=ScenarioOverridesInput(
            blockage_pct=10.0,
            scenario_name="Simulate Grate Jetting & Cleaning",
        ),
    ),
    DemoScenarioPreset(
        id="SCEN-03",
        title="Intense Monsoon Downpour with Partial Constriction",
        description="Rainfall intensity reaches 38 mm/h with 45% blockage. Elevated risk approaching alert threshold.",
        suggested_role="Emergency Coordinator",
        readings=DrainageReadingInput(
            water_level_cm=70.0,
            capacity_cm=120.0,
            rainfall_mm_h=38.0,
            blockage_pct=45.0,
            flow_drop_pct=25.0,
            location_id="LOC-03",
            location_name="Andheri Subway Storm Drain",
            data_mode=DataModeEnum.SIMULATED,
        ),
        default_overrides=ScenarioOverridesInput(
            rainfall_mm_h=55.0,
            blockage_pct=70.0,
            scenario_name="Simulate Extreme Cloudburst Surge",
        ),
    ),
    DemoScenarioPreset(
        id="SCEN-04",
        title="Critical Cloudburst & Severe Bottleneck",
        description="Water level near capacity, heavy torrential rain, and 85% drain blockage triggering critical alerts.",
        suggested_role="Emergency / Incident Coordinator",
        readings=DrainageReadingInput(
            water_level_cm=115.0,
            capacity_cm=120.0,
            rainfall_mm_h=60.0,
            blockage_pct=85.0,
            flow_drop_pct=65.0,
            location_id="LOC-05",
            location_name="Milan Subway Gravity Drain",
            data_mode=DataModeEnum.SIMULATED,
        ),
        default_overrides=ScenarioOverridesInput(
            blockage_pct=20.0,
            flow_drop_pct=10.0,
            scenario_name="Simulate Emergency Dewatering & Bypass",
        ),
    ),
]


class AssessmentHistoryStore:
    """In-memory store for recent assessments and audit trail."""
    def __init__(self, max_records: int = 100):
        self.max_records = max_records
        self.history: List[Dict] = []

    def add(self, assessment_dict: Dict) -> None:
        self.history.insert(0, assessment_dict)
        if len(self.history) > self.max_records:
            self.history = self.history[:self.max_records]

    def get_all(self, limit: int = 20) -> List[Dict]:
        return self.history[:limit]

    def get_by_location(self, location_id: str) -> List[Dict]:
        return [item for item in self.history if item.get("location_id") == location_id]


history_store = AssessmentHistoryStore()
