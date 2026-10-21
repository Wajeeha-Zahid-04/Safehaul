from django.urls import path

from api.views import GeocodeView, HeatmapView, PlanView

urlpatterns = [
    path("geocode", GeocodeView.as_view(), name="geocode"),
    path("plan", PlanView.as_view(), name="plan"),
    path("heatmap", HeatmapView.as_view(), name="heatmap"),
]
