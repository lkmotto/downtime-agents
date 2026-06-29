"""
Configuration for the DownTime Weekend Email Digest Agent.

All values are loaded from environment variables. See .env.example for reference.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Email ──────────────────────────────────────────────────────────────────────
RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
# Use onboarding@resend.dev as fallback until mail.getdowntime.app domain is verified in Resend
FROM_EMAIL: str = os.getenv("FROM_EMAIL", "DownTime <onboarding@resend.dev>")
RECIPIENT_EMAIL: str = os.getenv("RECIPIENT_EMAIL", "ljm32901@gmail.com")

# ── Location ───────────────────────────────────────────────────────────────────
CITY: str = os.getenv("CITY", "Dallas")
STATE: str = os.getenv("STATE", "TX")
CITY_LAT: float = float(os.getenv("CITY_LAT", "32.7767"))  # Dallas city center
CITY_LON: float = float(os.getenv("CITY_LON", "-96.7970"))

# ── User profile ───────────────────────────────────────────────────────────────
USER_NAME: str = os.getenv("USER_NAME", "Luke")
USER_INTERESTS: list[str] = ["photography", "outdoor", "food", "arts", "festivals"]

# ── DownTime backend API (optional — used if not importing fetchers directly) ──
BACKEND_URL: str = os.getenv("BACKEND_URL", "")

# ── Source API keys (passed through to fetchers) ───────────────────────────────
TM_API_KEY: str = os.getenv("TM_API_KEY", "")
SG_CLIENT_ID: str = os.getenv("SG_CLIENT_ID", "")
SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")
OTM_API_KEY: str = os.getenv("OTM_API_KEY", "")

# ── Curation settings ──────────────────────────────────────────────────────────
TOP_N_EVENTS: int = int(os.getenv("TOP_N_EVENTS", "10"))
FETCH_DAYS_AHEAD: int = 4  # Friday–Sunday = ~3 days from Thursday
FETCH_PAGE_SIZE: int = 100
