"""
Event Curator for the DownTime Weekend Email Digest.

Fetches events for Dallas-Fort Worth this weekend (Friday–Sunday),
scores them, filters the top N, and groups them into email-ready buckets.

Imports fetchers and scoring engine from the downtime-backend package
(installed as a pip dependency) instead of bundling a copy.
"""
import sentry_init  # noqa: E402,F401

import asyncio
import logging
import os
import importlib.util
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Load agent models ─────────────────────────────────────────────────────────
import models as _agent_models_mod

Event = _agent_models_mod.Event
CuratedWeekend = _agent_models_mod.CuratedWeekend
CATEGORY_BUCKET_MAP = _agent_models_mod.CATEGORY_BUCKET_MAP
CATEGORY_FALLBACK_MAP = _agent_models_mod.CATEGORY_FALLBACK_MAP
EMAIL_CATEGORIES = _agent_models_mod.EMAIL_CATEGORIES

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Backend imports (from downtime-backend package, installed as a dependency) ─
import downtime_backend.config as backend_config

# Monkey-patch backend config keys from our agent env vars so fetchers pick them up
_agent_cfg_spec = importlib.util.spec_from_file_location(
    "agent_config_raw", os.path.join(_AGENT_DIR, "config.py")
)
_agent_config_raw = importlib.util.module_from_spec(_agent_cfg_spec)  # type: ignore
_agent_cfg_spec.loader.exec_module(_agent_config_raw)  # type: ignore

backend_config.TM_API_KEY = _agent_config_raw.TM_API_KEY
backend_config.SG_CLIENT_ID = _agent_config_raw.SG_CLIENT_ID
backend_config.SERPAPI_KEY = _agent_config_raw.SERPAPI_KEY
backend_config.OTM_API_KEY = _agent_config_raw.OTM_API_KEY
backend_config.FETCH_DAYS_AHEAD = _agent_config_raw.FETCH_DAYS_AHEAD
backend_config.FETCH_PAGE_SIZE = _agent_config_raw.FETCH_PAGE_SIZE

from downtime_backend.fetchers.ticketmaster import fetch_ticketmaster_events
from downtime_backend.fetchers.seatgeek import fetch_seatgeek_events
from downtime_backend.fetchers.serpapi_google import fetch_google_events
from downtime_backend.fetchers.opentripmap import fetch_opentripmap_places
from downtime_backend.scoring import score_events
from downtime_backend.models import Event as BackendEvent

logger = logging.getLogger(__name__)


# ── Why-go copy generator ─────────────────────────────────────────────────────

WHY_GO_TEMPLATES: dict[str, list[str]] = {
    "Date Night": [
        "A perfect excuse to dress up and make a night of it — great energy and ambiance.",
        "One of those experiences that actually makes for a memorable evening out.",
        "Great atmosphere and a shared experience you'll both be talking about after.",
    ],
    "Adventure / Outdoors": [
        "Get outside and break your routine — this one's worth blocking the morning for.",
        "Scenic, active, and a solid excuse to bring the camera gear.",
        "The kind of outing that makes the weekend feel like an actual adventure.",
    ],
    "Food & Drink": [
        "Worth the drive — the food is the feature, not just the fuel.",
        "A solid option if you're GF/DF and tired of guessing what's safe to eat.",
        "Locally loved and the kind of spot you'll want to return to.",
    ],
    "Arts & Culture": [
        "More engaging than a scroll session — and great for the 'gram with good glass.",
        "The kind of thing you'll wish you hadn't skipped.",
        "Visually rich environment — the Lumix will love this one.",
    ],
    "Free Things": [
        "Zero-cost, high-value — the best kind of weekend discovery.",
        "Free to attend and genuinely worth your time.",
        "No ticket required — just show up and explore.",
    ],
}

CAMERA_WHY_GO_SUFFIX: dict[str, str] = {
    "outdoor": " Bring the drone — wide-open skies here.",
    "festivals": " Prime conditions for crowd + color photography.",
    "arts": " The S5IIX will be right at home with the lighting inside.",
    "photography": " Meta opportunity: other shooters, great feedback loop.",
    "food": " Overhead flat-lays and ambient shots are easy wins here.",
    "music": " Low-light stage performance — perfect for testing high ISO limits.",
}


def _generate_why_go(event: Event) -> str:
    """Generate a 1-2 sentence 'why go' blurb for an event."""
    bucket = event.email_category or "Free Things"
    templates = WHY_GO_TEMPLATES.get(bucket, WHY_GO_TEMPLATES["Free Things"])

    # Pick template based on event score for variety
    idx = event.score % len(templates)
    why = templates[idx]

    # Append camera-specific note if camera worthy
    if event.camera_worthy and event.camera_note:
        why += f" {event.camera_note}."
    elif event.camera_worthy and event.category in CAMERA_WHY_GO_SUFFIX:
        why += CAMERA_WHY_GO_SUFFIX[event.category]

    return why


# ── Bucket assignment ──────────────────────────────────────────────────────────

def _assign_email_category(event: Event) -> str:
    """Assign an email display category to an event."""
    # Special case: free events that score below threshold go to Free Things
    price_lower = event.price_range.lower()
    is_free = price_lower in ("free", "$0", "0")

    if is_free:
        return "Free Things"

    # Try exact (category, scenario) match
    key = (event.category, event.scenario)
    if key in CATEGORY_BUCKET_MAP:
        return CATEGORY_BUCKET_MAP[key]

    # Fallback by category only
    return CATEGORY_FALLBACK_MAP.get(event.category, "Arts & Culture")


# ── Deduplication (mirrored from backend) ─────────────────────────────────────

def _deduplicate(events: list[BackendEvent]) -> list[BackendEvent]:
    seen: dict[str, BackendEvent] = {}
    priority = {"ticketmaster": 4, "seatgeek": 3, "google": 2, "opentripmap": 1}
    for event in events:
        title_norm = event.title.lower().strip()[:50]
        date_norm = (event.date_start or "")[:10]
        venue_norm = event.venue.lower().strip()[:30]
        key = f"{title_norm}|{date_norm}|{venue_norm}"
        if key not in seen or priority.get(event.source, 0) > priority.get(seen[key].source, 0):
            seen[key] = event
    return list(seen.values())


# ── Weekend date range ─────────────────────────────────────────────────────────

def _get_weekend_range() -> tuple[datetime, datetime, str, str]:
    """
    Returns (friday, sunday, friday_label, sunday_label) in local time (CT).

    When called on Thursday, this returns the upcoming Friday–Sunday.
    """
    now = datetime.now()
    # weekday(): Monday=0 … Sunday=6
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7  # If today IS Friday, get next Friday
    # From Thursday, days_until_friday == 1 → tomorrow = Friday ✓
    friday = now + timedelta(days=days_until_friday)
    sunday = friday + timedelta(days=2)

    friday_label = friday.strftime("%A, %B %-d")
    sunday_label = sunday.strftime("%A, %B %-d")

    return friday, sunday, friday_label, sunday_label


# ── Main curator ───────────────────────────────────────────────────────────────

async def _fetch_all(city: str, state: str, lat: float, lon: float) -> list[BackendEvent]:
    """Fetch from all sources concurrently, tolerating individual failures."""
    tasks = [
        fetch_ticketmaster_events(city=city, state=state, lat=lat, lon=lon),
        fetch_seatgeek_events(city=city, state=state, lat=lat, lon=lon),
        fetch_opentripmap_places(city=city, state=state, lat=lat, lon=lon, fetch_details=True),
        fetch_google_events(city=city, state=state, date_filter="this_week"),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    source_names = ["ticketmaster", "seatgeek", "opentripmap", "google"]

    all_events: list[BackendEvent] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Source '{source_names[i]}' failed: {result}")
        elif isinstance(result, list):
            logger.info(f"Source '{source_names[i]}': {len(result)} raw events")
            all_events.extend(result)

    return all_events


def _filter_weekend(events: list[BackendEvent], friday: datetime, sunday: datetime) -> list[BackendEvent]:
    """Keep only events that fall on Friday, Saturday, or Sunday."""
    friday_str = friday.strftime("%Y-%m-%d")
    sunday_str = sunday.strftime("%Y-%m-%d")

    weekend_events = []
    for e in events:
        date_str = (e.date_start or "")[:10]
        if not date_str:
            # No date — include anyway (OpenTripMap places, etc.)
            weekend_events.append(e)
            continue
        if friday_str <= date_str <= sunday_str:
            weekend_events.append(e)

    return weekend_events


def _backend_to_agent_event(be: BackendEvent) -> Event:
    """Convert a backend Event to our agent Event model."""
    return Event(
        id=be.id,
        title=be.title,
        description=be.description,
        category=be.category,
        scenario=be.scenario,
        source=be.source,
        source_url=be.source_url,
        venue=be.venue,
        address=be.address,
        city=be.city,
        state=be.state,
        lat=be.lat,
        lon=be.lon,
        date_start=be.date_start,
        date_end=be.date_end,
        time_info=be.time_info,
        price_range=be.price_range,
        price_note=be.price_note,
        image_url=be.image_url,
        camera_worthy=be.camera_worthy,
        camera_note=be.camera_note,
        tags=be.tags,
        score=be.score,
        is_featured=be.is_featured,
    )


async def curate_weekend(
    city: str,
    state: str,
    lat: float,
    lon: float,
    top_n: int = 10,
) -> CuratedWeekend:
    """
    Full curation pipeline:
      1. Fetch events from all sources
      2. Deduplicate
      3. Score with photography/user preferences weighted in
      4. Filter to this weekend (Fri–Sun)
      5. Pick top N by score
      6. Assign email categories + why-go copy
      7. Return CuratedWeekend

    Falls back gracefully — if weekend filter yields too few events,
    loosens to all upcoming events this week.
    """
    # Load agent config by file path (backend config shadows module-level import)
    import importlib.util as _ilu
    _cfg_spec = _ilu.spec_from_file_location("_agent_cfg", os.path.join(_AGENT_DIR, "config.py"))
    _agent_cfg = _ilu.module_from_spec(_cfg_spec)  # type: ignore
    _cfg_spec.loader.exec_module(_agent_cfg)  # type: ignore
    USER_INTERESTS = _agent_cfg.USER_INTERESTS

    friday, sunday, friday_label, sunday_label = _get_weekend_range()
    logger.info(f"Curating weekend: {friday_label} → {sunday_label}")

    # 1. Fetch
    raw = await _fetch_all(city, state, lat, lon)
    logger.info(f"Total raw events fetched: {len(raw)}")

    # 2. Deduplicate
    deduped = _deduplicate(raw)
    logger.info(f"After deduplication: {len(deduped)}")

    # 3. Score
    scored_backend = score_events(deduped, city_lat=lat, city_lon=lon, user_interests=USER_INTERESTS)
    logger.info(f"Scored {len(scored_backend)} events")

    # 4. Filter to weekend
    weekend_events = _filter_weekend(scored_backend, friday, sunday)
    logger.info(f"Weekend events (Fri–Sun): {len(weekend_events)}")

    # If very few weekend events, fall back to all fetched events
    if len(weekend_events) < 5:
        logger.warning(f"Only {len(weekend_events)} weekend events found — using all scored events")
        weekend_events = scored_backend

    # 5. Top N
    top_events_be = weekend_events[:top_n]

    # 6. Convert + enrich
    buckets: dict[str, list[Event]] = {cat: [] for cat in EMAIL_CATEGORIES}
    used_ids: set[str] = set()
    total_placed = 0

    for be in top_events_be:
        if be.id in used_ids:
            continue
        used_ids.add(be.id)

        agent_event = _backend_to_agent_event(be)
        agent_event.email_category = _assign_email_category(agent_event)
        agent_event.why_go = _generate_why_go(agent_event)
        bucket = agent_event.email_category

        buckets[bucket].append(agent_event)
        total_placed += 1

    # Ensure each bucket has at most 3 events; redistribute overflow to ensure variety
    # (simple: accept however they fall — top N events are curated by score)

    # Remove empty buckets to keep email clean
    non_empty = {k: v for k, v in buckets.items() if v}

    logger.info(f"Curated {total_placed} events into {len(non_empty)} categories")
    for cat, evts in non_empty.items():
        logger.info(f"  {cat}: {len(evts)} events")

    return CuratedWeekend(
        fetch_date=datetime.now(),
        weekend_start=friday_label,
        weekend_end=sunday_label,
        city_label="Dallas–Fort Worth",
        buckets=non_empty,
        total_fetched=len(raw),
        total_scored=len(scored_backend),
    )


if __name__ == "__main__":
    import sentry_sdk as _sentry_sdk
    try:
        import config

        logging.basicConfig(level=logging.INFO)
        result = asyncio.run(
            curate_weekend(
                city=config.CITY,
                state=config.STATE,
                lat=config.CITY_LAT,
                lon=config.CITY_LON,
                top_n=config.TOP_N_EVENTS,
            )
        )
        print(f"\nCurated weekend: {result.weekend_start} – {result.weekend_end}")
        for cat, evts in result.buckets.items():
            print(f"\n[{cat}]")
            for e in evts:
                print(f"  • {e.title} | Score: {e.score} | {e.price_range}")
    except Exception as _exc:
        _sentry_sdk.capture_exception(_exc)
        raise

