"""Provider selection + caching. ORS is used whenever ORS_API_KEY is set; otherwise the keyless
Valhalla/Photon fallback (documented deviation: ORS sign-up was unavailable)."""

from django.conf import settings
from django.core.cache import cache

from routing import ors, photon, valhalla
from routing.types import LatLon, Place, Route

GEOCODE_TTL_S = 24 * 60 * 60
ROUTES_TTL_S = 60 * 60
COORD_KEY_DECIMALS = 5


def provider_name() -> str:
    return "ors" if settings.ORS_API_KEY else "fallback"


def geocode(query: str) -> list[Place]:
    query = query.strip()
    if not query:
        return []
    key = f"geocode:{provider_name()}:{query.lower()}"
    cached: list[Place] | None = cache.get(key)
    if cached is not None:
        return cached
    places = (
        ors.geocode(query, settings.ORS_API_KEY) if settings.ORS_API_KEY else photon.geocode(query)
    )
    cache.set(key, places, GEOCODE_TTL_S)
    return places


def get_routes(origin: LatLon, destination: LatLon, load_lb: float) -> list[Route]:
    key = f"routes:{provider_name()}:{_coord_key(origin)}:{_coord_key(destination)}:{load_lb:g}"
    cached: list[Route] | None = cache.get(key)
    if cached is not None:
        return cached
    if settings.ORS_API_KEY:
        routes = ors.directions(origin, destination, load_lb, settings.ORS_API_KEY)
    else:
        routes = valhalla.directions(origin, destination, load_lb)
    cache.set(key, routes, ROUTES_TTL_S)
    return routes


def _coord_key(point: LatLon) -> str:
    return f"{point[0]:.{COORD_KEY_DECIMALS}f},{point[1]:.{COORD_KEY_DECIMALS}f}"
