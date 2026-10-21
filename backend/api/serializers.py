"""Request validation (spec §3 "Input validation")."""

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from rest_framework import serializers

MAX_STRING = 200
MAX_LOAD_LB = 120_000
INTERVALS_MI = (10, 25, 50)
MAX_DEPARTURE_AHEAD = timedelta(hours=48)
# The form defaults to "now"; allow for the time between filling it in and submitting.
DEPARTURE_GRACE = timedelta(minutes=5)


def validate_within_window(value: datetime) -> datetime:
    """Shared rule for departure / heatmap start: now (minus grace) to now + 48 h."""
    now = timezone.now()
    if value < now - DEPARTURE_GRACE:
        raise serializers.ValidationError("Time cannot be in the past.")
    if value > now + MAX_DEPARTURE_AHEAD:
        raise serializers.ValidationError("Time must be within the next 48 hours.")
    return value


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=MAX_STRING, trim_whitespace=True)


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=MAX_STRING)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=INTERVALS_MI)

    def validate_departure(self, value: datetime) -> datetime:
        return validate_within_window(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        o, d = attrs["origin"], attrs["destination"]
        if (o["lat"], o["lon"]) == (d["lat"], d["lon"]):
            raise serializers.ValidationError("Origin and destination must differ.")
        return attrs


class HeatmapRequestSerializer(serializers.Serializer):
    # [min_lon, min_lat, max_lon, max_lat], i.e. GeoJSON bbox order (as /plan returns it).
    bbox = serializers.ListField(child=serializers.FloatField(), min_length=4, max_length=4)
    start = serializers.DateTimeField()
    # Optional extension to the spec body so heatmap scores apply the same load overrides.
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB, default=0)

    def validate_start(self, value: datetime) -> datetime:
        return validate_within_window(value)

    def validate_bbox(self, value: list[float]) -> list[float]:
        min_lon, min_lat, max_lon, max_lat = value
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise serializers.ValidationError(
                "bbox must be [min_lon, min_lat, max_lon, max_lat] with min < max."
            )
        return value
