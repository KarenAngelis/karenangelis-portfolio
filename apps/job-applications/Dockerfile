FROM python:3.12-slim
WORKDIR /app
COPY apps/job-applications/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/job-applications/ .
CMD ["python", "-u", "jobs.py", "run"]
