"""
OpenTripMap API fetcher — POIs/attractions.

Endpoint: https://api.opentripmap.com/0.1/en/places/radius
Auth: API key as query param (apikey=)
Rate limit: 5,000/day, cacheable
Docs: https://dev.opentripmap.org
"""
import hashlib
import logging

import httpx

from config import OTM_API_KEY
from models import Event

logger = logging.getLogger(__name__)

BASE_URL = "https://api.opentripmap.com/0.1/en/places"

# OpenTripMap kinds → DownTime categories
OTM_CATEGORY_MAP = {
    "museums": "arts",
    "theatres_and_entertainments": "arts",
    "cultural": "arts",
    "historic": "arts",
    "architecture": "arts",
    "religion": "arts",
    "natural": "outdoor",
    "beaches": "outdoor",
    "gardens_and_parks": "outdoor",
    "water": "outdoor",
    "geological_formations": "outdoor",
    "mountain_peaks": "outdoor",
    "view_points": "outdoor",
    "sport": "sports",
    "amusements": "arts",
    "accomodations": "travel",
    "foods": "food",
    "shops": "arts",
    "transport": "travel",
    "industrial_facilities": "arts",
    "other": "arts",
}

# Kind → camera-worthiness mapping
CAMERA_WORTHY_KINDS = {
    "natural", "beaches", "gardens_and_parks", "view_points",
    "geological_formations", "mountain_peaks", "water",
    "architecture", "historic", "cultural", "museums",
}

CAMERA_NOTES = {
    "natural": "Capture the natural beauty — wide landscapes and macro details",
    "beaches": "Golden hour shots at the waterfront — bring a polarizer",
    "gardens_and_parks": "Lush greenery and walking paths — great for portraits",
    "view_points": "Panoramic vista — bring a wide-angle lens",
    "geological_formations": "Dramatic rock formations — play with scale",
    "mountain_peaks": "Epic summit views — arrive early for sunrise",
    "water": "Reflections and moving water — experiment with long exposure",
    "architecture": "Interesting lines and facades — shoot from low angles",
    "historic": "Rich textures and history — look for storytelling details",
    "cultural": "Cultural landmark — capture the atmosphere and crowds",
    "museums": "Interior architecture and exhibits — check flash rules",
}

# Kinds to request in bulk — covers the most interesting POI types
FETCH_KINDS = (
    "interesting_places,"
    "museums,"
    "theatres_and_entertainments,"
    "cultural,"
    "historic,"
    "architecture,"
    "natural,"
    "beaches,"
    "gardens_and_parks,"
    "view_points,"
    "sport,"
    "amusements"
)


def _make_id(xid: str) -> str:
    return f"otm_{hashlib.md5(xid.encode()).hexdigest()[:12]}"


def _primary_kind(kinds_str: str) -> str:
    """Get the primary (first) kind from a comma-separated kinds string."""
    if not kinds_str:
        return "other"
    parts = kinds_str.split(",")
    return parts[0].strip()


def _kinds_to_category(kinds_str: str) -> str:
    """Map OpenTripMap kinds to DownTime category."""
    if not kinds_str:
        return "arts"

    kinds = [k.strip() for k in kinds_str.split(",")]

    # Try each kind against our map
    for kind in kinds:
        if kind in OTM_CATEGORY_MAP:
            return OTM_CATEGORY_MAP[kind]

    return "arts"


def _is_camera_worthy(kinds_str: str) -> tuple[bool, str | None]:
    """Check if the POI is camera-worthy based on its kinds."""
    if not kinds_str:
        return False, None

    kinds = [k.strip() for k in kinds_str.split(",")]
    for kind in kinds:
        if kind in CAMERA_WORTHY_KINDS:
            note = CAMERA_NOTES.get(kind, "A visually interesting spot worth photographing")
            return True, note

    return False, None


def _extract_tags(kinds_str: str, name: str = "") -> list[str]:
    """Extract tags from kinds and name."""
    tags = []
    if kinds_str:
        tags = [k.strip().replace("_", " ") for k in kinds_str.split(",") if k.strip()]

    # Add some name-derived tags
    name_lower = name.lower()
    extra_tags = ["free", "outdoor", "historic", "park", "museum", "gallery", "trail"]
    for tag in extra_tags:
        if tag in name_lower and tag not in tags:
            tags.append(tag)

    return list(set(tags))[:10]  # Cap at 10 tags


def _rate_to_score_boost(rate: int) -> int:
    """Convert OpenTripMap rate (1-7) to a score boost."""
    # Rate 7 = UNESCO etc, rate 1 = minor
    return min(rate * 5, 35)  # Max 35 point boost


def _normalize_place(raw: dict, city: str, state: str, detail: dict | None = None) -> Event:
    """Convert a raw OpenTripMap place to our Event model."""
    name = raw.get("name", "") or ""
    if detail:
        name = detail.get("name", name) or name

    kinds_str = raw.get("kinds", "")
    point = raw.get("point", {})
    lat = point.get("lat", 0.0) or 0.0
    lon = point.get("lon", 0.0) or 0.0

    # Detail fields (if we fetched them)
    description = ""
    address_str = ""
    image_url = None
    source_url = ""

    if detail:
        # Wikipedia extract
        wiki = detail.get("wikipedia_extracts", {})
        description = wiki.get("text", "") or ""
        if not description:
            description = detail.get("info", {}).get("descr", "") or ""

        # Address
        addr = detail.get("address", {})
        parts = [
            addr.get("road", ""),
            addr.get("house_number", ""),
        ]
        city_name = addr.get("city", "") or addr.get("town", "") or addr.get("village", "")
        state_name = addr.get("state", "")
        address_str = ", ".join(p for p in parts if p)
        if city_name and city_name.lower() != city.lower():
            address_str += f", {city_name}"

        # Image
        image_url = detail.get("preview", {}).get("source")
        if not image_url:
            image_url = detail.get("image")

        # URL
        source_url = detail.get("otm", "") or detail.get("url", "") or ""
        if not source_url and detail.get("wikipedia"):
            source_url = detail["wikipedia"]

    camera_worthy, camera_note = _is_camera_worthy(kinds_str)

    return Event(
        id=_make_id(raw.get("xid", "")),
        title=name if name else "Unnamed Attraction",
        description=description[:500],  # Truncate long descriptions
        category=_kinds_to_category(kinds_str),
        scenario="",  # Assigned by scoring engine
        source="opentripmap",
        source_url=source_url,
        venue=name,
        address=address_str,
        city=city,
        state=state,
        lat=lat,
        lon=lon,
        date_start=None,  # POIs don't have specific dates
        date_end=None,
        time_info="Open attraction — check hours",
        price_range="Varies",
        price_note="Check venue for admission details",
        image_url=image_url,
        camera_worthy=camera_worthy,
        camera_note=camera_note,
        tags=_extract_tags(kinds_str, name),
        score=0,  # Will be set by scoring engine
        is_featured=False,
    )


async def fetch_opentripmap_places(
    city: str,
    state: str,
    lat: float,
    lon: float,
    radius: int = 30000,
    limit: int = 50,
    fetch_details: bool = True,
) -> list[Event]:
    """
    Fetch POIs/attractions from OpenTripMap.

    Params:
        city: City name
        state: State code
        lat, lon: Center coordinates
        radius: Search radius in meters (default 30km)
        limit: Max results
        fetch_details: Whether to fetch detail endpoint for each place
            (uses 1 extra API call per place — set False to conserve quota)

    Returns:
        List of Event objects (treated as "always-on" attractions)
    """
    if not OTM_API_KEY:
        logger.warning("OTM_API_KEY not set — skipping OpenTripMap fetch")
        return []

    params = {
        "apikey": OTM_API_KEY,
        "radius": radius,
        "lon": lon,
        "lat": lat,
        "kinds": FETCH_KINDS,
        "format": "json",
        "limit": limit,
        "rate": "2",  # Min rating 2 to filter low-quality POIs
    }

    events: list[Event] = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Step 1: Get list of places
            resp = await client.get(f"{BASE_URL}/radius", params=params)

            if resp.status_code == 429:
                logger.warning("OpenTripMap rate limit hit")
                return []
            resp.raise_for_status()

            places = resp.json()
            if not isinstance(places, list):
                logger.warning(f"OpenTripMap returned unexpected format: {type(places)}")
                return []

            # Filter out places without names
            places = [p for p in places if p.get("name")]

            logger.info(f"OpenTripMap: found {len(places)} places near {city}")

            # Step 2: Optionally fetch details for top-rated places
            for place in places:
                detail = None
                if fetch_details and place.get("xid"):
                    try:
                        detail_resp = await client.get(
                            f"{BASE_URL}/xid/{place['xid']}",
                            params={"apikey": OTM_API_KEY},
                        )
                        if detail_resp.status_code == 200:
                            detail = detail_resp.json()
                    except Exception as e:
                        logger.debug(f"Failed to fetch OTM detail for {place.get('xid')}: {e}")

                try:
                    events.append(_normalize_place(place, city, state, detail))
                except Exception as e:
                    logger.error(f"Error parsing OTM place: {e}")
                    continue

    except httpx.HTTPStatusError as e:
        logger.error(f"OpenTripMap HTTP error for {city}: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"OpenTripMap request error for {city}: {e}")
    except Exception as e:
        logger.error(f"OpenTripMap unexpected error for {city}: {e}")

    logger.info(f"OpenTripMap: processed {len(events)} places for {city}, {state}")
    return events
