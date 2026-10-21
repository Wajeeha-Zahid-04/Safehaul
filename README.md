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

_TBD (ticket #2)._

## Assumptions

_TBD (ticket #16): gusts shown but not scored, No-Travel ranking, mile attribution._

## API

_TBD (ticket #16): `GET /api/geocode`, `POST /api/plan`, `POST /api/heatmap`._
