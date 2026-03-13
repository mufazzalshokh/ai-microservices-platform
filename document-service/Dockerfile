FROM python:3.11-slim

RUN addgroup --system app && adduser --system --group app

WORKDIR /app

COPY document-service/requirements.txt ./requirements.txt
COPY shared/ ./shared/

RUN pip install --no-cache-dir -r requirements.txt &&     pip install --no-cache-dir -e ./shared/

COPY document-service/app/ ./app/

USER app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
