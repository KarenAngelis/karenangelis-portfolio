FROM python:3.14-slim
WORKDIR /app
COPY apps/domains-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/domains-api/*.py ./
RUN mkdir /data && chown 65534:65534 /data && chmod 700 /data
ENV DOMAINS_DB=/data/domains.sqlite3
USER 65534:65534
CMD ["uvicorn", "main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8002", "--workers", "1", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
