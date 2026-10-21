from django.urls import path

from api.views import GeocodeView, PlanView

urlpatterns = [
    path("geocode", GeocodeView.as_view(), name="geocode"),
    path("plan", PlanView.as_view(), name="plan"),
]
