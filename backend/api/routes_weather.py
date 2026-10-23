"""India-wide weather search and current model data from Open-Meteo."""

from __future__ import annotations

import re
import time
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/weather", tags=["India Weather"])
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
PIN_LOOKUP_URL = "https://api.postalpincode.in/pincode/{pincode}"
PIN_COORDINATE_URL = "https://api.zippopotam.us/IN/{pincode}"
OSM_GEOCODING_URL = "https://nominatim.openstreetmap.org/search"
CACHE_SECONDS = 600
_weather_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _condition(code: int | None) -> str:
    if code is None:
        return "Condition unavailable"
    conditions = {
        0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle",
        55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
        67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
        77: "Snow grains", 80: "Light rain showers", 81: "Rain showers",
        82: "Heavy rain showers", 85: "Snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
    }
    return conditions.get(code, "Variable conditions")


@router.get("/search", summary="Find a city or place in India")
async def search_indian_places(
    q: str = Query(min_length=2, max_length=80, description="City, district, or postal code"),
) -> Dict[str, Any]:
    """Search India only, returning geocoded places for weather lookup."""
    # Open-Meteo's place search does not contain every Indian PIN code. Resolve
    # six-digit PINs through the India postal directory, then geocode the post
    # office names to obtain coordinates for the weather request.
    if re.fullmatch(r"\d{6}", q.strip()):
        pincode = q.strip()
        # Prefer a postal provider that returns coordinates directly. Open-Meteo
        # does not index every Indian PIN and can return an empty result for a
        # valid code, so it must not be the only way a PIN is resolved.
        try:
            async with httpx.AsyncClient(timeout=7.0) as client:
                coordinate_response = await client.get(PIN_COORDINATE_URL.format(pincode=pincode))
                if coordinate_response.is_success:
                    coordinate_payload = coordinate_response.json()
                    if coordinate_payload.get("country abbreviation") == "IN":
                        direct_results = []
                        for place in coordinate_payload.get("places", []):
                            try:
                                latitude = float(place["latitude"])
                                longitude = float(place["longitude"])
                            except (KeyError, TypeError, ValueError):
                                continue
                            if not (6.0 <= latitude <= 38.8 and 68.0 <= longitude <= 98.8):
                                continue
                            direct_results.append({
                                "id": f"{pincode}-{len(direct_results)}",
                                "name": place.get("place name") or pincode,
                                "admin1": place.get("state", ""),
                                "admin2": "",
                                "country": "India",
                                "latitude": latitude,
                                "longitude": longitude,
                                "timezone": "Asia/Kolkata",
                                "pincode": pincode,
                            })
                        if direct_results:
                            return {"source": "Zippopotam.us postal coordinates", "results": direct_results}
        except (httpx.HTTPError, ValueError, TypeError):
            pass

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                postal_response = await client.get(PIN_LOOKUP_URL.format(pincode=pincode))
                postal_response.raise_for_status()
                postal_payload = postal_response.json()
                offices = (postal_payload[0].get("PostOffice") or []) if postal_payload else []
                pin_results = []
                seen = set()
                for office in offices[:8]:
                    name = office.get("Name")
                    district = office.get("District") or ""
                    state = office.get("State") or ""
                    if not name or not state:
                        continue
                    query = ", ".join(part for part in (name, district, state, "India") if part)
                    geo_response = await client.get(
                        GEOCODING_URL,
                        params={"name": query, "countryCode": "IN", "count": 2, "language": "en", "format": "json"},
                    )
                    geo_response.raise_for_status()
                    for item in (geo_response.json().get("results") or []):
                        if item.get("country_code") != "IN" or "latitude" not in item or "longitude" not in item:
                            continue
                        key = (round(item["latitude"], 3), round(item["longitude"], 3))
                        if key in seen:
                            continue
                        seen.add(key)
                        pin_results.append({
                            "id": item.get("id"),
                            "name": name,
                            "admin1": state,
                            "admin2": district,
                            "country": "India",
                            "latitude": item["latitude"],
                            "longitude": item["longitude"],
                            "timezone": item.get("timezone", "Asia/Kolkata"),
                            "pincode": pincode,
                        })
                        break
                    if len(pin_results) >= 5:
                        break
                if not pin_results and offices:
                    first = offices[0]
                    district = first.get("District") or ""
                    state = first.get("State") or ""
                    if district and state:
                        geo_response = await client.get(
                            GEOCODING_URL,
                            params={"name": f"{district}, {state}, India", "countryCode": "IN", "count": 2, "language": "en", "format": "json"},
                        )
                        geo_response.raise_for_status()
                        for item in (geo_response.json().get("results") or []):
                            if item.get("country_code") == "IN" and "latitude" in item and "longitude" in item:
                                pin_results.append({
                                    "id": item.get("id"),
                                    "name": district,
                                    "admin1": state,
                                    "admin2": "",
                                    "country": "India",
                                    "latitude": item["latitude"],
                                    "longitude": item["longitude"],
                                    "timezone": item.get("timezone", "Asia/Kolkata"),
                                    "pincode": pincode,
                                })
                                break
                if pin_results:
                    return {"source": "India postal directory + Open-Meteo Geocoding API", "results": pin_results}
        except (httpx.HTTPError, ValueError, IndexError, TypeError):
            # Fall through to the general geocoder, which may still resolve it.
            pass

        # Last geocoding fallback uses postal-code data in OpenStreetMap. Search
        # by PIN first, then by the post-office name returned by the directory.
        try:
            async with httpx.AsyncClient(timeout=7.0, headers={"User-Agent": "Floodora/1.0 location weather lookup"}) as client:
                osm_response = await client.get(
                    OSM_GEOCODING_URL,
                    params={"postalcode": pincode, "country": "India", "countrycodes": "in", "format": "jsonv2", "limit": 5},
                )
                osm_response.raise_for_status()
                osm_places = osm_response.json()
                if not osm_places:
                    # Some PINs are not mapped as postal polygons in OSM.
                    postal_response = await client.get(PIN_LOOKUP_URL.format(pincode=pincode))
                    postal_response.raise_for_status()
                    postal_payload = postal_response.json()
                    offices = (postal_payload[0].get("PostOffice") or []) if postal_payload else []
                    if offices:
                        office = offices[0]
                        locality_query = ", ".join(part for part in (office.get("Name"), office.get("District"), office.get("State"), "India") if part)
                        osm_response = await client.get(
                            OSM_GEOCODING_URL,
                            params={"q": locality_query, "countrycodes": "in", "format": "jsonv2", "limit": 5},
                        )
                        osm_response.raise_for_status()
                        osm_places = osm_response.json()
                osm_results = []
                for place in osm_places or []:
                    latitude = float(place["lat"])
                    longitude = float(place["lon"])
                    if not (6.0 <= latitude <= 38.8 and 68.0 <= longitude <= 98.8):
                        continue
                    osm_results.append({
                        "id": place.get("place_id", pincode),
                        "name": place.get("name") or pincode,
                        "admin1": "India",
                        "admin2": place.get("display_name", ""),
                        "country": "India",
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": "Asia/Kolkata",
                        "pincode": pincode,
                    })
                if osm_results:
                    return {"source": "OpenStreetMap postal geocoding", "results": osm_results}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                GEOCODING_URL,
                params={"name": q, "countryCode": "IN", "count": 8, "language": "en", "format": "json"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"India location search is temporarily unavailable: {exc}") from exc

    results = response.json().get("results", []) or []
    return {
        "source": "Open-Meteo Geocoding API (GeoNames)",
        "results": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "admin1": item.get("admin1", ""),
                "admin2": item.get("admin2", ""),
                "country": item.get("country", "India"),
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "timezone": item.get("timezone", "Asia/Kolkata"),
            }
            for item in results
            if item.get("country_code") == "IN" and "latitude" in item and "longitude" in item
        ],
    }


@router.get("/current", summary="Get current weather model data for an Indian location")
async def current_indian_weather(
    latitude: float = Query(ge=6.0, le=38.8),
    longitude: float = Query(ge=68.0, le=98.8),
) -> Dict[str, Any]:
    """Return recent model-derived conditions; precipitation is converted to an hourly rate."""
    cache_key = f"{latitude:.3f},{longitude:.3f}"
    now = time.monotonic()
    cached = _weather_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        return {**cached[1], "cache_age_seconds": int(now - cached[0]), "cached": True}

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "timezone": "auto",
        "timeformat": "iso8601",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(WEATHER_URL, params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        if cached:
            return {**cached[1], "cache_age_seconds": int(now - cached[0]), "cached": True, "stale": True}
        raise HTTPException(status_code=502, detail=f"Live weather is temporarily unavailable: {exc}") from exc

    payload = response.json()
    current = payload.get("current") or {}
    units = payload.get("current_units") or {}
    interval_seconds = int(current.get("interval", 3600) or 3600)
    precipitation_mm = float(current.get("precipitation") or 0.0)
    rainfall_mm_h = precipitation_mm * 3600 / max(interval_seconds, 1)
    code = current.get("weather_code")
    result = {
        "latitude": payload.get("latitude", latitude),
        "longitude": payload.get("longitude", longitude),
        "timezone": payload.get("timezone", "Asia/Kolkata"),
        "observed_at": current.get("time"),
        "interval_seconds": interval_seconds,
        "temperature_c": current.get("temperature_2m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precipitation_mm": precipitation_mm,
        "rain_mm": current.get("rain"),
        "showers_mm": current.get("showers"),
        "rainfall_mm_h_equivalent": round(rainfall_mm_h, 2),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "wind_gusts_kmh": current.get("wind_gusts_10m"),
        "weather_code": code,
        "condition": _condition(code),
        "units": units,
        "source": "Open-Meteo Forecast API",
        "source_url": "https://open-meteo.com/en/docs",
        "attribution": "Weather data by Open-Meteo; CC BY 4.0. Model-derived conditions, not a local rain-gauge observation.",
        "data_kind": "weather_model_estimate",
        "cached": False,
        "cache_age_seconds": 0,
        "stale": False,
    }
    _weather_cache[cache_key] = (now, result)
    return result
