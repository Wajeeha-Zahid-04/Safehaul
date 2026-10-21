"""API views. Upstream and routing failures are turned into responses by api.exceptions.handler."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.planner import plan_trip
from api.serializers import (
    GeocodeQuerySerializer,
    HeatmapRequestSerializer,
    PlanRequestSerializer,
)
from heatmap import BBox, build_heatmap
from routing import geocode


class GeocodeView(APIView):
    def get(self, request: Request) -> Response:
        query = GeocodeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        places = geocode(query.validated_data["q"])
        return Response(
            {"results": [{"label": p.label, "lat": p.lat, "lon": p.lon} for p in places]}
        )


class PlanView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "plan"

    def post(self, request: Request) -> Response:
        body = PlanRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        plan = plan_trip(
            origin=(data["origin"]["lat"], data["origin"]["lon"]),
            destination=(data["destination"]["lat"], data["destination"]["lon"]),
            departure=data["departure"],
            load_lb=data["load_lb"],
            interval_mi=data["interval_mi"],
        )
        return Response(plan)


class HeatmapView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "heatmap"

    def post(self, request: Request) -> Response:
        body = HeatmapRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        return Response(build_heatmap(BBox(*data["bbox"]), data["start"], data["load_lb"]))
