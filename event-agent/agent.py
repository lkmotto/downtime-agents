"""
DownTime Event Collection Agent — main runner.

Fetches events from AllEvents.in and Facebook Events for each configured city,
deduplicates them, scores them, saves results to /data/, and optionally POSTs
to the DownTime backend API.

Usage:
  python -m agent                   # run all configured cities
  python -m agent --cities Austin   # run specific city (comma-separated)
  python -m agent --dry-run         # fetch but don't POST to backend

Designed to run as a Northflank cron job: CMD ["python", "-m", "agent"]
"""

from __future__ import annotations
from motto_common.sentry_init import init_sentry  # was: import sentry_init
init_sentry(agent_name="downtime-event-agent")

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config import (
    CITIES,
    BACKEND_URL,
    BACKEND_API_KEY,
    DATA_DIR,
    MAX_EVENTS_PER_CITY,
    CityConfig,
)
from fetchers.allevents import fetch_allevents_events
from fetchers.facebook_events import fetch_facebook_events
from models import Event
from scoring import score_events

# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent")


# ──────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────


def _normalise_title(title: str) -> str:
    """Lowercase, strip punctuation/whitespace for fuzzy comparison."""
    import re

    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def _deduplicate(events: list[Event]) -> list[Event]:
    """
    Remove duplicate events using a combination of:
    1. Exact ID match
    2. Fuzzy title + date + venue match (normalised strings)

    An event is considered a duplicate when two of the three match exactly
    after normalisation.
    """
    seen_ids: set[str] = set()
    seen_combos: set[tuple[str, str, str]] = set()
    unique: list[Event] = []

    for ev in events:
        if ev.id in seen_ids:
            continue

        norm_title = _normalise_title(ev.title)
        date_key = (ev.date_start or ev.time_info or "")[:10]  # YYYY-MM-DD prefix
        venue_key = _normalise_title(ev.venue)[:30]

        # Check two-of-three fuzzy match
        is_dup = False
        combo_title_date = (norm_title, date_key, "")
        combo_title_venue = (norm_title, "", venue_key)
        combo_date_venue = ("", date_key, venue_key)

        for combo in (combo_title_date, combo_title_venue, combo_date_venue):
            if combo != ("", "", "") and combo in seen_combos:
                is_dup = True
                break

        if is_dup:
            logger.debug(f"Dedup: skipping '{ev.title}' from {ev.source}")
            continue

        seen_ids.add(ev.id)
        seen_combos.add((norm_title, date_key, venue_key))
        seen_combos.add(combo_title_date)
        seen_combos.add(combo_title_venue)
        seen_combos.add(combo_date_venue)
        unique.append(ev)

    return unique


# ──────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────


def _save_city_results(city: CityConfig, events: list[Event], run_ts: str) -> Path:
    """Save events for a city to a timestamped JSON file under DATA_DIR."""
    data_path = Path(DATA_DIR)
    data_path.mkdir(parents=True, exist_ok=True)

    city_slug = city.slug
    filename = f"{city_slug}_{run_ts}.json"
    output_path = data_path / filename

    payload = {
        "city": city.name,
        "state": city.state,
        "lat": city.lat,
        "lon": city.lon,
        "run_at": run_ts,
        "event_count": len(events),
        "events": [ev.model_dump(mode="json") for ev in events],
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    logger.info(f"Saved {len(events)} events → {output_path}")
    return output_path


def _save_latest_symlink(city: CityConfig, output_path: Path) -> None:
    """Maintain a 'latest' file per city for easy downstream consumption."""
    data_path = Path(DATA_DIR)
    latest_path = data_path / f"{city.slug}_latest.json"
    try:
        if latest_path.exists():
            latest_path.unlink()
        latest_path.symlink_to(output_path.name)
    except OSError:
        # Symlinks may not be supported in all environments — fall back to copy
        import shutil

        shutil.copy2(output_path, latest_path)


# ──────────────────────────────────────────────
# Backend API push
# ──────────────────────────────────────────────


async def _post_to_backend(city: CityConfig, events: list[Event]) -> bool:
    """
    POST scored events to the DownTime backend API.

    Endpoint: POST {BACKEND_URL}/internal/events
    Headers:  Authorization: Bearer {BACKEND_API_KEY}  (if set)
    Body:     { city, state, events: [...] }

    Returns True on success.
    """
    if not BACKEND_URL:
        return False

    endpoint = f"{BACKEND_URL.rstrip('/')}/internal/events"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if BACKEND_API_KEY:
        headers["Authorization"] = f"Bearer {BACKEND_API_KEY}"

    payload = {
        "city": city.name,
        "state": city.state,
        "source": "agent",
        "event_count": len(events),
        "events": [ev.model_dump(mode="json") for ev in events],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code in (200, 201, 204):
                logger.info(
                    f"Backend: pushed {len(events)} events for {city.name} → {resp.status_code}"
                )
                return True
            else:
                logger.warning(
                    f"Backend: push returned {resp.status_code} for {city.name}: {resp.text[:200]}"
                )
    except httpx.RequestError as exc:
        logger.error(f"Backend: request error for {city.name}: {exc}")
    except Exception as exc:
        logger.error(f"Backend: unexpected error for {city.name}: {exc}")

    return False


# ──────────────────────────────────────────────
# Per-city fetch orchestration
# ──────────────────────────────────────────────


async def _process_city(city: CityConfig, dry_run: bool, run_ts: str) -> dict[str, Any]:
    """
    Run both fetchers for a single city, deduplicate, score, save, and push.

    Returns a summary dict with counts and status.
    """
    t_start = time.monotonic()
    logger.info(f"═══ Starting {city.name}, {city.state} ═══")

    all_events: list[Event] = []
    errors: list[str] = []

    # ── AllEvents.in ──
    try:
        ae_events = await fetch_allevents_events(
            city.name, city.state, city_slug=city.slug
        )
        logger.info(f"{city.name}: AllEvents.in → {len(ae_events)} events")
        all_events.extend(ae_events)
    except Exception as exc:
        msg = f"AllEvents fetch failed for {city.name}: {exc}"
        logger.error(msg)
        errors.append(msg)

    # ── Facebook Events ──
    try:
        fb_events = await fetch_facebook_events(city.name, city.state)
        logger.info(f"{city.name}: Facebook → {len(fb_events)} events")
        all_events.extend(fb_events)
    except Exception as exc:
        msg = f"Facebook fetch failed for {city.name}: {exc}"
        logger.error(msg)
        errors.append(msg)

    # ── Deduplicate ──
    before_dedup = len(all_events)
    all_events = _deduplicate(all_events)
    logger.info(f"{city.name}: dedup {before_dedup} → {len(all_events)} events")

    # ── Score ──
    scored_events = score_events(all_events, city_lat=city.lat, city_lon=city.lon)

    # Cap at configured max
    scored_events = scored_events[:MAX_EVENTS_PER_CITY]

    # ── Save ──
    output_path = _save_city_results(city, scored_events, run_ts)
    try:
        _save_latest_symlink(city, output_path)
    except Exception:
        pass  # non-critical

    # ── Push to backend ──
    pushed = False
    if not dry_run and BACKEND_URL:
        pushed = await _post_to_backend(city, scored_events)

    elapsed = time.monotonic() - t_start
    summary = {
        "city": city.name,
        "state": city.state,
        "total_fetched": before_dedup,
        "after_dedup": len(all_events),
        "saved": len(scored_events),
        "pushed_to_backend": pushed,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "output_file": str(output_path),
    }
    logger.info(
        f"═══ {city.name} done in {elapsed:.1f}s — "
        f"{len(scored_events)} events saved, backend={'OK' if pushed else 'skip'} ═══"
    )
    return summary


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


async def run(
    city_names: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """
    Main entry point.

    city_names: if provided, only process those cities (matched by name).
    dry_run:    if True, skip posting to backend.
    """
    run_ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info(f"DownTime Event Agent starting — run_ts={run_ts}, dry_run={dry_run}")

    # Select cities
    if city_names:
        name_set = {n.lower().strip() for n in city_names}
        cities = [c for c in CITIES if c.name.lower() in name_set]
        if not cities:
            logger.error(f"No matching cities found for: {city_names}")
            sys.exit(1)
    else:
        cities = list(CITIES)

    logger.info(f"Processing {len(cities)} cities")

    summaries: list[dict] = []

    # Process cities sequentially to respect rate limits and be a good citizen.
    # A random inter-city delay prevents sustained load on any single site.
    for i, city in enumerate(cities):
        summary = await _process_city(city, dry_run=dry_run, run_ts=run_ts)
        summaries.append(summary)

        if i < len(cities) - 1:
            # Inter-city delay: 10–20 s
            import random

            delay = random.uniform(10, 20)
            logger.info(f"Waiting {delay:.1f}s before next city …")
            await asyncio.sleep(delay)

    # ── Run summary ──
    total_saved = sum(s["saved"] for s in summaries)
    total_errors = sum(len(s["errors"]) for s in summaries)
    pushed_count = sum(1 for s in summaries if s["pushed_to_backend"])

    # Save run manifest
    manifest_path = Path(DATA_DIR) / f"manifest_{run_ts}.json"
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w") as f:
        json.dump(
            {
                "run_ts": run_ts,
                "cities_processed": len(summaries),
                "total_events_saved": total_saved,
                "total_errors": total_errors,
                "cities_pushed_to_backend": pushed_count,
                "summaries": summaries,
            },
            f,
            indent=2,
        )

    logger.info(
        f"Run complete: {len(summaries)} cities, {total_saved} events saved, "
        f"{total_errors} errors. Manifest → {manifest_path}"
    )

    if total_errors > 0:
        logger.warning(f"{total_errors} errors occurred — check logs above")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DownTime Event Collection Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m agent
  python -m agent --cities Austin,Denver
  python -m agent --cities "New York" --dry-run
        """,
    )
    parser.add_argument(
        "--cities",
        type=str,
        default="",
        help="Comma-separated list of city names to process (default: all configured cities)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Fetch and save locally but do not POST to backend",
    )
    return parser.parse_args()


if __name__ == "__main__":
    import sentry_sdk as _sentry_sdk

    try:
        args = _parse_args()
        city_names = [c.strip() for c in args.cities.split(",") if c.strip()] or None
        asyncio.run(run(city_names=city_names, dry_run=args.dry_run))
    except Exception as _exc:
        _sentry_sdk.capture_exception(_exc)
        raise
