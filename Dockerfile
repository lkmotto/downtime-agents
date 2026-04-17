# ──────────────────────────────────────────────────────────────
# DownTime Event Collection Agent
# Cron job — one-shot runner
#
# Build:   docker build -t downtime-agent .
# Run:     docker run --env-file .env downtime-agent
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Install system dependencies required by Playwright / Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium runtime deps
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Font support (bookworm-compatible names)
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-unifont \
    # Network / curl for healthchecks
    curl \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium browser (skip install-deps since we handle deps above)
RUN playwright install chromium

# Copy application source
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Non-root user for security
RUN addgroup --system agent && adduser --system --ingroup agent agent
RUN chown -R agent:agent /app
USER agent

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data

# One-shot cron command
CMD ["python", "-m", "agent"]
