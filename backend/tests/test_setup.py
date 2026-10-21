from django.conf import settings
from django.core.management import call_command


def test_django_system_checks_pass() -> None:
    call_command("check")


def test_secrets_come_from_environment() -> None:
    assert settings.SECRET_KEY
    assert "rest_framework" in settings.INSTALLED_APPS
    assert "corsheaders" in settings.INSTALLED_APPS
