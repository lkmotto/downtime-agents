"""
DownTime Weekend Email Digest Agent

Orchestrates the full pipeline:
  1. Fetch events from all sources (Ticketmaster, SeatGeek, SerpAPI, OpenTripMap)
  2. Score and curate the top picks for this weekend in DFW
  3. Compose the HTML + plain-text email
  4. Send via Resend

Designed for one-shot execution as a Northflank cron job (every Thursday evening).

Usage:
    python agent.py            # Full run
    python agent.py --dry-run  # Curate + compose but don't send
    python agent.py --test     # Send a test email only
"""
import sentry_init  # noqa: E402,F401

import asyncio
import logging
import sys
import os
import time
from datetime import datetime
from pathlib import Path

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("downtime-agent")


# ── Import config early so env vars are loaded ─────────────────────────────────
# Load by absolute path to avoid shadowing from any other config modules.
import importlib.util as _ilu
import os as _os
_AGENT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_cfg_spec = _ilu.spec_from_file_location("agent_config_ns", _os.path.join(_AGENT_DIR, "config.py"))
config = _ilu.module_from_spec(_cfg_spec)  # type: ignore
_cfg_spec.loader.exec_module(config)  # type: ignore

from curator import curate_weekend
from email_composer import compose_email
from sender import send_email, send_test_email, SendError


# ── Pipeline ───────────────────────────────────────────────────────────────────

async def run(dry_run: bool = False) -> bool:
    """
    Execute the full fetch → curate → compose → send pipeline.

    Args:
        dry_run: If True, skips the send step and prints the email to stdout.

    Returns:
        True on success, False on failure.
    """
    start_time = time.monotonic()
    logger.info("=" * 60)
    logger.info("DownTime Weekend Email Digest Agent starting")
    logger.info(f"Target: {config.RECIPIENT_EMAIL}")
    logger.info(f"City:   {config.CITY}, {config.STATE}")
    logger.info(f"DryRun: {dry_run}")
    logger.info("=" * 60)

    # ── Step 1: Curate ─────────────────────────────────────────────────────────
    logger.info("[1/3] Curating weekend events…")
    try:
        weekend = await curate_weekend(
            city=config.CITY,
            state=config.STATE,
            lat=config.CITY_LAT,
            lon=config.CITY_LON,
            top_n=config.TOP_N_EVENTS,
        )
    except Exception as e:
        logger.error(f"Curation failed: {e}", exc_info=True)
        return False

    total_events = sum(len(v) for v in weekend.buckets.values())
    if total_events == 0:
        logger.error("No events curated — aborting. Check API keys and network connectivity.")
        return False

    logger.info(
        f"Curated {total_events} events for {weekend.weekend_start} – {weekend.weekend_end}"
    )
    for cat, evts in weekend.buckets.items():
        logger.info(f"  [{cat}] {len(evts)} event(s)")

    # ── Step 2: Compose ────────────────────────────────────────────────────────
    logger.info("[2/3] Composing email…")
    try:
        email_payload = compose_email(weekend)
    except Exception as e:
        logger.error(f"Email composition failed: {e}", exc_info=True)
        return False

    logger.info(f"Subject: {email_payload['subject']}")
    logger.info(f"HTML size: {len(email_payload['html'])} bytes")
    logger.info(f"Text size: {len(email_payload['text'])} bytes")

    # ── Optional: save email preview to disk ──────────────────────────────────
    preview_dir = Path(__file__).parent / "previews"
    preview_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = preview_dir / f"email_{ts}.html"
    try:
        preview_path.write_text(email_payload["html"], encoding="utf-8")
        logger.info(f"HTML preview saved: {preview_path}")
    except Exception as e:
        logger.warning(f"Could not save preview: {e}")

    # ── Step 3: Send ───────────────────────────────────────────────────────────
    if dry_run:
        logger.info("[3/3] DRY RUN — skipping send.")
        logger.info("\n" + "=" * 60)
        logger.info("PLAIN TEXT PREVIEW:")
        logger.info("=" * 60)
        print(email_payload["text"])
        logger.info("=" * 60)
        logger.info("Dry run complete. Email NOT sent.")
    else:
        logger.info("[3/3] Sending email via Resend…")
        try:
            result = send_email(
                subject=email_payload["subject"],
                html_body=email_payload["html"],
                text_body=email_payload["text"],
            )
            resend_id = result.get("id", "unknown")
            logger.info(f"Email sent! Resend message ID: {resend_id}")
        except (SendError, ValueError) as e:
            logger.error(f"Failed to send email: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected send error: {e}", exc_info=True)
            return False

    elapsed = time.monotonic() - start_time
    logger.info(f"Pipeline completed in {elapsed:.1f}s")
    return True


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    test_mode = "--test" in args

    if test_mode:
        # Quick smoke test: send a minimal test email
        logger.info("Running in TEST mode — sending test email only")
        try:
            result = send_test_email()
            logger.info(f"Test email sent. Resend ID: {result.get('id')}")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Test email failed: {e}")
            sys.exit(1)

    # Full pipeline
    success = asyncio.run(run(dry_run=dry_run))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    import sentry_sdk as _sentry_sdk
    try:
        main()
    except Exception as _exc:
        _sentry_sdk.capture_exception(_exc)
        raise

