# Floodora

Floodora is a working hackathon prototype for smart drainage monitoring and early flood-risk awareness. It combines a FastAPI backend with a responsive operator dashboard served by the same application.

The integrated dashboard supports PIN search, live weather-model data, explainable risk assessment, scenario comparison, and assessment history. A configurable REST sensor adapter can fetch current drain telemetry by PIN when a vendor API URL and PIN-to-device mapping are configured. Without that configuration, no drain sensor values are available and the dashboard does not invent them.

## Run locally

Use Python 3.10 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Open the operator dashboard at <http://localhost:8000/> or <http://localhost:8000/dashboard>. API status is available at <http://localhost:8000/api> and interactive API documentation at <http://localhost:8000/docs>.

## Run with Docker

```sh
docker compose up --build
```

Then open <http://localhost:8000/dashboard>. Stop the service with `docker compose down`.

## Integrated workflow

1. Search an Indian city, district, or PIN. The dashboard loads weather for the resolved coordinates and queries the sensor endpoint using the PIN.
2. If the sensor feed is configured and the PIN is mapped, returned readings fill in the drain form. A complete reading triggers a location-specific risk assessment. Partial feeds leave missing fields visible for field entry; Floodora will not fill them with demo values.
3. The simulator uses the selected PIN's readings as its baseline. Preset scenarios only supply hypothetical slider overrides.
4. The dashboard reads recent assessments from `GET /api/history`. History is held in memory and resets when the service restarts.
5. Weather refreshes every 10 minutes and the sensor API is polled every minute. Sensor request errors and last-reading timestamps are shown separately from weather status.

The browser and API share an origin, so no separate frontend server or CORS setup is needed. To permit an additional hosted client, set `FLOODORA_CORS_ORIGINS` to a comma-separated list of exact origins, such as `https://ops.example.org`.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Operator dashboard |
| `GET` | `/api` | API service status |
| `GET` | `/dashboard` | Integrated operator interface |
| `GET` | `/api/health` | Backend and engine health |
| `GET` | `/api/locations` | Simulated monitored locations |
| `GET` | `/api/locations/{location_id}` | One location and its current demo reading |
| `GET` | `/api/scenarios` | Demo baseline readings and suggested overrides |
| `POST` | `/api/assess` | Validate and assess a drainage reading |
| `POST` | `/api/simulate` | Compare a baseline reading with hypothetical overrides |
| `GET` | `/api/history` | Recent in-memory assessments; supports `limit` and `location_id` |
| `GET` | `/api/weather/search?q=Chennai` | Search city, district, or PIN code in India |
| `GET` | `/api/weather/current?latitude=13.08&longitude=80.27` | Current model-based weather and recent precipitation for India |
| `GET` | `/api/sensors/status` | Check whether the sensor REST adapter is configured |
| `GET` | `/api/sensors/current?pincode=600020` | Fetch and normalize telemetry for the PIN's configured device |

Example assessment:

```sh
curl -X POST http://localhost:8000/api/assess \
  -H "Content-Type: application/json" \
  -d '{"water_level_cm":75,"capacity_cm":120,"rainfall_mm_h":38,"blockage_pct":40,"flow_drop_pct":25,"data_mode":"simulated"}'
```

## Deploy the complete app to Vercel

This project deploys as one FastAPI app that serves the dashboard, API, and static assets. The root `main.py` entrypoint loads `backend.main:app` for Vercel; `pyproject.toml` points Vercel to `main:app`. `.python-version` selects Python 3.12 to match the Docker image. Vercel supports FastAPI and static files mounted with Starlette's `StaticFiles`.

1. Push the repository, including `pyproject.toml` and `.python-version`, to GitHub.
2. In Vercel, choose **Add New → Project** and import `crypticlumen/Floodora-prototype`.
3. Keep the project root at the repository root. Leave the build command and output directory unset so Vercel detects the Python app and installs `requirements.txt`.
4. Add any configured sensor variables from `.env.example` under **Project Settings → Environment Variables**. Do not upload `.env` or put a sensor token in frontend code. Leave sensor settings unset if no real sensor provider and device mapping are available.
5. Deploy. Open the deployment URL for the dashboard; append `/api/health` to check the backend and `/docs` for the API schema.

## Risk method and data boundaries

The drainage score is a transparent, uncalibrated heuristic. It weights water-level fill at 35%, blockage at 25%, rainfall at 20% (normalized against 50 mm/h), and flow drop at 20%. It maps scores to LOW (0–24), MEDIUM (25–49), HIGH (50–74), and CRITICAL (75–100). These are prototype indicators, not incident probabilities or certified flood forecasts.

The satellite and terrain feature classifier described in the PRD is a separate research workstream. This project does not include its dataset, a trained model, measured model results, automatic alert/dispatch integrations, or a bundled sensor service. Sensor data is real only when the operator configures an authorized provider endpoint and maps PINs to actual devices.

### Connect a drain sensor REST API

1. Copy `.env.example` to `.env` in the project root.
2. Set `FLOODORA_SENSOR_URL` to the vendor's latest-telemetry endpoint. The URL can contain `{pincode}` or `{device_id}` placeholders; otherwise Floodora adds `pincode` and `device_id` query parameters.
3. Set `FLOODORA_SENSOR_API_TOKEN` if required. The token stays on the backend and is never sent to the browser. For query-string authentication, set `FLOODORA_SENSOR_API_TOKEN_PARAM` to the vendor's token parameter name instead of using the Authorization header.
4. Replace the example `FLOODORA_SENSOR_DEVICE_MAP` with your PIN-to-device mapping. A mapping value can be a device ID string or an object such as `{"device_id":"drain-600020","capacity_cm":120}`. Capacity is site configuration if the sensor does not report it.
5. If the vendor uses different JSON field names, set `FLOODORA_SENSOR_FIELD_MAP` to map Floodora fields to dotted paths. For example: `{"water_level_cm":"data.level.value","blockage_pct":"data.blockage_pct","flow_drop_pct":"data.flow_drop_pct"}`.
6. Reinstall requirements and restart the backend. For Docker, rebuild with `docker compose up --build`.

The adapter recognizes common names such as `water_level_cm`, `waterLevel`, `level_cm`, `blockage_pct`, and `flow_drop_pct`. A complete assessment requires water level, configured/measured capacity, blockage, and flow drop. If the feed only supplies water level, missing measurements remain explicit and the operator must provide them before scoring.

Example vendor response (field names can instead be mapped in `.env`):

```json
{"data":{"water_level_cm":42.5,"capacity_cm":120,"blockage_pct":18,"flow_drop_pct":7,"timestamp":"2026-10-24T12:30:00+05:30"}}
```

Do not commit `.env`; it may contain credentials. The repository cannot connect to a real sensor until the actual vendor URL, authorization method, payload fields, and device mapping are supplied.

### Live weather provider

Open-Meteo supplies the current weather conditions and geocoding used by the India search. Its current conditions are model-derived and include a timestamp and aggregation interval. Floodora converts the precipitation amount from that preceding interval to an hourly-rate equivalent for the existing heuristic input; this is not a rain-gauge observation. The backend caches responses for 10 minutes and marks stale cached data if the provider becomes unreachable. Weather data attribution is shown in the interface and is licensed CC BY 4.0. The provider's free endpoint is limited to non-commercial use; use a commercial subscription for a commercial deployment. See the [Open-Meteo API documentation](https://open-meteo.com/en/docs), [usage terms](https://open-meteo.com/en/terms), and [pricing](https://open-meteo.com/en/pricing).

For official IMD observations, district nowcasts, warnings, and rainfall data, see the [IMD API portal](https://api.imd.gov.in/public/api_reference.html). The portal requires an account for API access; this project does not claim to consume IMD data or alerts. Direct sensor ingestion also requires a real sensor gateway or vendor API and a site-specific mapping for water level, blockage, flow, and capacity.

The PRD identifies the associated urban inundation dataset as CC BY 4.0 and cites Pawar and Phade (2026), DOI [10.5194/nhess-26-5119-2026](https://doi.org/10.5194/nhess-26-5119-2026), and dataset DOI [10.5281/zenodo.18486214](https://doi.org/10.5281/zenodo.18486214). Review and retain attribution from the dataset's own README and LICENSE before redistributing it; the data is not bundled here.

## Project layout

```text
backend/       FastAPI app, API routes, models, risk and simulation services
frontend/      Responsive dashboard (HTML, CSS, JavaScript)
tests/         Existing backend and API test suite
Dockerfile     Container image
compose.yaml   Local container setup
```

