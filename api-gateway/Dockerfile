FROM python:3.11-slim

RUN addgroup --system app && adduser --system --group app

WORKDIR /app

COPY api-gateway/requirements.txt ./requirements.txt
COPY shared/ ./shared/

RUN pip install --no-cache-dir -r requirements.txt &&     pip install --no-cache-dir -e ./shared/

COPY api-gateway/app/ ./app/

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
