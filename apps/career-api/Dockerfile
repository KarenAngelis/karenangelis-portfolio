FROM node:22-bookworm-slim AS codex
ARG CODEX_VERSION=0.163.0
RUN npm install -g --include=optional @openai/codex@${CODEX_VERSION}

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY apps/career-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=codex /usr/local/lib/node_modules/@openai/codex /opt/codex
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
RUN ln -s /opt/codex/bin/codex.js /usr/local/bin/codex && useradd -m -u 10001 career && mkdir /data && chown career:career /data
RUN codex --version
COPY apps/career-api/ .
COPY web/data/profile.json web/data/career.json web/data/evidence.json /app/profile-data/
USER career
EXPOSE 8010
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1", "--no-access-log"]
