"""
SerpAPI Google Events fetcher.

Endpoint: https://serpapi.com/search?engine=google_events
Auth: API key as query param (api_key=)
Rate limit: 250 searches/month on free tier — use weekly only
Docs: https://serpapi.com/google-events-api
"""
import hashlib
import logging
import re

import httpx

from config import SERPAPI_KEY
from models import Event

logger = logging.getLogger(__name__)

BASE_URL = "https://serpapi.com/search"

# Date filter chips for Google Events
DATE_FILTERS = {
    "today": "date:today",
    "tomorrow": "date:tomorrow",
    "this_week": "date:week",
    "next_week": "date:next_week",
    "this_month": "date:month",
}


def _make_id(title: str, date_info: str) -> str:
    raw = f"{title}|{date_info}"
    return f"ge_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _guess_category(title: str, description: str = "") -> str:
    """Guess category from event title and description text."""
    text = f"{title} {description}".lower()

    category_keywords = {
        "music": ["concert", "live music", "band", "dj", "orchestra", "symphony", "jazz", "hip hop", "rock", "festival music", "songwriter", "open mic"],
        "sports": ["game", "match", "tournament", "race", "marathon", "5k", "10k", "baseball", "basketball", "football", "soccer", "hockey", "tennis", "boxing", "wrestling"],
        "arts": ["art", "gallery", "exhibit", "museum", "theater", "theatre", "play", "musical", "ballet", "dance", "opera", "comedy", "stand-up", "standup", "improv"],
        "food": ["food", "wine", "beer", "tasting", "brunch", "dinner", "cooking", "chef", "culinary", "brewery", "distillery", "farmers market"],
        "outdoor": ["hike", "hiking", "trail", "park", "garden", "outdoor", "nature", "kayak", "bike", "cycling", "camping", "fishing"],
        "nightlife": ["club", "nightclub", "party", "dj set", "rave", "bar crawl", "happy hour", "lounge", "karaoke"],
        "film": ["film", "movie", "cinema", "screening", "documentary", "short film"],
        "festivals": ["festival", "fest ", "fair", "carnival", "celebration", "fiesta", "block party", "street festival"],
        "photography": ["photo", "photography", "camera", "photo walk"],
        "motorsports": ["racing", "drag race", "nascar", "formula", "motocross", "monster truck"],
    }

    for category, keywords in category_keywords.items():
        for kw in keywords:
            if kw in text:
                return category

    return "arts"


def _extract_tags(event: dict) -> list[str]:
    """Extract tags from Google Events data."""
    tags = []
    title = (event.get("title") or "").lower()

    tag_keywords = [
        "free", "outdoor", "live", "family", "kids", "virtual", "online",
        "workshop", "class", "tour", "meetup", "popup", "pop-up",
    ]
    for kw in tag_keywords:
        if kw in title:
            tags.append(kw)

    # Add venue type if available
    address_parts = event.get("address", [])
    if address_parts and len(address_parts) > 0:
        venue_name = address_parts[0].lower()
        venue_hints = ["park", "museum", "gallery", "theater", "stadium", "arena", "bar", "brewery", "garden"]
        for hint in venue_hints:
            if hint in venue_name:
                tags.append(hint)

    return list(set(tags))


def _parse_price(ticket_info: list) -> tuple[str, str]:
    """Parse price from ticket_info array."""
    if not ticket_info:
        return ("Unknown", "Check event link for pricing")

    prices = []
    sources = []
    for ticket in ticket_info:
        source = ticket.get("source", "")
        link = ticket.get("link", "")
        price_str = ticket.get("link_type", "") or ""

        # Try to extract price from the ticket data
        if source:
            sources.append(source)

        # SerpAPI sometimes includes price in different fields
        for field in ("price", "link_type"):
            val = ticket.get(field, "")
            if val and "$" in str(val):
                # Extract numeric price
                match = re.search(r"\$(\d+(?:\.\d{2})?)", str(val))
                if match:
                    prices.append(float(match.group(1)))

    if prices:
        if len(prices) == 1:
            return (f"${prices[0]:.0f}", f"Tickets from ${prices[0]:.0f}")
        min_p, max_p = min(prices), max(prices)
        if min_p == max_p:
            return (f"${min_p:.0f}", f"Tickets at ${min_p:.0f}")
        return (f"${min_p:.0f}–${max_p:.0f}", f"Tickets from ${min_p:.0f} to ${max_p:.0f}")

    if sources:
        return ("See link", f"Tickets via {', '.join(sources)}")

    return ("Unknown", "Check event link for pricing")


def _normalize_event(raw: dict, city: str, state: str) -> Event:
    """Convert a raw SerpAPI Google event to our Event model."""
    title = raw.get("title", "Untitled Event")

    # Address parsing — Google returns an array like ["Venue Name", "City, TX"]
    address_parts = raw.get("address", [])
    venue_name = address_parts[0] if len(address_parts) > 0 else ""
    address_str = address_parts[1] if len(address_parts) > 1 else ""
    full_address = ", ".join(address_parts[1:]) if len(address_parts) > 1 else ""

    # Date parsing
    date_obj = raw.get("date", {})
    start_date = date_obj.get("start_date", "")
    when = date_obj.get("when", "")
    time_info = when if when else start_date

    description = raw.get("description", "") or ""

    # Price
    ticket_info = raw.get("ticket_info", [])
    price_range, price_note = _parse_price(ticket_info)

    return Event(
        id=_make_id(title, str(date_obj)),
        title=title,
        description=description,
        category=_guess_category(title, description),
        scenario="",  # Assigned by scoring engine
        source="google",
        source_url=raw.get("link", ""),
        venue=venue_name,
        address=full_address,
        city=city,
        state=state,
        lat=0.0,  # Google Events doesn't provide coords
        lon=0.0,
        date_start=start_date if start_date else None,
        date_end=None,
        time_info=time_info,
        price_range=price_range,
        price_note=price_note,
        image_url=raw.get("thumbnail"),
        camera_worthy=False,
        camera_note=None,
        tags=_extract_tags(raw),
        score=0,
        is_featured=False,
    )


async def fetch_google_events(
    city: str,
    state: str,
    date_filter: str = "this_week",
) -> list[Event]:
    """
    Fetch events from Google via SerpAPI.

    IMPORTANT: This uses 1 API call per request out of 250/month free.
    Should only be called weekly per city, not daily.

    Params:
        city: City name
        state: State code
        date_filter: One of 'today', 'tomorrow', 'this_week', 'next_week', 'this_month'

    Returns:
        List of Event objects
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set — skipping Google Events fetch")
        return []

    q = f"events in {city}, {state}"
    htichips = DATE_FILTERS.get(date_filter, "date:week")

    params = {
        "engine": "google_events",
        "q": q,
        "hl": "en",
        "gl": "us",
        "api_key": SERPAPI_KEY,
        "htichips": htichips,
    }

    events: list[Event] = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(BASE_URL, params=params)

            if resp.status_code == 429:
                logger.warning("SerpAPI rate limit hit")
                return []
            resp.raise_for_status()

            data = resp.json()

            # Check for API errors
            if "error" in data:
                logger.error(f"SerpAPI error: {data['error']}")
                return []

            raw_events = data.get("events_results", [])

            for raw in raw_events:
                try:
                    events.append(_normalize_event(raw, city, state))
                except Exception as e:
                    logger.error(f"Error parsing Google event: {e}")
                    continue

    except httpx.HTTPStatusError as e:
        logger.error(f"SerpAPI HTTP error for {city}: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"SerpAPI request error for {city}: {e}")
    except Exception as e:
        logger.error(f"SerpAPI unexpected error for {city}: {e}")

    logger.info(f"Google Events: fetched {len(events)} events for {city}, {state}")
    return events
