FROM python:3.11-slim
RUN addgroup --system app && adduser --system --group app
WORKDIR /app
COPY mcp-gateway/requirements.txt ./requirements.txt
COPY shared/ ./shared/
RUN pip install --no-cache-dir -r requirements.txt ./shared/
COPY mcp-gateway/app/ ./app/
USER app
EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
