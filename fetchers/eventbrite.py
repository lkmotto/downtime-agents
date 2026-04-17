"""
Eventbrite API Fetcher for DownTime Event Collection Agent.

Uses the Eventbrite v3 REST API to fetch public events by location.
API docs: https://www.eventbrite.com/platform/api

Requires EVENTBRITE_TOKEN env var (OAuth private token).
"""
import os
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EVENTBRITE_TOKEN = os.getenv("EVENTBRITE_TOKEN", "")
BASE_URL = "https://www.eventbriteapi.com/v3"

# Eventbrite category IDs (subset we care about)
CATEGORY_MAP = {
    "103": "Music",
    "105": "Performing & Visual Arts",
    "104": "Film, Media & Entertainment",
    "110": "Food & Drink",
    "113": "Community & Culture",
    "109": "Travel & Outdoor",
    "108": "Sports & Fitness",
    "107": "Health & Wellness",
    "115": "Family & Education",
    "199": "Other",
}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {EVENTBRITE_TOKEN}",
        "Content-Type": "application/json",
    }


def _parse_event(raw: dict) -> Optional[dict]:
    """Parse a raw Eventbrite event object into our standard Event dict."""
    try:
        name = raw.get("name", {}).get("text", "").strip()
        if not name:
            return None

        description = raw.get("description", {}).get("text", "") or ""
        summary = raw.get("summary", "") or ""

        # Dates
        start_obj = raw.get("start", {})
        end_obj = raw.get("end", {})
        start_local = start_obj.get("local", "")
        end_local = end_obj.get("local", "")
        start_utc = start_obj.get("utc", "")

        # Venue
        venue = raw.get("venue", {})
        venue_name = ""
        address_str = ""
        lat = None
        lon = None
        if venue:
            venue_name = venue.get("name", "") or ""
            addr = venue.get("address", {})
            address_str = addr.get("localized_address_display", "") or ""
            lat = float(addr.get("latitude", 0)) or None
            lon = float(addr.get("longitude", 0)) or None

        # Category
        cat_id = raw.get("category_id", "")
        category = CATEGORY_MAP.get(cat_id, raw.get("format", {}).get("name", "Event"))

        # Image
        logo = raw.get("logo", {})
        image_url = ""
        if logo:
            image_url = logo.get("url", "") or ""

        # Price
        is_free = raw.get("is_free", False)
        price_str = "Free" if is_free else ""

        # URL
        url = raw.get("url", "")

        return {
            "title": name,
            "description": (summary or description[:500]).strip(),
            "start_datetime": start_local,
            "end_datetime": end_local,
            "start_utc": start_utc,
            "venue": venue_name,
            "address": address_str,
            "latitude": lat,
            "longitude": lon,
            "category": category,
            "image_url": image_url,
            "price": price_str,
            "is_free": is_free,
            "url": url,
            "source": "eventbrite",
            "source_id": raw.get("id", ""),
        }
    except Exception as e:
        logger.warning(f"Failed to parse Eventbrite event: {e}")
        return None


async def fetch_eventbrite_events(
    lat: float,
    lon: float,
    radius_miles: int = 25,
    days_ahead: int = 14,
    max_events: int = 200,
) -> list[dict]:
    """
    Fetch upcoming events near a location from Eventbrite API.

    Args:
        lat: Latitude of search center
        lon: Longitude of search center
        radius_miles: Search radius in miles
        days_ahead: How many days ahead to search
        max_events: Maximum events to return

    Returns:
        List of event dicts in standard DownTime format
    """
    if not EVENTBRITE_TOKEN:
        logger.warning("EVENTBRITE_TOKEN not set — skipping Eventbrite fetch")
        return []

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days_ahead)

    params = {
        "location.latitude": str(lat),
        "location.longitude": str(lon),
        "location.within": f"{radius_miles}mi",
        "start_date.range_start": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_date.range_end": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sort_by": "best",
        "expand": "venue,category,format",
        "page_size": 50,
    }

    events: list[dict] = []
    page = 1
    max_pages = math.ceil(max_events / 50)

    async with httpx.AsyncClient(timeout=30) as client:
        while page <= max_pages and len(events) < max_events:
            params["page"] = str(page)
            try:
                resp = await client.get(
                    f"{BASE_URL}/events/search/",
                    params=params,
                    headers=_headers(),
                )

                if resp.status_code == 401:
                    logger.error("Eventbrite auth failed — check EVENTBRITE_TOKEN")
                    break
                if resp.status_code == 429:
                    logger.warning("Eventbrite rate limit hit — stopping pagination")
                    break
                if resp.status_code != 200:
                    logger.warning(f"Eventbrite API error {resp.status_code}: {resp.text[:200]}")
                    break

                data = resp.json()
                raw_events = data.get("events", [])

                for raw in raw_events:
                    parsed = _parse_event(raw)
                    if parsed:
                        events.append(parsed)

                # Check pagination
                pagination = data.get("pagination", {})
                has_more = pagination.get("has_more_items", False)
                if not has_more:
                    break

                page += 1

            except httpx.TimeoutException:
                logger.warning(f"Eventbrite timeout on page {page}")
                break
            except Exception as e:
                logger.error(f"Eventbrite fetch error: {e}")
                break

    logger.info(f"Eventbrite: fetched {len(events)} events near ({lat}, {lon})")
    return events[:max_events]


# Synchronous wrapper for use in non-async contexts
def fetch_eventbrite_events_sync(
    lat: float,
    lon: float,
    radius_miles: int = 25,
    days_ahead: int = 14,
    max_events: int = 200,
) -> list[dict]:
    """Synchronous wrapper around fetch_eventbrite_events."""
    import asyncio
    return asyncio.run(fetch_eventbrite_events(lat, lon, radius_miles, days_ahead, max_events))
