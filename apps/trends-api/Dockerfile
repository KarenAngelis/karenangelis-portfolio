FROM python:3.14-slim
WORKDIR /app
COPY apps/trends-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/trends-api/main.py .
USER 65534:65534
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
