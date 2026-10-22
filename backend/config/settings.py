"""Django settings for SafeHaul. Environment-specific values come from env vars (.env locally)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Hosting platforms inject the service's public hostname; no manual ALLOWED_HOSTS edit needed.
for platform_host_var in ("RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN", "SPACE_HOST"):
    if platform_host := os.environ.get(platform_host_var):
        ALLOWED_HOSTS.append(platform_host)

ORS_API_KEY = os.environ.get("ORS_API_KEY", "")

# Redis when REDIS_URL is set, otherwise in-process LocMem (spec §2 Caching).
REDIS_URL = os.environ.get("REDIS_URL", "")
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
        if REDIS_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # Default (300) is far too small: one long route caches ~100 weather keys.
            "OPTIONS": {"MAX_ENTRIES": 10_000},
        }
    )
}

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Route geometry makes /plan responses large (~0.5 MB for 1,000 mi); gzip cuts ~70%.
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    # No cookies/sessions exist, and DRF views are CSRF-exempt by design; kept as defence in depth.
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No accounts and no persisted data (spec §3), so no database is configured.
DATABASES: dict = {}

# --- Security (spec §3) ---

# HTTPS hardening is on whenever DEBUG is off; DJANGO_SECURE_HTTPS=False allows plain-HTTP
# local runs of a production-like config.
SECURE_HTTPS = env_bool("DJANGO_SECURE_HTTPS", default=not DEBUG)
if SECURE_HTTPS:
    SECURE_SSL_REDIRECT = True
    # Render/Railway terminate TLS at their proxy and forward the original scheme.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# HSTS preload needs a domain we own; a *.onrender.com subdomain can't be submitted.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Requests are small JSON bodies; reject anything larger early.
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024

# CORS: only the frontend origin(s), only the API, only the methods the API uses.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "api.exceptions.handler",
    # Per-IP limits protecting upstream API quotas (spec §3).
    "DEFAULT_THROTTLE_RATES": {"plan": "30/min", "heatmap": "30/min"},
    # Trusted reverse proxies in front of the app (1 on Render). The client IP is taken from
    # that position in X-Forwarded-For, so a spoofed header can't dodge the throttle.
    "NUM_PROXIES": int(os.environ.get("DJANGO_NUM_PROXIES", "0")),
}

# Upstream failures are logged as warnings (no stack traces reach clients).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
