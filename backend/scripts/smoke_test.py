"""Post-deploy smoke test for SafeHaul (spec §5 ticket 15).

Usage:
    python scripts/smoke_test.py --api https://safehaul-api.onrender.com --web https://safehaul.vercel.app

Exits non-zero if any check fails. Needs only `requests`. Note: a free Render service sleeps
when idle, so the first request may take ~50 s while it wakes up; that is reported, not failed.
"""

import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

TIMEOUT_S = 90
CHICAGO = {"label": "Chicago, Illinois, United States", "lat": 41.8781, "lon": -87.6298}
INDIANAPOLIS = {"label": "Indianapolis, Indiana, United States", "lat": 39.7684, "lon": -86.1581}
COLD_BUDGET_S = 5.0  # spec §1 success criterion


class Smoke:
    def __init__(self, api: str, web: str) -> None:
        self.api, self.web = api.rstrip("/"), web.rstrip("/")
        self.session = requests.Session()
        self.failures = 0

    def check(self, name: str, fn: Callable[[], str]) -> None:
        try:
            detail = fn()
            print(f"PASS  {name}: {detail}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            self.failures += 1
            print(f"FAIL  {name}: {exc}")

    def post(self, path: str, body: dict[str, Any]) -> tuple[requests.Response, float]:
        start = time.perf_counter()
        res = self.session.post(f"{self.api}{path}", json=body, timeout=TIMEOUT_S)
        return res, time.perf_counter() - start

    # --- checks ---
    def wake(self) -> str:
        start = time.perf_counter()
        res = self.session.get(
            f"{self.api}/api/geocode", params={"q": "Chicago"}, timeout=TIMEOUT_S
        )
        res.raise_for_status()
        return f"API reachable in {time.perf_counter() - start:.1f}s (includes free-tier wake-up)"

    def geocode(self) -> str:
        res = self.session.get(
            f"{self.api}/api/geocode", params={"q": "Indianapolis"}, timeout=TIMEOUT_S
        )
        res.raise_for_status()
        results = res.json()["results"]
        assert results, "no geocode results"
        return f"{len(results)} results, first: {results[0]['label']}"

    def plan(self) -> str:
        departure = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        body = {
            "origin": CHICAGO,
            "destination": INDIANAPOLIS,
            "departure": departure,
            "load_lb": 40_000,
            "interval_mi": 25,
        }
        res, cold = self.post("/api/plan", body)
        assert res.status_code == 200, f"HTTP {res.status_code}: {res.text[:200]}"
        data = res.json()
        assert data["routes"], "no routes"
        assert data["recommended_id"] == data["routes"][0]["id"], (
            "recommended route not ranked first"
        )
        assert all(r["checkpoints"] for r in data["routes"]), "route without checkpoints"
        _, warm = self.post("/api/plan", body)
        budget = "within" if cold <= COLD_BUDGET_S else "OVER"
        self.heatmap_body = {
            "bbox": data["routes"][0]["bbox"],
            "start": departure,
            "load_lb": 40_000,
        }
        return (
            f"{len(data['routes'])} routes, recommended {data['recommended_id']} "
            f"({data['recommendation_reason']}); cold {cold:.2f}s ({budget} {COLD_BUDGET_S:.0f}s), "
            f"warm {warm:.2f}s"
        )

    def heatmap(self) -> str:
        res, took = self.post("/api/heatmap", self.heatmap_body)
        assert res.status_code == 200, f"HTTP {res.status_code}: {res.text[:200]}"
        data = res.json()
        assert data["hours"] == 49 and len(data["scores"]) == 49, "expected 49 hourly frames"
        assert all(len(row) == len(data["points"]) for row in data["scores"]), "ragged scores"
        points, hours, spacing = len(data["points"]), data["hours"], data["spacing_km"]
        return f"{points} points x {hours} h @ {spacing} km in {took:.2f}s"

    def validation(self) -> str:
        res, _ = self.post("/api/plan", {"load_lb": 999_999})
        assert res.status_code == 400, f"expected 400, got {res.status_code}"
        return "invalid body rejected with 400"

    def cors(self) -> str:
        def preflight(origin: str) -> requests.Response:
            return self.session.options(
                f"{self.api}/api/plan",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
                timeout=TIMEOUT_S,
            )

        allowed = preflight(self.web).headers.get("Access-Control-Allow-Origin")
        assert allowed == self.web, f"frontend origin not allowed (got {allowed!r})"
        evil = preflight("https://evil.example").headers.get("Access-Control-Allow-Origin")
        assert evil is None, f"foreign origin allowed: {evil!r}"
        return f"only {self.web} allowed"

    def https(self) -> str:
        plain = self.api.replace("https://", "http://", 1)
        res = self.session.get(f"{plain}/api/geocode?q=x", allow_redirects=False, timeout=TIMEOUT_S)
        assert res.status_code in (301, 302, 307, 308), f"HTTP not redirected ({res.status_code})"
        assert res.headers["Location"].startswith("https://"), "redirect is not to https"
        secure = self.session.get(f"{self.api}/api/geocode", params={"q": "x"}, timeout=TIMEOUT_S)
        for header in ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options"):
            assert header in secure.headers, f"missing {header}"
        return "http->https redirect, HSTS, nosniff, X-Frame-Options"

    def frontend(self) -> str:
        res = self.session.get(self.web, timeout=TIMEOUT_S)
        res.raise_for_status()
        assert 'id="root"' in res.text, "app shell not served"
        for header in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options"):
            assert header in res.headers, f"missing {header}"
        return "app shell served with CSP and security headers"

    def run(self) -> int:
        self.check("API wake-up", self.wake)
        self.check("GET /api/geocode", self.geocode)
        self.check("POST /api/plan", self.plan)
        self.check("POST /api/heatmap", self.heatmap)
        self.check("Input validation", self.validation)
        self.check("CORS", self.cors)
        self.check("HTTPS + security headers (API)", self.https)
        self.check("Frontend (Vercel)", self.frontend)
        print(
            f"\n{'ALL CHECKS PASSED' if not self.failures else f'{self.failures} CHECK(S) FAILED'}"
        )
        return 1 if self.failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--api", required=True, help="Backend base URL, e.g. https://safehaul-api.onrender.com"
    )
    parser.add_argument(
        "--web", required=True, help="Frontend URL, e.g. https://safehaul.vercel.app"
    )
    args = parser.parse_args()
    sys.exit(Smoke(args.api, args.web).run())


if __name__ == "__main__":
    main()
