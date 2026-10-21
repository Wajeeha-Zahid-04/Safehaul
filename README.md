# SafeHaul — Truck Route Safety Planner

Helps a truck driver pick the safest of 3 routes using forecast weather at each checkpoint (at the truck's ETA) plus load weight.

> **Disclaimer:** SafeHaul is a decision aid, not an official safety clearance.

- **Live app:** _TBD (ticket #15)_
- **Loom walkthrough:** _TBD (ticket #17)_

## Stack

| Layer | Tech |
|---|---|
| Backend | Django 5 + Django REST Framework, gunicorn, whitenoise |
| Frontend | React 18, Vite, TypeScript (strict), MapLibre GL (react-map-gl), TanStack Query, Tailwind |
| Data | OpenRouteService (geocode + `driving-hgv`), Open-Meteo (hourly forecast) |

## Repository layout

```
backend/    Django project (config/) + api app
frontend/   Vite React TS app
```

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then set DJANGO_SECRET_KEY and ORS_API_KEY
python manage.py runserver  # http://localhost:8000
```

Tests and lint:

```bash
pytest
ruff check . && ruff format --check .
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev                 # http://localhost:5173
```

Type check / lint / build:

```bash
npx tsc -b --noEmit
npm run lint
npm run build
```

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | backend | Django secret key (required) |
| `DJANGO_DEBUG` | backend | `True` for local dev only |
| `DJANGO_ALLOWED_HOSTS` | backend | Comma-separated hostnames |
| `CORS_ALLOWED_ORIGINS` | backend | Comma-separated allowed frontend origins |
| `ORS_API_KEY` | backend | OpenRouteService key — server-side only |
| `VITE_API_BASE_URL` | frontend | Base URL of the Django API |

## Risk model

Implemented in `backend/risk/rules.py` as `classify(wind_mph, rain_in_hr, snow_in_hr, load_lb) -> (level, reasons)`. Lower bounds are inclusive.

| Level (score) | Wind mph | Rain in/hr | Snow in/hr |
|---|---|---|---|
| Low (0) | <25 | <0.10 | <0.5 |
| Moderate (1) | 25–<35 | 0.10–<0.25 | 0.5–<1.0 |
| High (2) | 35–<45 | 0.25–<0.50 | 1.0–<2.0 |
| Severe (3) | 45–<55 | 0.50–≤1.00 | 2.0–≤3.0 |
| No Travel (4) | ≥55 | >1.00 | >3.0 |

Load overrides (load thresholds are strict, so exactly 30,000 lb does not trigger the first rule):

- Wind ≥55 → No Travel for any load.
- Wind 45–<55 and load >30,000 lb → No Travel.
- Wind 35–<45 and load >40,000 lb → Severe.

The checkpoint level is the maximum across all conditions after overrides. `reasons` lists every rule that reached that level.

## Assumptions

_TBD (ticket #16): gusts shown but not scored, No-Travel ranking, mile attribution._

## API

_TBD (ticket #16): `GET /api/geocode`, `POST /api/plan`, `POST /api/heatmap`._
