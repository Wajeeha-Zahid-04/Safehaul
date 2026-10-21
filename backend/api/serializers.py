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
        now = timezone.now()
        if value < now - DEPARTURE_GRACE:
            raise serializers.ValidationError("Departure cannot be in the past.")
        if value > now + MAX_DEPARTURE_AHEAD:
            raise serializers.ValidationError("Departure must be within the next 48 hours.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        o, d = attrs["origin"], attrs["destination"]
        if (o["lat"], o["lon"]) == (d["lat"], d["lon"]):
            raise serializers.ValidationError("Origin and destination must differ.")
        return attrs
