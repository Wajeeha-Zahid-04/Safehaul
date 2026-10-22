"""Security hardening (spec §3): deploy checks, HTTPS, headers, CORS, throttling, error leakage."""

import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROD_ENV = {
    "DJANGO_DEBUG": "False",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
    "DJANGO_ALLOWED_HOSTS": "safehaul-api.onrender.com",
    "CORS_ALLOWED_ORIGINS": "https://safehaul.vercel.app",
}
HTTPS = {"HTTP_X_FORWARDED_PROTO": "https"}


def run_manage(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


def shell_print(code: str, env: dict[str, str]) -> str:
    """Last stdout line of `manage.py shell -c` (Django 5.2 prints an auto-import banner first)."""
    result = run_manage("shell", "-c", code, env=env)
    lines = result.stdout.strip().splitlines()
    assert lines, result.stderr
    return lines[-1]


# --- production configuration ---
def test_deploy_checks_pass_with_production_env() -> None:
    result = run_manage("check", "--deploy", "--fail-level", "WARNING", env=PROD_ENV)
    assert result.returncode == 0, result.stdout + result.stderr


def test_production_env_enables_https_hardening() -> None:
    script = (
        "from django.conf import settings as s;"
        "print(s.DEBUG, s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS, s.SECURE_PROXY_SSL_HEADER[0],"
        " s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE)"
    )
    assert shell_print(script, PROD_ENV).split() == [
        "False",
        "True",
        "31536000",
        "HTTP_X_FORWARDED_PROTO",
        "True",
        "True",
    ]


# --- HTTPS redirect + HSTS behind a TLS-terminating proxy ---
@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_HSTS_SECONDS=31_536_000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
)
def test_plain_http_redirects_and_https_gets_hsts() -> None:
    plain = Client().get("/api/geocode", {"q": ""})
    assert plain.status_code == 301
    assert plain["Location"].startswith("https://")

    secure = Client().get("/api/geocode", {"q": ""}, **HTTPS)
    assert secure.status_code == 400  # reached the view (validation), not redirected
    assert secure["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


# --- always-on security headers ---
def test_security_headers_on_api_responses() -> None:
    res = Client().get("/api/geocode", {"q": ""})
    assert res["X-Content-Type-Options"] == "nosniff"
    assert res["X-Frame-Options"] == "DENY"
    assert res["Referrer-Policy"] == "same-origin"


# --- CORS ---
@override_settings(CORS_ALLOWED_ORIGINS=["https://safehaul.vercel.app"])
def test_cors_allows_only_the_frontend_origin() -> None:
    def preflight(origin: str, method: str = "POST") -> Any:
        return Client().options(
            "/api/plan",
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD=method,
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )

    ok = preflight("https://safehaul.vercel.app")
    assert ok["Access-Control-Allow-Origin"] == "https://safehaul.vercel.app"
    allowed = {m.strip() for m in ok["Access-Control-Allow-Methods"].split(",")}
    assert allowed == {"GET", "POST", "OPTIONS"}

    assert "Access-Control-Allow-Origin" not in preflight("https://evil.example")
    assert "Access-Control-Allow-Origin" not in preflight("http://localhost:5173")


@override_settings(CORS_ALLOWED_ORIGINS=["https://safehaul.vercel.app"])
def test_cors_headers_only_on_api_paths() -> None:
    res = Client().get("/static/missing.css", HTTP_ORIGIN="https://safehaul.vercel.app")
    assert "Access-Control-Allow-Origin" not in res


# --- throttling can't be dodged by spoofing X-Forwarded-For ---
def test_throttle_uses_proxy_appended_ip_not_spoofed_header() -> None:
    rest = {
        "DEFAULT_AUTHENTICATION_CLASSES": [],
        "DEFAULT_PERMISSION_CLASSES": [],
        "UNAUTHENTICATED_USER": None,
        "DEFAULT_THROTTLE_RATES": {"plan": "30/min", "heatmap": "30/min"},
        "NUM_PROXIES": 1,
    }
    with override_settings(REST_FRAMEWORK=rest):
        client = APIClient()
        statuses = [
            # Attacker rotates the leading (spoofed) entry; the proxy appends the real IP last.
            client.post(
                "/api/plan", {}, format="json", HTTP_X_FORWARDED_FOR=f"10.9.9.{i}, 203.0.113.7"
            ).status_code
            for i in range(31)
        ]
    assert statuses[30] == 429


# --- request size + error leakage ---
def test_oversized_body_is_rejected() -> None:
    res = Client().post("/api/plan", data="x" * (101 * 1024), content_type="application/json")
    assert res.status_code in (400, 413)


class _Boom(APIView):
    def get(self, request: Any) -> Response:
        raise RuntimeError("secret internals: db password=hunter2")


urlpatterns = [path("boom", _Boom.as_view())]
handler500 = "rest_framework.exceptions.server_error"


@override_settings(ROOT_URLCONF=__name__, DEBUG=False)
def test_unhandled_error_is_generic_json_without_details() -> None:
    res = Client(raise_request_exception=False).get("/boom")
    assert res.status_code == 500
    assert res["Content-Type"].startswith("application/json")
    assert "hunter2" not in res.content.decode()
    assert "Traceback" not in res.content.decode()


@pytest.mark.parametrize(
    ("var", "host"),
    [
        ("RENDER_EXTERNAL_HOSTNAME", "safehaul-api-x1y2.onrender.com"),
        ("RAILWAY_PUBLIC_DOMAIN", "safehaul-production.up.railway.app"),
        ("SPACE_HOST", "wajeeha-zahid-04-safehaul-api.hf.space"),
    ],
)
def test_platform_hostname_is_allowed_automatically(var: str, host: str) -> None:
    hosts = shell_print(
        "from django.conf import settings; print(*settings.ALLOWED_HOSTS)", {**PROD_ENV, var: host}
    )
    assert hosts.split() == ["safehaul-api.onrender.com", host]


def test_debug_is_off_unless_explicitly_enabled() -> None:
    # Empty value = not enabled (an exported empty var also stops .env from setting it).
    env = {**PROD_ENV, "DJANGO_DEBUG": ""}
    assert shell_print("from django.conf import settings; print(settings.DEBUG)", env) == "False"


def test_env_file_is_git_ignored() -> None:
    ignored = (BACKEND_DIR.parent / ".gitignore").read_text().splitlines()
    assert ".env" in ignored
    assert "!.env.example" in ignored
