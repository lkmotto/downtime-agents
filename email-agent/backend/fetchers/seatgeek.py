"""
SeatGeek API fetcher.

Endpoint: https://api.seatgeek.com/2/events
Auth: client_id query param
Rate limit: No published cap (reasonable use)
Docs: https://platform.seatgeek.com
"""
import hashlib
import logging
from datetime import datetime, timedelta

import httpx

from config import SG_CLIENT_ID, FETCH_DAYS_AHEAD, FETCH_PAGE_SIZE
from models import Event

logger = logging.getLogger(__name__)

BASE_URL = "https://api.seatgeek.com/2/events"

# Map SeatGeek event types to DownTime categories
SG_CATEGORY_MAP = {
    "concert": "music",
    "concerts": "music",
    "music_festival": "festivals",
    "nba": "sports",
    "nfl": "sports",
    "mlb": "sports",
    "nhl": "sports",
    "ncaa_football": "sports",
    "ncaa_basketball": "sports",
    "ncaa_baseball": "sports",
    "ncaa_hockey": "sports",
    "ncaa_womens_basketball": "sports",
    "mls": "sports",
    "soccer": "sports",
    "tennis": "sports",
    "golf": "sports",
    "boxing": "sports",
    "mma": "sports",
    "wrestling": "sports",
    "racing": "motorsports",
    "nascar": "motorsports",
    "monster_truck": "motorsports",
    "horse_racing": "sports",
    "rodeo": "sports",
    "auto_racing": "motorsports",
    "theater": "arts",
    "broadway_tickets_national": "arts",
    "comedy": "arts",
    "dance_performance_tour": "arts",
    "classical": "music",
    "classical_orchestral_instrumental": "music",
    "opera": "arts",
    "literary": "arts",
    "circus": "arts",
    "family": "arts",
    "film": "film",
    "food": "food",
    "festival": "festivals",
    "minor_league_baseball": "sports",
    "minor_league_hockey": "sports",
    "pga": "sports",
    "lpga": "sports",
    "wnba": "sports",
    "animal_sports": "sports",
}


def _make_id(sg_id: str | int) -> str:
    return f"sg_{hashlib.md5(str(sg_id).encode()).hexdigest()[:12]}"


def _extract_category(event: dict) -> str:
    """Map SeatGeek type to DownTime category."""
    sg_type = (event.get("type") or "").lower()
    if sg_type in SG_CATEGORY_MAP:
        return SG_CATEGORY_MAP[sg_type]

    # Check taxonomies for more detail
    taxonomies = event.get("taxonomies", [])
    for tax in taxonomies:
        tax_name = (tax.get("name") or "").lower()
        if tax_name in SG_CATEGORY_MAP:
            return SG_CATEGORY_MAP[tax_name]

    # Check parent taxonomy
    for tax in taxonomies:
        parent = tax.get("parent_id")
        if parent:
            # parent_id 1000000 = concert, 2000000 = sports, 3000000 = theater
            if parent == 1000000:
                return "music"
            elif parent == 2000000:
                return "sports"
            elif parent == 3000000:
                return "arts"

    return "arts"


def _extract_tags(event: dict) -> list[str]:
    """Extract tags from SeatGeek event data."""
    tags = []
    sg_type = event.get("type", "")
    if sg_type:
        tags.append(sg_type.lower().replace("_", " "))

    taxonomies = event.get("taxonomies", [])
    for tax in taxonomies:
        name = tax.get("name", "")
        if name:
            tags.append(name.lower())

    performers = event.get("performers", [])
    for p in performers:
        p_type = p.get("type", "")
        if p_type:
            tags.append(p_type.lower())
        # Add genres from performer
        genres = p.get("genres", [])
        for g in genres:
            slug = g.get("slug", "")
            if slug:
                tags.append(slug.replace("-", " "))

    return list(set(tags))


def _extract_price(event: dict) -> tuple[str, str]:
    """Extract price range from SeatGeek stats."""
    stats = event.get("stats", {})
    lowest = stats.get("lowest_price")
    highest = stats.get("highest_price")
    avg = stats.get("average_price")

    if lowest is not None and highest is not None:
        if lowest == 0 and highest == 0:
            return ("Free", "Free event")
        if lowest == highest:
            return (f"${lowest:.0f}", f"Tickets at ${lowest:.0f}")
        return (
            f"${lowest:.0f}–${highest:.0f}",
            f"From ${lowest:.0f} to ${highest:.0f}",
        )
    if lowest is not None:
        return (f"From ${lowest:.0f}", f"Starting at ${lowest:.0f}")
    if avg is not None:
        return (f"~${avg:.0f}", f"Average ticket price ${avg:.0f}")

    return ("Unknown", "Price not listed — check source")


def _extract_image(event: dict) -> str | None:
    """Pick the best performer image."""
    performers = event.get("performers", [])
    if not performers:
        return None

    # Prefer the primary performer's image
    primary = performers[0]

    # Try images dict first (has multiple sizes)
    images = primary.get("images", {})
    if images:
        # Prefer huge > banner > block > etc.
        for key in ("huge", "banner", "block", "image"):
            if key in images and images[key]:
                return images[key]

    # Fall back to top-level image
    return primary.get("image")


def _normalize_event(raw: dict) -> Event:
    """Convert a raw SeatGeek event to our Event model."""
    venue = raw.get("venue", {})

    # Parse datetime
    dt_local = raw.get("datetime_local", "")
    date_start = dt_local if dt_local else None
    date_end = raw.get("datetime_local_end") or None

    # Build time info
    time_info = ""
    if dt_local:
        try:
            dt = datetime.fromisoformat(dt_local)
            time_info = dt.strftime("%Y-%m-%d at %I:%M %p")
        except ValueError:
            time_info = dt_local

    if raw.get("time_tbd"):
        date_part = dt_local[:10] if dt_local else ""
        time_info = f"{date_part} — Time TBD"
    if raw.get("date_tbd"):
        time_info = "Date TBD"

    price_range, price_note = _extract_price(raw)

    # Location
    lat = venue.get("location", {}).get("lat", 0.0) or 0.0
    lon = venue.get("location", {}).get("lon", 0.0) or 0.0

    return Event(
        id=_make_id(raw.get("id", "")),
        title=raw.get("title") or raw.get("short_title") or "Untitled Event",
        description=raw.get("description", "") or "",
        category=_extract_category(raw),
        scenario="",  # Assigned by scoring engine
        source="seatgeek",
        source_url=raw.get("url", ""),
        venue=venue.get("name", ""),
        address=venue.get("address", ""),
        city=venue.get("city", ""),
        state=venue.get("state", ""),
        lat=lat,
        lon=lon,
        date_start=date_start,
        date_end=date_end,
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


async def fetch_seatgeek_events(
    city: str,
    state: str,
    lat: float | None = None,
    lon: float | None = None,
    days_ahead: int | None = None,
) -> list[Event]:
    """
    Fetch upcoming events from SeatGeek.

    Params:
        city: City name
        state: State code
        lat/lon: Optional coordinates for geo search (range=30mi)
        days_ahead: Days ahead filter

    Returns:
        List of Event objects
    """
    if not SG_CLIENT_ID:
        logger.warning("SG_CLIENT_ID not set — skipping SeatGeek fetch")
        return []

    days = days_ahead or FETCH_DAYS_AHEAD
    now = datetime.utcnow()
    gte = now.strftime("%Y-%m-%dT%H:%M:%S")
    lte = (now + timedelta(days=days)).strftime("%Y-%m-%dT23:59:59")

    params: dict = {
        "client_id": SG_CLIENT_ID,
        "per_page": min(FETCH_PAGE_SIZE, 100),
        "sort": "datetime_local.asc",
        "datetime_utc.gte": gte,
        "datetime_utc.lte": lte,
    }

    if lat and lon:
        params["lat"] = lat
        params["lon"] = lon
        params["range"] = "30mi"
    else:
        params["venue.city"] = city
        if state:
            params["venue.state_code"] = state

    events: list[Event] = []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(BASE_URL, params=params)

            if resp.status_code == 429:
                logger.warning("SeatGeek rate limit hit — backing off")
                return []
            resp.raise_for_status()

            data = resp.json()
            raw_events = data.get("events", [])

            for raw in raw_events:
                try:
                    events.append(_normalize_event(raw))
                except Exception as e:
                    logger.error(f"Error parsing SeatGeek event: {e}")
                    continue

    except httpx.HTTPStatusError as e:
        logger.error(f"SeatGeek HTTP error for {city}, {state}: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"SeatGeek request error for {city}, {state}: {e}")
    except Exception as e:
        logger.error(f"SeatGeek unexpected error for {city}, {state}: {e}")

    logger.info(f"SeatGeek: fetched {len(events)} events for {city}, {state}")
    return events
