FROM python:3.11-slim

RUN addgroup --system app && adduser --system --group app

WORKDIR /app

COPY worker-service/requirements.txt ./requirements.txt
COPY shared/ ./shared/

RUN pip install --no-cache-dir -r requirements.txt &&     pip install --no-cache-dir -e ./shared/

COPY worker-service/app/ ./app/

USER app

# Celery worker — not a web server, no EXPOSE needed
CMD ["celery", "-A", "app.celery_app:celery_app", "worker",      "--loglevel=info", "--concurrency=4", "-E"]
