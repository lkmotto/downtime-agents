# DownTime Weekend Email Digest Agent
# Northflank cron job — runs every Thursday evening at ~7pm CT
#
# Build:  docker build -t downtime-email-agent .
# Run:    docker run --env-file .env downtime-email-agent
# Cron:   0 1 * * 5 (01:00 UTC Friday = 8pm CT Thursday)

FROM python:3.12-slim

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Copy the email agent ──────────────────────────────────────────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the email agent source
COPY . /app/downtime-email-agent/

# Copy the backend (fetchers + scoring engine) into the image
# The curator.py resolves BACKEND_DIR relative to its own __file__,
# so we place backend at the expected relative path.
COPY ../downtime-product/backend /app/downtime-product/backend/

# ── Working directory for execution ──────────────────────────────────────────
WORKDIR /app/downtime-email-agent

# ── Create previews directory ─────────────────────────────────────────────────
RUN mkdir -p /app/downtime-email-agent/previews

# ── Environment defaults (override at runtime via Northflank env vars) ────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CITY=Dallas \
    STATE=TX \
    CITY_LAT=32.7767 \
    CITY_LON=-96.7970 \
    USER_NAME=Luke \
    RECIPIENT_EMAIL=ljm32901@gmail.com \
    FROM_EMAIL="DownTime <downtime@mail.getdowntime.app>" \
    TOP_N_EVENTS=10

# ── One-shot execution ────────────────────────────────────────────────────────
# Runs the full pipeline: fetch → curate → compose → send
CMD ["python", "agent.py"]
