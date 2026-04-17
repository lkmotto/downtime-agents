"""
Configuration for DownTime Event Collection Agent.

Loads settings from environment variables / .env file.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Backend connection
# ──────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "")           # e.g. https://api.getdowntime.com
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")   # optional bearer token

# ──────────────────────────────────────────────
# Data output
# ──────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# ──────────────────────────────────────────────
# Fetch settings
# ──────────────────────────────────────────────
FETCH_DAYS_AHEAD = int(os.getenv("FETCH_DAYS_AHEAD", "14"))
MAX_EVENTS_PER_CITY = int(os.getenv("MAX_EVENTS_PER_CITY", "100"))
MAX_REQUESTS_PER_SITE = int(os.getenv("MAX_REQUESTS_PER_SITE", "30"))

# ──────────────────────────────────────────────
# Anti-detection settings
# ──────────────────────────────────────────────
# Delay range (seconds) between page loads
DELAY_MIN = float(os.getenv("DELAY_MIN", "2.0"))
DELAY_MAX = float(os.getenv("DELAY_MAX", "8.0"))

# Viewport pool — randomised per request
VIEWPORT_POOL = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 1920, "height": 1080},
    {"width": 1600, "height": 900},
    {"width": 1280, "height": 1024},
    {"width": 1024, "height": 768},
    {"width": 1400, "height": 900},
    {"width": 1680, "height": 1050},
]

# Real browser user-agent pool (Chrome on various OS)
USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# Playwright browser args to reduce bot fingerprint
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--hide-scrollbars",
    "--mute-audio",
    "--disable-background-networking",
]

# ──────────────────────────────────────────────
# Cities — top 50 US cities with coordinates
# ──────────────────────────────────────────────
@dataclass
class CityConfig:
    name: str
    state: str
    lat: float
    lon: float
    # allevents.in uses slug format: "new-york" etc.
    slug: str = field(default="")

    def __post_init__(self):
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "-")


CITIES: list[CityConfig] = [
    CityConfig("New York", "NY", 40.7128, -74.0060, slug="new-york"),
    CityConfig("Los Angeles", "CA", 34.0522, -118.2437, slug="los-angeles"),
    CityConfig("Chicago", "IL", 41.8781, -87.6298, slug="chicago"),
    CityConfig("Houston", "TX", 29.7604, -95.3698, slug="houston"),
    CityConfig("Phoenix", "AZ", 33.4484, -112.0740, slug="phoenix"),
    CityConfig("Philadelphia", "PA", 39.9526, -75.1652, slug="philadelphia"),
    CityConfig("San Antonio", "TX", 29.4241, -98.4936, slug="san-antonio"),
    CityConfig("San Diego", "CA", 32.7157, -117.1611, slug="san-diego"),
    CityConfig("Dallas", "TX", 32.7767, -96.7970, slug="dallas"),
    CityConfig("Austin", "TX", 30.2672, -97.7431, slug="austin"),
    CityConfig("Jacksonville", "FL", 30.3322, -81.6557, slug="jacksonville"),
    CityConfig("Fort Worth", "TX", 32.7555, -97.3308, slug="fort-worth"),
    CityConfig("San Jose", "CA", 37.3382, -121.8863, slug="san-jose"),
    CityConfig("Columbus", "OH", 39.9612, -82.9988, slug="columbus"),
    CityConfig("Charlotte", "NC", 35.2271, -80.8431, slug="charlotte"),
    CityConfig("Indianapolis", "IN", 39.7684, -86.1581, slug="indianapolis"),
    CityConfig("San Francisco", "CA", 37.7749, -122.4194, slug="san-francisco"),
    CityConfig("Seattle", "WA", 47.6062, -122.3321, slug="seattle"),
    CityConfig("Denver", "CO", 39.7392, -104.9903, slug="denver"),
    CityConfig("Washington", "DC", 38.9072, -77.0369, slug="washington-dc"),
    CityConfig("Nashville", "TN", 36.1627, -86.7816, slug="nashville"),
    CityConfig("Oklahoma City", "OK", 35.4676, -97.5164, slug="oklahoma-city"),
    CityConfig("El Paso", "TX", 31.7619, -106.4850, slug="el-paso"),
    CityConfig("Boston", "MA", 42.3601, -71.0589, slug="boston"),
    CityConfig("Portland", "OR", 45.5152, -122.6784, slug="portland"),
    CityConfig("Las Vegas", "NV", 36.1699, -115.1398, slug="las-vegas"),
    CityConfig("Memphis", "TN", 35.1495, -90.0490, slug="memphis"),
    CityConfig("Louisville", "KY", 38.2527, -85.7585, slug="louisville"),
    CityConfig("Baltimore", "MD", 39.2904, -76.6122, slug="baltimore"),
    CityConfig("Milwaukee", "WI", 43.0389, -87.9065, slug="milwaukee"),
    CityConfig("Albuquerque", "NM", 35.0844, -106.6504, slug="albuquerque"),
    CityConfig("Tucson", "AZ", 32.2226, -110.9747, slug="tucson"),
    CityConfig("Fresno", "CA", 36.7378, -119.7871, slug="fresno"),
    CityConfig("Sacramento", "CA", 38.5816, -121.4944, slug="sacramento"),
    CityConfig("Mesa", "AZ", 33.4152, -111.8315, slug="mesa"),
    CityConfig("Kansas City", "MO", 39.0997, -94.5786, slug="kansas-city"),
    CityConfig("Atlanta", "GA", 33.7490, -84.3880, slug="atlanta"),
    CityConfig("Omaha", "NE", 41.2565, -95.9345, slug="omaha"),
    CityConfig("Colorado Springs", "CO", 38.8339, -104.8214, slug="colorado-springs"),
    CityConfig("Raleigh", "NC", 35.7796, -78.6382, slug="raleigh"),
    CityConfig("Long Beach", "CA", 33.7701, -118.1937, slug="long-beach"),
    CityConfig("Virginia Beach", "VA", 36.8529, -75.9780, slug="virginia-beach"),
    CityConfig("Miami", "FL", 25.7617, -80.1918, slug="miami"),
    CityConfig("Oakland", "CA", 37.8044, -122.2712, slug="oakland"),
    CityConfig("Minneapolis", "MN", 44.9778, -93.2650, slug="minneapolis"),
    CityConfig("Tampa", "FL", 27.9506, -82.4572, slug="tampa"),
    CityConfig("Tulsa", "OK", 36.1540, -95.9928, slug="tulsa"),
    CityConfig("Arlington", "TX", 32.7357, -97.1081, slug="arlington"),
    CityConfig("New Orleans", "LA", 29.9511, -90.0715, slug="new-orleans"),
    CityConfig("Pittsburgh", "PA", 40.4406, -79.9959, slug="pittsburgh"),
]


def get_city(name: str, state: str | None = None) -> CityConfig | None:
    """Look up a city by name and optional state code."""
    name_lower = name.lower()
    for city in CITIES:
        if city.name.lower() == name_lower:
            if state is None or city.state.upper() == state.upper():
                return city
    return None
