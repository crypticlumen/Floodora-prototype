"""Configurable REST adapter for operator-owned drain sensor feeds.

No public sensor discovery is possible from a PIN alone. Operators configure a
vendor endpoint and map each postal PIN to the vendor's device identifier.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.parse import quote

import httpx
from fastapi import HTTPException

DEFAULT_FIELD_ALIASES = {
    "water_level_cm": ("water_level_cm", "waterLevelCm", "waterLevel", "level_cm", "level"),
    "capacity_cm": ("capacity_cm", "capacityCm", "drain_capacity_cm", "max_level_cm"),
    "blockage_pct": ("blockage_pct", "blockagePercent", "blockage", "clog_pct"),
    "flow_drop_pct": ("flow_drop_pct", "flowDropPercent", "flow_drop", "flow_reduction_pct"),
    "rainfall_mm_h": ("rainfall_mm_h", "rainfallRate", "rain_rate_mm_h", "rainfall"),
    "timestamp": ("timestamp", "observed_at", "observedAt", "updated_at", "time"),
}
REQUIRED_DRAIN_FIELDS = ("water_level_cm", "capacity_cm", "blockage_pct", "flow_drop_pct")


def _json_env(name: str, fallback: Any) -> Any:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"{name} must contain valid JSON.") from exc


def _device_map() -> Dict[str, Any]:
    value = _json_env("FLOODORA_SENSOR_DEVICE_MAP", {})
    if not isinstance(value, dict):
        raise HTTPException(status_code=500, detail="FLOODORA_SENSOR_DEVICE_MAP must be a JSON object.")
    return value


def _get_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    while isinstance(current, list) and current:
        current = current[-1]
    if isinstance(current, dict) and "value" in current:
        return current["value"]
    return current


def _find_value(payload: Any, canonical: str, field_map: Dict[str, Any]) -> Any:
    configured_path = field_map.get(canonical)
    paths = [configured_path] if isinstance(configured_path, str) else []
    paths.extend(DEFAULT_FIELD_ALIASES.get(canonical, ()))
    roots = [payload]
    if isinstance(payload, dict):
        roots.extend(payload[key] for key in ("data", "current", "readings", "telemetry", "result") if key in payload)
    for root in roots:
        for path in paths:
            result = _get_path(root, path)
            if result is not None:
                return result
    return None


def sensor_status() -> Dict[str, Any]:
    configured = bool(os.getenv("FLOODORA_SENSOR_URL", "").strip())
    mapping = _device_map() if configured else {}
    return {
        "provider": os.getenv("FLOODORA_SENSOR_NAME", "Configured drain sensor REST API"),
        "configured": configured,
        "pin_mappings": len(mapping),
        "required_configuration": ["FLOODORA_SENSOR_URL", "FLOODORA_SENSOR_DEVICE_MAP"],
        "connected": None,
        "message": "Feed configured; connection is checked when a PIN is queried." if configured else "No REST sensor endpoint is configured.",
    }


async def get_sensor_reading(pincode: str) -> Dict[str, Any]:
    """Fetch and normalize one PIN's latest REST telemetry without caching it."""
    url_template = os.getenv("FLOODORA_SENSOR_URL", "").strip()
    if not url_template:
        return {
            "configured": False, "connected": False, "pincode": pincode,
            "message": "No drain sensor feed is configured. Add the provider URL and PIN-to-device mapping to .env.",
        }

    device_entry = _device_map().get(pincode)
    if isinstance(device_entry, dict):
        device_id = device_entry.get("device_id") or device_entry.get("id")
        configured_capacity = device_entry.get("capacity_cm")
    else:
        device_id = device_entry
        configured_capacity = None
    if "{device_id}" in url_template and not device_id:
        raise HTTPException(status_code=404, detail=f"No sensor device is mapped to PIN {pincode}.")

    try:
        url = url_template.format(pincode=quote(pincode, safe=""), device_id=quote(str(device_id or ""), safe=""))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="FLOODORA_SENSOR_URL supports only {pincode} and {device_id} placeholders.") from exc

    params: Dict[str, str] = {}
    if "{pincode}" not in url_template:
        params[os.getenv("FLOODORA_SENSOR_PIN_PARAM", "pincode")] = pincode
    if device_id and "{device_id}" not in url_template:
        params[os.getenv("FLOODORA_SENSOR_DEVICE_PARAM", "device_id")] = str(device_id)
    headers: Dict[str, str] = {"Accept": "application/json"}
    token = os.getenv("FLOODORA_SENSOR_API_TOKEN", "").strip()
    if token:
        header = os.getenv("FLOODORA_SENSOR_AUTH_HEADER", "Authorization")
        scheme = os.getenv("FLOODORA_SENSOR_AUTH_SCHEME", "Bearer").strip()
        token_param = os.getenv("FLOODORA_SENSOR_API_TOKEN_PARAM", "").strip()
        if token_param:
            params[token_param] = token
        else:
            headers[header] = f"{scheme} {token}" if scheme else token
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("FLOODORA_SENSOR_TIMEOUT_SECONDS", "8"))) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="The drain sensor feed timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Drain sensor provider returned HTTP {exc.response.status_code}.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not read JSON from the drain sensor provider.") from exc

    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    field_map = _json_env("FLOODORA_SENSOR_FIELD_MAP", {})
    if not isinstance(field_map, dict):
        raise HTTPException(status_code=500, detail="FLOODORA_SENSOR_FIELD_MAP must be a JSON object.")
    values: Dict[str, Any] = {}
    for name in (*REQUIRED_DRAIN_FIELDS, "rainfall_mm_h", "timestamp"):
        value = _find_value(payload, name, field_map)
        if name == "capacity_cm" and value is None:
            value = configured_capacity or os.getenv("FLOODORA_SENSOR_DEFAULT_CAPACITY_CM")
        if value is not None:
            try:
                values[name] = value if name == "timestamp" else float(value)
            except (TypeError, ValueError):
                continue

    valid = {
        key: value for key, value in values.items()
        if key == "timestamp" or (isinstance(value, (int, float)) and value >= 0)
    }
    if "capacity_cm" in valid and valid["capacity_cm"] <= 0:
        valid.pop("capacity_cm")
    for bounded in ("blockage_pct", "flow_drop_pct"):
        if bounded in valid and valid[bounded] > 100:
            valid.pop(bounded)
    missing = [name for name in REQUIRED_DRAIN_FIELDS if name not in valid]
    return {
        "configured": True,
        "connected": True,
        "provider": os.getenv("FLOODORA_SENSOR_NAME", "Configured drain sensor REST API"),
        "pincode": pincode,
        "device_id": str(device_id) if device_id else None,
        "source": os.getenv("FLOODORA_SENSOR_NAME", "Configured drain sensor REST API"),
        "observed_at": valid.get("timestamp"),
        "reading": {key: value for key, value in valid.items() if key != "timestamp"},
        "available_fields": [key for key in valid if key != "timestamp"],
        "missing_fields": missing,
        "assessment_ready": not missing,
        "message": "Live sensor data received." if not missing else f"Live sensor data received; missing: {', '.join(missing)}.",
    }
