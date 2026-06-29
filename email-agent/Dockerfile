# DownTime Weekend Email Digest Agent
# Cron job — runs every Thursday evening
#
# Build:  docker build -t downtime-email-agent .
# Run:    docker run --env-file .env downtime-email-agent

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything (agent + bundled backend/)
COPY . .

RUN mkdir -p /app/previews

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CITY=Dallas \
    STATE=TX \
    CITY_LAT=32.7767 \
    CITY_LON=-96.7970 \
    USER_NAME=Luke \
    RECIPIENT_EMAIL=ljm32901@gmail.com \
    FROM_EMAIL="DownTime <onboarding@resend.dev>" \
    TOP_N_EVENTS=10

CMD ["python", "agent.py"]
