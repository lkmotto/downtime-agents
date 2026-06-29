# DownTime Weekend Email Digest Agent

A standalone Python agent that generates and sends a personalized weekend recommendation email for **Luke Motto** in the **Dallas–Fort Worth** area. Runs as a Northflank cron job every Thursday evening.

---

## What It Does

Every Thursday at ~7–8pm CT, this agent:

1. **Fetches events** from Ticketmaster, SeatGeek, SerpAPI Google Events, and OpenTripMap — the same sources as the DownTime app backend
2. **Scores and curates** the top 10 events for the upcoming Friday–Sunday using the DownTime scoring engine (weighted for photography value, price, proximity, and uniqueness)
3. **Groups events** into five email categories: Date Night, Adventure/Outdoors, Food & Drink, Arts & Culture, and Free Things
4. **Composes a dark-themed HTML email** matching DownTime's aesthetic, with camera-worthy badges for photogenic events
5. **Sends via Resend** to `ljm32901@gmail.com`

---

## File Structure

```
downtime-email-agent/
├── agent.py           # Orchestrator — fetch → curate → compose → send
├── curator.py         # Event fetching, scoring, categorization pipeline
├── email_composer.py  # HTML + plain-text email templates
├── sender.py          # Resend API integration
├── config.py          # Environment variable loading
├── models.py          # Data models (mirrors backend Event + email-specific types)
├── Dockerfile         # Python 3.12-slim, one-shot CMD
├── requirements.txt   # httpx, pydantic, python-dotenv
├── .env.example       # Template for required env vars
└── README.md
```

---

## Setup

### 1. Clone and install dependencies

```bash
cd downtime-email-agent
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required:**
- `RESEND_API_KEY` — from [resend.com/api-keys](https://resend.com/api-keys)
- At least one of: `TM_API_KEY`, `SG_CLIENT_ID`, `SERPAPI_KEY`, `OTM_API_KEY`

**Optional (have defaults):**
- `FROM_EMAIL` — default: `DownTime <downtime@mail.getdowntime.app>`
- `RECIPIENT_EMAIL` — default: `ljm32901@gmail.com`
- `CITY` / `STATE` — default: `Dallas` / `TX`
- `TOP_N_EVENTS` — default: `10`

---

## Running Locally

### Full pipeline
```bash
python agent.py
```

### Dry run (no email sent — prints plain text to stdout)
```bash
python agent.py --dry-run
```

### Test email only (validates Resend integration)
```bash
python agent.py --test
```

### Individual module testing
```bash
# Test curation only
python curator.py

# Test email composition (outputs HTML)
python email_composer.py > preview.html

# Test send
python sender.py ljm32901@gmail.com
```

---

## Docker / Northflank Deployment

### Build the image

From the **workspace root** (parent of both `downtime-email-agent/` and `downtime-product/`):

```bash
docker build -f downtime-email-agent/Dockerfile \
  -t downtime-email-agent \
  --build-context root=. \
  .
```

### Run locally with env file
```bash
docker run --env-file downtime-email-agent/.env downtime-email-agent
```

### Northflank Cron Job Setup

1. **Create a new Job** in Northflank → select "Cron Job"
2. **Docker image**: push to your registry and reference it here
3. **Schedule**: `0 1 * * 5` — runs at 01:00 UTC every Friday (= ~8pm CT Thursday)
4. **Environment variables**: add all keys from `.env.example` as Northflank secrets
5. **CMD**: leave as default (uses `CMD ["python", "agent.py"]` from Dockerfile)

---

## Architecture

```
agent.py (orchestrator)
    │
    ├── curator.py
    │     ├── fetchers/ticketmaster.py  ← from backend
    │     ├── fetchers/seatgeek.py      ← from backend
    │     ├── fetchers/serpapi_google.py← from backend
    │     ├── fetchers/opentripmap.py   ← from backend
    │     └── scoring.py               ← from backend
    │
    ├── email_composer.py
    │     └── Dark-themed HTML + plain text
    │
    └── sender.py
          └── Resend API → ljm32901@gmail.com
```

The agent imports backend fetchers and scoring engine from the `downtime-backend` package (installed as a pip dependency), keeping all logic in one place with no duplication.

---

## Email Design

- **Background**: `#0D0D12` (DownTime dark base)
- **Surface**: `#16161F` (card backgrounds)
- **Accent**: `#F59E0B` (amber — CTAs, badges, highlights)
- **📷 Camera-Worthy badge**: amber background — marks events ideal for the Lumix S5IIX, drone, or GoPro
- **FREE badge**: emerald green
- Fully inline CSS — compatible with Gmail, Apple Mail, Outlook (web), iOS Mail

---

## Subject Line Pool

The subject rotates randomly each week from:

- "Your DFW Weekend Playbook 📍"
- "10 Ways to Win This Weekend in DFW"
- "This Weekend's Best Bets in Dallas–Fort Worth"
- "Weekend Unlocked: Your DFW Hit List"
- "DFW Weekend Drop — Don't Sleep On These"
- "Your Weekend, Curated. DFW Edition."
- "Friday's Almost Here — Here's Your Plan"
- "The DownTime DFW Weekend Guide Is In"
- "This is Your Weekend in DFW"
- "Weekend Picks, Personalized. Let's Go."

---

## User Profile

| Field | Value |
|---|---|
| Name | Luke Motto |
| Location | Roanoke TX 76262 (DFW) |
| Interests | Photography, Outdoor, Food, Arts, Festivals |
| Camera Gear | Lumix S5IIX, DJI drone, GoPro, underwater housing |
| Food Preferences | Gluten-free, dairy-free |

Events are scored with these interests weighted in. Camera-worthy events receive a visual badge and dedicated shot suggestions.
