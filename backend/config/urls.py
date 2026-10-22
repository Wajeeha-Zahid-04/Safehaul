from django.urls import include, path

urlpatterns = [
    path("api/", include("api.urls")),
]

# Unhandled errors return a generic JSON 500 (no HTML, no stack trace).
handler500 = "rest_framework.exceptions.server_error"
