from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.planner import plan_trip
from api.serializers import GeocodeQuerySerializer, PlanRequestSerializer
from routing import geocode
from upstream import UpstreamError

UPSTREAM_ERROR = {"detail": "Upstream service unavailable. Please try again."}


class GeocodeView(APIView):
    def get(self, request: Request) -> Response:
        query = GeocodeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            places = geocode(query.validated_data["q"])
        except UpstreamError:
            return Response(UPSTREAM_ERROR, status=status.HTTP_502_BAD_GATEWAY)
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
        try:
            plan = plan_trip(
                origin=(data["origin"]["lat"], data["origin"]["lon"]),
                destination=(data["destination"]["lat"], data["destination"]["lon"]),
                departure=data["departure"],
                load_lb=data["load_lb"],
                interval_mi=data["interval_mi"],
            )
        except UpstreamError:
            return Response(UPSTREAM_ERROR, status=status.HTTP_502_BAD_GATEWAY)
        return Response(plan)
