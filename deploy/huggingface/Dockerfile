# Hugging Face Space build for the SafeHaul API.
# The Space holds only this file + README.md: it downloads the backend from the public GitHub
# repo at build time, so redeploying is just "Factory rebuild" in the Space settings.
# Same steps as backend/Dockerfile, which builds from a local checkout instead.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

RUN useradd --create-home --uid 1000 app

# Remote ADD re-downloads when the branch changes, so a rebuild always gets the latest main.
ADD https://github.com/Wajeeha-Zahid-04/Safehaul/archive/refs/heads/main.tar.gz /tmp/src.tar.gz
RUN mkdir /app \
    && tar -xzf /tmp/src.tar.gz --strip-components=2 -C /app Safehaul-main/backend \
    && rm /tmp/src.tar.gz
WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt \
    && DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

USER app
EXPOSE 7860
CMD ["gunicorn", "config.wsgi:application"]
