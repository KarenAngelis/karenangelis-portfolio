FROM python:3.12-slim
WORKDIR /app
COPY apps/prospect-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m app && mkdir /data && chown app /data
COPY apps/prospect-api/ .
USER app
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
