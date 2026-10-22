# SafeHaul — Truck Route Safety Planner

SafeHaul helps a truck driver pick the safest of up to three routes. Every route is sampled into checkpoints, each checkpoint is checked against the **forecast at the truck's ETA** (not "now"), the truck's **load weight** is applied to wind risk, and the routes are ranked by how many miles they spend in No-Travel, Severe and High conditions.

> **Disclaimer:** SafeHaul is a decision aid based on forecast data. It is not an official safety clearance.

| | |
|---|---|
| **Live app** | https://safehaul-j4uk.vercel.app |
| **API** | https://safehaul-two.vercel.app (try [`/api/geocode?q=Denver`](https://safehaul-two.vercel.app/api/geocode?q=Denver)) |
| **Loom walkthrough** | https://www.loom.com/share/1b150aa953064a2581c991642a28c257 |

**Contents:** [Features](#features) · [How it works](#how-it-works) · [Risk model](#risk-model) · [Recommendation](#recommendation) · [Assumptions](#assumptions) · [Deviations from spec](#deviations-from-spec) · [API](#api) · [Testing](#testing) · [Security](#security) · [Performance](#performance) · [Local setup](#local-setup) · [Deployment](#deployment) · [Environment variables](#environment-variables) · [Project structure](#project-structure)

---

## Features

- **Trip form:** origin and destination autocomplete (300 ms debounce, keyboard navigation), departure from now to +48 h, load weight (0–120,000 lb), checkpoint interval (10 / 25 / 50 mi).
- **Up to 3 truck routes** on a MapLibre map, each segment coloured by its checkpoint's risk. The selected route is drawn thick; the others are faded to 40%.
- **Checkpoint popups** with ETA, the forecast hour used, wind (gusts shown), rain, snow, precipitation, risk level and the exact rule that set it.
- **Route cards** showing distance, time, Severe/High/No-Travel miles and average risk. The recommended route comes first with a badge and a one-line reason (e.g. *"0 severe mi vs 12, 12 min slower"*). Routes with any No-Travel get a *Do not travel* flag.
- **Corridor heatmap** with a 0–48 h slider. All 49 hours are loaded once and the slider swaps precomputed frames, so there is no refetch. The status line reports how many areas are at Moderate or worse and can jump to the busiest hour.
- **Legend** with the five risk colours and a heatmap toggle.
- **States:** empty, loading skeletons, error with retry, and an "all routes No Travel" banner.
- **Mobile layout:** the side panel becomes a bottom sheet.

## How it works

```
React (Vite, TS) ──HTTPS──> Django REST API ──> Valhalla truck routing / ORS driving-hgv (geocode: Photon / ORS)
  MapLibre GL                     │          └─> Open-Meteo hourly forecast (batched, multi-point)
  heatmap layer                   └─> Cache (Redis, or Django LocMem fallback)
```

`POST /api/plan` runs this pipeline (`backend/api/planner.py`):

1. **Routing** (`routing/`): up to 3 truck routes with the load as a weight restriction. Every provider is normalised to `Route(coordinates, steps[start,end,distance,duration])`.
2. **Checkpoints** (`checkpoints/`): walk the polyline using cumulative haversine distance and place a checkpoint at every `interval` miles. The destination is always the last checkpoint. **ETA** = departure + duration interpolated along the route, where each routing step's duration is spread over its vertices by distance, so highway and city speeds are respected.
3. **Weather** (`weather/`): one batched Open-Meteo request per route (comma-separated lat/lon lists). Routes are fetched concurrently. Each checkpoint reads the forecast hour nearest its ETA.
4. **Risk** (`risk/`): a pure `classify(wind, rain, snow, load) -> (level, reasons)`.
5. **Stats and ranking** (`recommend/`): miles per level, mile-weighted average score, and a sort by the spec's tuple key.

`POST /api/heatmap` builds a grid of about 15 km spacing over the routes' bounding box plus a 25 km buffer, capped at 400 points by widening the spacing. It fetches 0–48 h for every point, scores each point and hour with the same `classify`, and returns compact arrays.

## Risk model

`backend/risk/rules.py`. Lower bounds are inclusive.

| Level (score) | Wind mph | Rain in/hr | Snow in/hr |
|---|---|---|---|
| Low (0) | <25 | <0.10 | <0.5 |
| Moderate (1) | 25–<35 | 0.10–<0.25 | 0.5–<1.0 |
| High (2) | 35–<45 | 0.25–<0.50 | 1.0–<2.0 |
| Severe (3) | 45–<55 | 0.50–≤1.00 | 2.0–≤3.0 |
| No Travel (4) | ≥55 | >1.00 | >3.0 |

**Load overrides:**

- Wind ≥55 mph → No Travel for any load.
- Wind 45–<55 mph and load >30,000 lb → No Travel.
- Wind 35–<45 mph and load >40,000 lb → Severe.

A checkpoint's level is the **maximum** across wind, rain and snow after overrides. `reasons` lists every rule that reached that level, e.g. `"Load 35,000 lb > 30,000 with wind 48 mph (45–<55) → No Travel"`.

## Recommendation

Routes are sorted ascending by `(notravel_mi, severe_mi, high_mi, avg_score, duration)` (`backend/recommend/stats.py`):

1. Fewest No-Travel miles
2. Fewest Severe miles
3. Fewest High miles
4. Lowest average risk score
5. Shortest duration

The reason line names the criterion that separated the top route from the runner-up, plus how much slower it is than the fastest route.

## Assumptions

Decisions where the spec was silent or ambiguous. Each is covered by tests.

- **Gusts are shown, not scored.** Wind risk uses sustained `wind_speed_10m`. `wind_gusts_10m` appears in the checkpoint popup, marked "not scored".
- **No Travel ranks worse than Severe.** It is the first sort key, and any route containing a No-Travel checkpoint is flagged **Do not travel**. If every route has No Travel, the UI shows a warning banner and the reason starts with "Do not travel: …"; the least-exposed route is still ranked first.
- **Mile attribution.** Each checkpoint owns the miles from the previous checkpoint (or the origin) up to itself, so the owned segments add up to the route length. There is no checkpoint at the origin, since it would own 0 miles.
- **Average risk score is mile-weighted**: Σ(score × owned miles) / route miles. A short final segment to the destination doesn't weigh as much as a full interval.
- **Override wind ranges.** "45–54" and "35–44" mph are treated as `45 ≤ wind < 55` and `35 ≤ wind < 45`, matching the wind bands, so values like 54.6 mph are covered. Load thresholds are strict: exactly 30,000 lb does not trigger the first override.
- **Forecast hour** = ETA rounded to the nearest whole hour in UTC, with half past rounding up.
- **Rain scored** is Open-Meteo `rain` (liquid). `precipitation` also includes snow water equivalent, so it is shown but not scored, to avoid counting snow twice.
- **Ranking ties.** Mile and score keys are compared after rounding (0.01 mi, 0.0001), so float noise can't decide a real tie. A full tie falls back to route id.
- **Missing forecast data fails loudly.** It returns a 502 for routes rather than being silently scored as Low. In the heatmap a missing cell is `null` and simply not drawn.
- **Heatmap starts at the trip's departure** and uses the trip's load, so it matches the route colours. Low cells are transparent.

## Deviations from spec

Every deviation came from an external blocker, or from a spec detail that would have produced wrong results.

- **Keyless routing fallback.** OpenRouteService is implemented as specified (`backend/routing/ors.py`: `driving-hgv`, `alternative_routes.target_count = 3`, weight restriction in tonnes) and is used whenever `ORS_API_KEY` is set. ORS sign-up was unavailable during development (an openrouteservice.org outage, and the HeiGIT account captcha kept failing). With no key, the backend uses the public **Valhalla** server (`truck` costing, weight restriction, 2 alternates, so up to 3 routes) and **Photon** for geocoding. Both are normalised to the same `Route` shape, so nothing downstream changes. Either provider may return fewer than 3 routes when no real alternatives exist.
- **Backend hosting.** The spec names Render or Railway. Render required a payment card even for the free tier, Railway had deploys paused for new accounts, and Hugging Face moved Docker Spaces behind a paid plan. The live backend therefore runs on **Vercel's Python runtime** (free, no card). The trade-off: serverless instances are short-lived, so the in-process cache and the per-IP throttle apply per warm instance rather than globally; setting `REDIS_URL` makes both shared again. The container setup (`backend/Dockerfile`, `gunicorn.conf.py`, `render.yaml`) is kept and tested, so moving to Render or Railway is configuration only.
- **Snowfall units.** The spec says snowfall arrives in cm/hr and is divided by 2.54. With `precipitation_unit=inch` (also in the spec), Open-Meteo already returns snowfall in inches, so dividing again would understate snow by 2.54×. The client converts using the units Open-Meteo reports in `hourly_units`: `cm` → ÷2.54, `inch` → as-is.
- **API additions.**
  - `/plan` accepts `origin`/`destination` as `{label, lat, lon}`, the place picked from autocomplete, which avoids re-geocoding text. The 200-character cap applies to `label`.
  - `/plan` also returns `recommendation_reason`, `all_no_travel`, per-route `rank`/`bbox`/`do_not_travel`, and per-checkpoint `path` for map colouring.
  - `/heatmap` accepts an optional `load_lb` and returns `start` and `spacing_km`.
- **Error statuses.** Real upstream failures keep the spec's generic **502**. A trip the router can't route returns **422** with the reason, and an upstream rate limit returns **503** with `Retry-After: 60`. None of them include stack traces or upstream details.
- **Free-tier limits.**
  - The public Valhalla server rejects trips whose origin and destination are more than ~1,500 km (~930 mi) apart in a straight line; this returns a 422 with that explanation.
  - Open-Meteo's free tier allows about 600 location-calls per minute and 10,000 per day. A 400-point heatmap costs about 400 of them, so heatmaps are cached for 30 minutes.

## API

Base URL: `https://safehaul-two.vercel.app`. JSON in and out. Errors are always `{"detail": "..."}`, except validation errors, which are DRF's per-field object.

### `GET /api/geocode?q=<text>`

Place autocomplete. `q` is 1–200 characters. Results are cached for 24 h.

```json
{"results": [{"label": "Denver, Colorado, United States", "lat": 39.7392, "lon": -104.9849}]}
```

### `POST /api/plan`

```json
{
  "origin":      {"label": "Chicago, Illinois, United States", "lat": 41.8781, "lon": -87.6298},
  "destination": {"label": "Indianapolis, Indiana, United States", "lat": 39.7684, "lon": -86.1581},
  "departure":   "2026-10-22T15:00:00Z",
  "load_lb":     40000,
  "interval_mi": 25
}
```

| Field | Rule |
|---|---|
| `origin`, `destination` | `label` ≤200 chars, `lat` −90…90, `lon` −180…180, and the two must differ |
| `departure` | ISO 8601, from now (5 min grace) to now + 48 h |
| `load_lb` | 0 – 120,000 |
| `interval_mi` | 10, 25 or 50 |

Response (routes in ranked order, recommended first; illustrative values, arrays shortened):

```json
{
  "recommended_id": 1,
  "recommendation_reason": "0 severe mi vs 12, 12 min slower",
  "all_no_travel": false,
  "routes": [{
    "id": 1, "rank": 0, "distance_mi": 205.3, "duration_s": 13320,
    "notravel_mi": 0, "severe_mi": 0, "high_mi": 25.0, "avg_score": 0.24,
    "do_not_travel": false,
    "bbox": [-87.63, 39.77, -86.15, 41.88],
    "checkpoints": [{
      "index": 0, "lat": 41.55, "lon": -87.41, "distance_mi": 25.0, "segment_mi": 25.0,
      "eta": "2026-10-22T15:28:11+00:00", "forecast_hour": "2026-10-22T15:00:00+00:00",
      "wind_mph": 36.2, "gust_mph": 51.0, "rain_in": 0.0, "precip_in": 0.0, "snow_in": 0.0,
      "level": 2, "level_label": "High", "reasons": ["Wind 36.2 mph ≥ 35 → High"],
      "path": [[-87.6298, 41.8781], [-87.41, 41.55]]
    }]
  }]
}
```

`path` is the polyline each checkpoint owns, in GeoJSON `[lon, lat]` order. `level` runs 0–4, as in the risk table.

### `POST /api/heatmap`

```json
{"bbox": [-87.63, 39.77, -86.15, 41.88], "start": "2026-10-22T15:00:00Z", "load_lb": 40000}
```

- `bbox` is `[min_lon, min_lat, max_lon, max_lat]`.
- `start` follows the same window as `departure`.
- `load_lb` is optional and defaults to 0.

```json
{
  "start": "2026-10-22T15:00:00+00:00", "hours": 49, "spacing_km": 15.0,
  "points": [[39.55, -87.95], [39.55, -87.77]],
  "scores": [[0, 1], [0, 2]]
}
```

`scores[hour][point]` holds 0–4, or `null` when there is no forecast. Hour `h` is `start + h` hours.

### Status codes and limits

| Status | When |
|---|---|
| 400 | Validation error (per-field messages) |
| 422 | No truck route exists, or the trip exceeds the routing service's distance limit |
| 429 | More than 30 requests/min per IP on `/plan` or `/heatmap` |
| 502 | An upstream service failed (generic message) |
| 503 | An upstream service is rate-limited (`Retry-After: 60`) |

## Testing

**240 backend tests** (pytest + pytest-django). Every external API is mocked with `responses`. They pass on Python 3.12 and 3.14.

| Module | Tests | Covers |
|---|---|---|
| `test_risk.py` | 58 | Every threshold just below, at and above, for wind, rain and snow; all load-override edges (30,000 vs 30,001, 40,000 vs 40,001, both wind-range ends); max-of-conditions; reason text; input validation |
| `test_checkpoints.py` | 26 | Haversine; exact spacing for 10/25/50 mi; destination always last and never duplicated; segments add up to the route length; ETA at constant speed and with per-step speeds; zero-length stops; per-checkpoint paths |
| `test_recommend.py` | 24 | Each sort key decides only when earlier keys tie; mile-weighted average; float-noise ties; reason text for every deciding key |
| `test_api.py` | 34 | `/plan` end to end; 12 invalid and 7 boundary inputs; one weather call per route; generic 502; 30/min throttle per IP; `/geocode` |
| `test_heatmap.py` | 23 | 15 km grid with 25 km buffer; 400-point cap on large areas; hour-major scores with load overrides; chunked fetch; caching; endpoint validation and throttle |
| `test_weather.py` | 23 | Nearest-hour rounding; batched params; unit conversion (cm, mm, km/h); caching and batching of only missing points |
| `test_routing.py` | 20 | ORS and Valhalla request bodies (lon/lat order, `target_count: 3`, tonnes); parsing; retry on 5xx and network errors, none on 4xx; key never logged |
| `test_security.py` | 16 | `check --deploy` under production env; HTTPS redirect and HSTS; headers; CORS allow-list; spoof-proof throttling; body cap; JSON 500 without details |
| `test_errors.py` | 14 | 422 for unroutable trips (Valhalla and ORS codes); 503 with `Retry-After` for rate limits |

```bash
cd backend && pytest                 # 240 passed
ruff check . && ruff format --check . # lint + format
cd ../frontend && npx tsc -b --noEmit && npm run lint && npm run build
```

`backend/scripts/smoke_test.py` checks a live deployment end to end (see [Deployment](#deployment)).

## Security

- **Secrets:** environment variables only (`.env` is git-ignored, and `.env.example` documents every variable). The ORS key never leaves the server, and log lines strip query strings so it can't leak into logs.
- **Django:** `DEBUG=False` by default. With `DEBUG` off: HTTPS redirect, HSTS (1 year), secure cookies, and the proxy SSL header. Always on: `nosniff`, `X-Frame-Options: DENY`, Referrer-Policy and a 100 KB request-body cap. Unhandled errors return a generic JSON 500. `manage.py check --deploy` passes, and an automated test enforces it.
- **CORS:** only the configured frontend origin(s), only on `/api/*`, and only GET/POST/OPTIONS.
- **Input validation:** DRF serializers enforce every rule in the API tables above.
- **Rate limiting:** 30 requests/min per IP on `/plan` and `/heatmap`. The client IP is taken from the trusted proxy position (`DJANGO_NUM_PROXIES`), so spoofing `X-Forwarded-For` can't get around it.
- **Upstream calls:** 10 s timeout, 1 retry on network errors and 5xx, and none on 4xx. Clients only ever see generic messages.
- **Frontend:** a strict Content-Security-Policy (only the app, the API hosts and the tile server), plus `nosniff`, `X-Frame-Options`, Referrer-Policy and Permissions-Policy (`frontend/vercel.json`).
- **Dependencies:** pinned in `requirements.txt` and `package-lock.json`. Dependabot is configured for pip and npm (`.github/dependabot.yml`), with React held at 18.

## Performance

Measured against the live deployment with `scripts/smoke_test.py`:

| | Result |
|---|---|
| `POST /api/plan`, cold cache (Chicago → Indianapolis, 3 routes) | **3.9 s** (target < 5 s) |
| `POST /api/plan`, warm | 0.95 s |
| `POST /api/heatmap` (228 points × 49 h) | 1.6 s |

What keeps it fast:

- **Backend:** weather is fetched for all routes in parallel. Results are cached (geocode 24 h, routes 1 h, weather 30 min per 2-decimal lat/lon and hour, heatmap 30 min). Responses are gzipped (a Chicago → Detroit plan went from 195 KB to 55 KB on the wire).
- **Frontend heatmap:** all 49 GeoJSON frames are precomputed once. The slider triggers at most one `setData` per animation frame via `requestAnimationFrame`, with no refetch and no React re-render of the map.
- **Map:** memoised GeoJSON with one source per layer type. Selecting a route only changes paint expressions, so no data is re-uploaded. The map component is memoised, so typing in the form never re-renders it.

## Local setup

**Backend** (Python 3.12+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # set DJANGO_SECRET_KEY; ORS_API_KEY is optional
python manage.py runserver    # http://localhost:8000
```

**Frontend** (developed and tested on Node 24):

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev                   # http://localhost:5173
```

## Deployment

Both apps deploy from this repo as **two Vercel projects**. With `DJANGO_DEBUG=False` the backend enables its HTTPS settings, and the platform's public hostname (`VERCEL_PROJECT_PRODUCTION_URL` / `VERCEL_URL`, `RENDER_EXTERNAL_HOSTNAME` or `RAILWAY_PUBLIC_DOMAIN`) is added to `ALLOWED_HOSTS` automatically.

- **Backend → Vercel (live).**
  - New Project → this repo → **Root Directory `backend`**, preset **Other**.
  - `backend/vercel.json` builds `config/wsgi.py` with `@vercel/python` and routes all paths to Django. The explicit `builds` entry stops Vercel from treating the Django `api/` package as functions.
  - Env: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_NUM_PROXIES=1`, `CORS_ALLOWED_ORIGINS=<frontend URL>`.
- **Backend → container hosts (Render / Railway, as in the spec).**
  - `backend/Dockerfile` runs gunicorn as a non-root user: 1 worker × 8 threads so the cache and throttle are shared, with a 60 s timeout.
  - `render.yaml` is a ready Render Blueprint. Alternatively, create a Python service with root `backend`, build `pip install -r requirements.txt && python manage.py collectstatic --noinput`, and start `gunicorn config.wsgi:application`.
- **Frontend → Vercel (live).**
  - New Project → this repo → **Root Directory `frontend`** (Vite), and set `VITE_API_BASE_URL` to the backend URL.
  - If you use another API host or `VITE_MAP_STYLE_URL`, add it to the CSP in `frontend/vercel.json`.

Smoke test a deployment:

```bash
cd backend
python scripts/smoke_test.py --api https://<api-host> --web https://<app-host>
```

It checks geocode, plan (cold and warm against the 5 s target), heatmap, validation, CORS, the HTTPS redirect, security headers and the frontend CSP, and exits non-zero on any failure.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | backend | Django secret key (required) |
| `DJANGO_DEBUG` | backend | `True` for local development only (default `False`) |
| `DJANGO_ALLOWED_HOSTS` | backend | Comma-separated hostnames; platform hostnames are added automatically |
| `CORS_ALLOWED_ORIGINS` | backend | Comma-separated frontend origins |
| `DJANGO_NUM_PROXIES` | backend | Trusted proxies in front of the app (`1` on Vercel/Render), for per-IP throttling |
| `DJANGO_SECURE_HTTPS` | backend | Override HTTPS hardening (defaults to on when `DEBUG` is off) |
| `ORS_API_KEY` | backend | OpenRouteService key, server-side only; empty → Valhalla/Photon fallback |
| `REDIS_URL` | backend | Optional shared cache; LocMem when empty |
| `VITE_API_BASE_URL` | frontend | Base URL of the API |
| `VITE_MAP_STYLE_URL` | frontend | Optional MapLibre style URL (default: OpenFreeMap positron, no key) |

## Project structure

```
backend/
  config/          settings (env-driven, security), urls, wsgi (Vercel `app`)
  api/             views, serializers, planner pipeline, exception → HTTP mapping
  routing/         ORS + Valhalla/Photon clients, polyline decoder, provider selection, cache
  checkpoints/     haversine sampler, ETA interpolation, per-checkpoint paths
  weather/         batched Open-Meteo client, unit normalisation, ETA-hour lookup, cache
  risk/            classify(): thresholds + load overrides (pure)
  recommend/       route stats + spec sort key + reason text (pure)
  heatmap/         buffered grid (≤400 pts) + 0–48 h scoring
  upstream.py      shared HTTP client: timeout, retry, safe logging, typed errors
  scripts/         smoke_test.py for live deployments
  tests/           240 tests
  Dockerfile, gunicorn.conf.py, vercel.json, pytest.ini, ruff.toml
frontend/
  src/api/         typed client + API types
  src/components/  TripForm, PlaceAutocomplete, MapView, CheckpointPopup, RouteCards,
                   HeatmapLayer, Legend, PanelStates
  src/lib/         risk colours, GeoJSON builders, heatmap frames + calibration,
                   MapLibre worker setup, formatting
  vercel.json      build + CSP and security headers
render.yaml        Render Blueprint (alternative backend host)
.github/           Dependabot
```
