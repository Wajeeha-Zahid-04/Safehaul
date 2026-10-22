# SafeHaul API image: one long-running gunicorn process (settings in gunicorn.conf.py).
# Runs anywhere that runs containers (Hugging Face Spaces, Render, Railway, Fly, ...).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# collectstatic only needs settings to import; the real secret comes from the runtime env.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

USER app
EXPOSE 7860
CMD ["gunicorn", "config.wsgi:application"]
