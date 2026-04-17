# DownTime Event Collection Agent

A Python-based event collection agent that fetches events from **AllEvents.in** and **Facebook Events** using Playwright with anti-detection measures. Designed to run as a **Northflank cron job**.

## What it does

1. Browses AllEvents.in city pages for each of the top 50 US cities
2. Browses Facebook Events search for each city (falls back to Google if blocked)
3. Deduplicates events across both sources using fuzzy title+date+venue matching
4. Scores every event using the same scoring engine as the main DownTime backend (0–100)
5. Saves results as timestamped JSON files in `/data/`
6. Optionally POSTs results to the DownTime backend API

---

## File Structure

```
downtime-agent/
├── agent.py                ← Main runner (entry point)
├── config.py               ← Settings, city list, anti-detection config
├── models.py               ← Event Pydantic model
├── scoring.py              ← Scoring engine (ported from backend)
├── fetchers/
│   ├── __init__.py
│   ├── allevents.py        ← AllEvents.in Playwright fetcher
│   └── facebook_events.py  ← Facebook Events Playwright fetcher
├── Dockerfile              ← Northflank cron deployment
├── requirements.txt
├── .env.example
└── README.md
```

---

## Local Development

### Prerequisites

- Python 3.12+
- `pip install -r requirements.txt`
- `playwright install chromium`

### Setup

```bash
cp .env.example .env
# Edit .env — at minimum set BACKEND_URL if you want to push results
```

### Run

```bash
# All 50 cities
python -m agent

# Specific cities
python -m agent --cities Austin,Denver

# Fetch-only, no backend push
python -m agent --dry-run

# Specific city, dry run
python -m agent --cities "New York" --dry-run
```

---

## Docker

### Build

```bash
docker build -t downtime-agent .
```

### Run locally

```bash
docker run --env-file .env -v $(pwd)/data:/app/data downtime-agent
```

### With specific cities

```bash
docker run --env-file .env downtime-agent python -m agent --cities Austin,Nashville
```

---

## Northflank Cron Deployment

1. **Create a new Job** in Northflank (type: Cron Job)
2. **Docker image**: build from this repo or push to a registry
3. **Schedule**: e.g. `0 6 * * *` (daily at 06:00 UTC)
4. **Command**: `python -m agent` (or leave at Dockerfile default)
5. **Environment variables**: set all values from `.env.example` in the Northflank UI
6. **Volume**: optionally mount a persistent volume at `/app/data` to keep history

### Required environment variables

| Variable | Description | Required |
|---|---|---|
| `BACKEND_URL` | DownTime backend base URL | Optional |
| `BACKEND_API_KEY` | Bearer token for backend auth | Optional |
| `DATA_DIR` | Output directory (default `/app/data`) | No |
| `FETCH_DAYS_AHEAD` | Days ahead to search (default `14`) | No |
| `MAX_EVENTS_PER_CITY` | Max events to keep per city (default `100`) | No |
| `MAX_REQUESTS_PER_SITE` | Max page loads per website per city (default `30`) | No |
| `DELAY_MIN` / `DELAY_MAX` | Random delay range in seconds (default `2.0`/`8.0`) | No |

---

## Output Format

Each city produces a file: `/data/{city-slug}_{YYYYMMDD_HHMMSS}.json`

```json
{
  "city": "Austin",
  "state": "TX",
  "lat": 30.2672,
  "lon": -97.7431,
  "run_at": "20240315_060012",
  "event_count": 87,
  "events": [
    {
      "id": "ae_abc123def456",
      "title": "South by Southwest Music Festival",
      "description": "...",
      "category": "festivals",
      "scenario": "weekend-adventure",
      "source": "allevents",
      "source_url": "https://allevents.in/austin/sxsw-2025/...",
      "venue": "Downtown Austin",
      "city": "Austin",
      "state": "TX",
      "date_start": "2025-03-15",
      "time_info": "Sat, Mar 15 at 12:00 PM",
      "price_range": "$150",
      "price_note": "Tickets at $150",
      "image_url": "https://...",
      "camera_worthy": true,
      "camera_note": "Vibrant colours and crowds — shoot wide to capture the energy",
      "score": 88,
      "is_featured": true,
      "attendee_count": null,
      "tags": ["festivals"],
      "created_at": "2024-03-15T06:00:12.000000"
    }
  ]
}
```

A `manifest_{run_ts}.json` file is also written summarising the full run across all cities.

---

## Anti-Detection Measures

| Measure | Implementation |
|---|---|
| User-agent rotation | Pool of 12 real Chrome/Firefox/Safari UAs, one picked randomly per browser launch |
| Viewport randomisation | Pool of 10 common screen sizes |
| Random delays | 2–8 s between page loads (configurable) |
| Human-like scrolling | Randomised scroll distances with variable pauses, occasional back-scrolls |
| Stealth JS overrides | Removes `navigator.webdriver`, fakes plugin/language lists, patches permissions API |
| Resource blocking | Images/fonts/tracking pixels blocked to reduce fingerprint and speed up loads |
| Request capping | Max 30 page loads per site per city per run |
| Graceful block handling | Login walls and captchas are logged and skipped — no aggressive retry |
| Inter-city delay | 10–20 s random pause between cities |

---

## Scoring

Events are scored 0–100 using five dimensions (ported from the main backend):

| Dimension | Max pts | Notes |
|---|---|---|
| Category match | 25 | Against user interests if provided; otherwise popularity baseline |
| Camera/photo value | 25 | Category + visual keywords (sunset, murals, skylines, etc.) |
| Price value | 20 | Free = 20 pts; $200+ = 3 pts |
| Proximity | 15 | Distance from city centre coordinates |
| Uniqueness | 15 | One-time events, festivals, specific dates score higher |

Events scoring ≥ 80 are marked `is_featured: true`.

---

## Backend API Integration

When `BACKEND_URL` is set, after processing each city the agent POSTs to:

```
POST {BACKEND_URL}/internal/events
Authorization: Bearer {BACKEND_API_KEY}
Content-Type: application/json

{
  "city": "Austin",
  "state": "TX",
  "source": "agent",
  "event_count": 87,
  "events": [...]
}
```

This endpoint does not exist in the current backend — add it to `main.py` to enable ingestion.

---

## Adding New Sources

1. Create `fetchers/my_source.py` with an `async def fetch_my_source_events(city, state) -> list[Event]` function
2. Import it in `fetchers/__init__.py`
3. Call it in `agent.py` inside `_process_city()` alongside the existing fetchers
