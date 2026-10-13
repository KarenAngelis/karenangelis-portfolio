FROM python:3.14-slim
WORKDIR /app
COPY apps/stats-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/stats-api/main.py .
RUN mkdir /data && chown 65534:65534 /data
ENV STATS_DB=/data/stats.sqlite3
USER 65534:65534
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
