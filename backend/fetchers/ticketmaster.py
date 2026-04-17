"""
Ticketmaster Discovery API fetcher.

Endpoint: https://app.ticketmaster.com/discovery/v2/events.json
Auth: API key as query param (apikey=)
Rate limit: 5,000 calls/day, 5 req/sec
Docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
"""
import hashlib
import logging
from datetime import datetime, timedelta

import httpx

from config import TM_API_KEY, FETCH_DAYS_AHEAD, FETCH_PAGE_SIZE
from models import Event

logger = logging.getLogger(__name__)

BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

# Map Ticketmaster segment/genre names to DownTime categories
TM_CATEGORY_MAP = {
    "music": "music",
    "sports": "sports",
    "arts & theatre": "arts",
    "arts": "arts",
    "theatre": "arts",
    "film": "film",
    "miscellaneous": "arts",
    "undefined": "arts",
}

TM_GENRE_CATEGORY_MAP = {
    "rock": "music",
    "pop": "music",
    "hip-hop/rap": "music",
    "r&b": "music",
    "country": "music",
    "alternative": "music",
    "classical": "music",
    "jazz": "music",
    "blues": "music",
    "electronic": "music",
    "latin": "music",
    "folk": "music",
    "metal": "music",
    "reggae": "music",
    "comedy": "arts",
    "dance": "arts",
    "magic & illusion": "arts",
    "circus & specialty acts": "arts",
    "theatre": "arts",
    "opera": "arts",
    "basketball": "sports",
    "football": "sports",
    "baseball": "sports",
    "hockey": "sports",
    "soccer": "sports",
    "tennis": "sports",
    "golf": "sports",
    "boxing": "sports",
    "wrestling": "sports",
    "motorsports/racing": "motorsports",
    "equestrian": "sports",
    "volleyball": "sports",
    "rugby": "sports",
    "martial arts": "sports",
    "fairs & festivals": "festivals",
    "festival": "festivals",
    "food & drink": "food",
    "family": "arts",
}


def _make_id(tm_id: str) -> str:
    return f"tm_{hashlib.md5(tm_id.encode()).hexdigest()[:12]}"


def _extract_category(event: dict) -> str:
    """Extract DownTime category from Ticketmaster classifications."""
    classifications = event.get("classifications", [])
    if not classifications:
        return "arts"

    c = classifications[0]

    # Check genre first (more specific)
    genre_name = c.get("genre", {}).get("name", "").lower()
    if genre_name in TM_GENRE_CATEGORY_MAP:
        return TM_GENRE_CATEGORY_MAP[genre_name]

    # Check sub-genre
    subgenre_name = c.get("subGenre", {}).get("name", "").lower()
    if subgenre_name in TM_GENRE_CATEGORY_MAP:
        return TM_GENRE_CATEGORY_MAP[subgenre_name]

    # Fall back to segment (broadest level)
    segment_name = c.get("segment", {}).get("name", "").lower()
    return TM_CATEGORY_MAP.get(segment_name, "arts")


def _extract_tags(event: dict) -> list[str]:
    """Extract tags from classifications and event data."""
    tags = []
    classifications = event.get("classifications", [])
    if classifications:
        c = classifications[0]
        for key in ("segment", "genre", "subGenre", "type", "subType"):
            name = c.get(key, {}).get("name", "")
            if name and name.lower() not in ("undefined", "other", ""):
                tags.append(name.lower())
    return list(set(tags))


def _extract_price_range(event: dict) -> tuple[str, str]:
    """Return (price_range, price_note) from priceRanges."""
    ranges = event.get("priceRanges", [])
    if not ranges:
        return ("Unknown", "Price not listed")

    r = ranges[0]
    price_min = r.get("min")
    price_max = r.get("max")
    currency = r.get("currency", "USD")

    if price_min is not None and price_max is not None:
        if price_min == 0 and price_max == 0:
            return ("Free", "Free event")
        if price_min == price_max:
            return (f"${price_min:.0f}", f"Tickets at ${price_min:.0f}")
        return (
            f"${price_min:.0f}–${price_max:.0f}",
            f"Tickets from ${price_min:.0f} to ${price_max:.0f} {currency}",
        )
    if price_min is not None:
        return (f"From ${price_min:.0f}", f"Starting at ${price_min:.0f}")
    if price_max is not None:
        return (f"Up to ${price_max:.0f}", f"Up to ${price_max:.0f}")

    return ("Unknown", "Price not listed")


def _extract_image(event: dict) -> str | None:
    """Pick the best image — prefer 16:9 ratio, larger sizes."""
    images = event.get("images", [])
    if not images:
        return None

    # Prefer 16_9 ratio with width >= 640
    for img in images:
        if img.get("ratio") == "16_9" and img.get("width", 0) >= 640:
            return img["url"]

    # Fallback: any 16_9
    for img in images:
        if img.get("ratio") == "16_9":
            return img["url"]

    # Fallback: largest image
    images_sorted = sorted(images, key=lambda x: x.get("width", 0), reverse=True)
    return images_sorted[0].get("url") if images_sorted else None


def _normalize_event(raw: dict, city_name: str, state_code: str) -> Event:
    """Convert a raw Ticketmaster event to our Event model."""
    venues = raw.get("_embedded", {}).get("venues", [{}])
    v = venues[0] if venues else {}

    dates = raw.get("dates", {})
    start = dates.get("start", {})
    end = dates.get("end", {})

    # Build time info string
    local_date = start.get("localDate", "")
    local_time = start.get("localTime", "")
    time_info = ""
    if local_date:
        time_info = local_date
    if local_time:
        try:
            t = datetime.strptime(local_time, "%H:%M:%S")
            time_info += f" at {t.strftime('%I:%M %p')}"
        except ValueError:
            time_info += f" at {local_time}"

    # Date status (TBD, TBA, etc.)
    if start.get("dateTBD"):
        time_info = "Date TBD"
    elif start.get("timeTBA"):
        time_info = f"{local_date} — Time TBA"

    price_range, price_note = _extract_price_range(raw)

    # Location
    lat = 0.0
    lon = 0.0
    try:
        loc = v.get("location", {})
        lat = float(loc.get("latitude", 0))
        lon = float(loc.get("longitude", 0))
    except (ValueError, TypeError):
        pass

    venue_city = v.get("city", {}).get("name", city_name)
    venue_state = v.get("state", {}).get("stateCode", state_code)

    return Event(
        id=_make_id(raw.get("id", "")),
        title=raw.get("name", "Untitled Event"),
        description=raw.get("info", "") or raw.get("pleaseNote", "") or "",
        category=_extract_category(raw),
        scenario="",  # Assigned by scoring engine
        source="ticketmaster",
        source_url=raw.get("url", ""),
        venue=v.get("name", ""),
        address=v.get("address", {}).get("line1", ""),
        city=venue_city,
        state=venue_state,
        lat=lat,
        lon=lon,
        date_start=start.get("dateTime") or start.get("localDate"),
        date_end=end.get("dateTime") or end.get("localDate"),
        time_info=time_info,
        price_range=price_range,
        price_note=price_note,
        image_url=_extract_image(raw),
        camera_worthy=False,  # Assigned by scoring engine
        camera_note=None,
        tags=_extract_tags(raw),
        score=0,  # Assigned by scoring engine
        is_featured=False,
    )


async def fetch_ticketmaster_events(
    city: str,
    state: str,
    lat: float | None = None,
    lon: float | None = None,
    days_ahead: int | None = None,
) -> list[Event]:
    """
    Fetch upcoming events from Ticketmaster Discovery API.

    Params:
        city: City name (e.g., "Austin")
        state: State code (e.g., "TX")
        lat/lon: Optional coordinates for geo-based search
        days_ahead: How many days ahead to search (default from config)

    Returns:
        List of Event objects
    """
    if not TM_API_KEY:
        logger.warning("TM_API_KEY not set — skipping Ticketmaster fetch")
        return []

    days = days_ahead or FETCH_DAYS_AHEAD
    now = datetime.utcnow()
    start_dt = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_dt = (now + timedelta(days=days)).strftime("%Y-%m-%dT23:59:59Z")

    params: dict = {
        "apikey": TM_API_KEY,
        "countryCode": "US",
        "size": min(FETCH_PAGE_SIZE, 200),
        "startDateTime": start_dt,
        "endDateTime": end_dt,
        "sort": "date,asc",
    }

    # Prefer city + stateCode; fall back to latlong
    if city:
        params["city"] = city
    if state:
        params["stateCode"] = state
    if lat and lon and not city:
        params["latlong"] = f"{lat},{lon}"

    events: list[Event] = []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Fetch up to 2 pages (200 events max) to stay within rate limits
            for page in range(2):
                params["page"] = page
                resp = await client.get(BASE_URL, params=params)

                if resp.status_code == 429:
                    logger.warning("Ticketmaster rate limit hit — backing off")
                    break
                resp.raise_for_status()

                data = resp.json()
                raw_events = data.get("_embedded", {}).get("events", [])
                if not raw_events:
                    break

                for raw in raw_events:
                    try:
                        events.append(_normalize_event(raw, city, state))
                    except Exception as e:
                        logger.error(f"Error parsing TM event: {e}")
                        continue

                # Check if there are more pages
                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 1)
                if page + 1 >= total_pages:
                    break

    except httpx.HTTPStatusError as e:
        logger.error(f"Ticketmaster HTTP error for {city}, {state}: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Ticketmaster request error for {city}, {state}: {e}")
    except Exception as e:
        logger.error(f"Ticketmaster unexpected error for {city}, {state}: {e}")

    logger.info(f"Ticketmaster: fetched {len(events)} events for {city}, {state}")
    return events
