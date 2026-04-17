"""
Facebook Events Playwright fetcher.

Strategy:
  PRIMARY:   Browse facebook.com/events/search/?q=[city] without login.
             Facebook renders some public event data even for unauthenticated users.

  FALLBACK:  If Facebook requires login or returns too few results, fall back to
             a Google Search via Playwright: site:facebook.com/events [city]
             This exposes public event pages indexed by Google.

Anti-detection:
  - Randomised user-agent and viewport
  - Human-like scroll patterns
  - Random delays 2–8 s
  - Stealth JS overrides (no webdriver flag etc.)
  - Graceful block detection: log and skip rather than retry aggressively
"""
import asyncio
import hashlib
import logging
import random
import re
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PwTimeout

try:
    from playwright_stealth import stealth_async as _stealth_async  # type: ignore
    _HAS_STEALTH = True
except ImportError:  # pragma: no cover
    _HAS_STEALTH = False

from config import (
    USER_AGENT_POOL,
    VIEWPORT_POOL,
    BROWSER_ARGS,
    DELAY_MIN,
    DELAY_MAX,
    MAX_REQUESTS_PER_SITE,
    MAX_EVENTS_PER_CITY,
)
from models import Event

logger = logging.getLogger(__name__)

FB_BASE = "https://www.facebook.com"
GOOGLE_SEARCH = "https://www.google.com/search"

# ──────────────────────────────────────────────
# Helpers shared with allevents (duplicated intentionally for standalone use)
# ──────────────────────────────────────────────

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "music": ["concert", "live music", "band", "dj", "orchestra", "symphony", "jazz", "hip hop", "rock", "songwriter"],
    "sports": ["game", "match", "tournament", "race", "marathon", "5k", "baseball", "basketball", "football"],
    "arts": ["art", "gallery", "exhibit", "museum", "theater", "theatre", "play", "ballet", "comedy", "stand-up"],
    "food": ["food", "wine", "beer", "tasting", "brunch", "dinner", "cooking", "chef", "culinary", "brewery"],
    "outdoor": ["hike", "hiking", "trail", "park", "garden", "outdoor", "nature", "kayak", "bike"],
    "nightlife": ["club", "nightclub", "party", "dj set", "bar crawl", "happy hour", "lounge", "karaoke"],
    "film": ["film", "movie", "cinema", "screening", "documentary"],
    "festivals": ["festival", "fest ", "fair", "carnival", "celebration", "block party", "street festival"],
    "photography": ["photo", "photography", "camera", "photo walk"],
    "motorsports": ["racing", "drag race", "nascar", "formula", "motocross"],
}


def _make_id(url: str, title: str) -> str:
    raw = f"fb_{url}_{title}"
    return f"fb_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _guess_category(text: str) -> str:
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return "arts"


def _parse_price(text: str) -> tuple[str, str]:
    if not text:
        return ("Unknown", "Check event link for pricing")
    t = text.lower().strip()
    if t in ("free", "free event", "$0"):
        return ("Free", "Free event")
    amounts = re.findall(r"\$\s?(\d+(?:\.\d{2})?)", text)
    if amounts:
        nums = [float(a) for a in amounts]
        mn, mx = min(nums), max(nums)
        if mn == mx:
            return (f"${mn:.0f}", f"Tickets at ${mn:.0f}")
        return (f"${mn:.0f}–${mx:.0f}", f"Tickets from ${mn:.0f} to ${mx:.0f}")
    return ("Unknown", text[:120])


def _parse_attendee_count(text: str) -> int | None:
    """Extract numeric attendee count from strings like '1.2K interested' or '345 going'."""
    if not text:
        return None
    # Handle K/M suffixes
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*([KkMm]?)\s*(?:interested|going|attending|people)", text)
    if m:
        num_str = m.group(1).replace(",", "")
        suffix = m.group(2).upper()
        try:
            num = float(num_str)
            if suffix == "K":
                num *= 1_000
            elif suffix == "M":
                num *= 1_000_000
            return int(num)
        except ValueError:
            pass
    return None


async def _random_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    lo = min_s if min_s is not None else DELAY_MIN
    hi = max_s if max_s is not None else DELAY_MAX
    await asyncio.sleep(random.uniform(lo, hi))


async def _human_scroll(page: Page, iterations: int = 4) -> None:
    for _ in range(iterations):
        scroll_by = random.randint(250, 700)
        await page.evaluate(f"window.scrollBy(0, {scroll_by})")
        await asyncio.sleep(random.uniform(0.4, 1.5))
    if random.random() < 0.4:
        await page.evaluate(f"window.scrollBy(0, -{random.randint(100, 250)})")
        await asyncio.sleep(random.uniform(0.3, 0.8))


async def _inject_stealth(page: Page) -> None:
    if _HAS_STEALTH:
        await _stealth_async(page)
        return

    # Manual fallback overrides
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'connection', {
            get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10 }),
        });
    """)


async def _new_context(playwright_instance: Any) -> tuple[Any, BrowserContext]:
    ua = random.choice(USER_AGENT_POOL)
    viewport = random.choice(VIEWPORT_POOL)
    browser = await playwright_instance.chromium.launch(headless=True, args=BROWSER_ARGS)
    context = await browser.new_context(
        user_agent=ua,
        viewport=viewport,
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "DNT": "1",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
        },
    )
    # Block tracking pixels but allow main content
    await context.route(
        "**/{pixel,beacon,analytics,ads,tracking}*",
        lambda route: route.abort(),
    )
    return browser, context


# ──────────────────────────────────────────────
# Facebook Events parser helpers
# ──────────────────────────────────────────────

def _parse_fb_cards(raw_cards: list[dict], city: str, state: str) -> list[Event]:
    events: list[Event] = []
    for card in raw_cards:
        try:
            title = (card.get("title") or "").strip()
            if not title or len(title) < 3:
                continue
            url = (card.get("url") or "").strip()
            date_text = (card.get("date") or "").strip()
            venue = (card.get("venue") or "").strip()
            description = (card.get("description") or "").strip()
            price_text = (card.get("price") or "").strip()
            image_url = card.get("image") or None
            attendee_text = (card.get("attendees") or "").strip()

            price_range, price_note = _parse_price(price_text)
            attendee_count = _parse_attendee_count(attendee_text)
            category = _guess_category(f"{title} {description}")

            full_url = url if url.startswith("http") else f"{FB_BASE}{url}"

            event = Event(
                id=_make_id(full_url, title),
                title=title,
                description=description,
                category=category,
                scenario="",
                source="facebook",
                source_url=full_url,
                venue=venue,
                address="",
                city=city,
                state=state,
                lat=0.0,
                lon=0.0,
                date_start=None,
                date_end=None,
                time_info=date_text,
                price_range=price_range,
                price_note=price_note,
                image_url=image_url,
                camera_worthy=False,
                camera_note=None,
                tags=[],
                score=0,
                is_featured=False,
                attendee_count=attendee_count,
            )
            events.append(event)
        except Exception as exc:
            logger.debug(f"FB card parse error: {exc}")
            continue
    return events


# ──────────────────────────────────────────────
# Primary: Facebook Events search (no login)
# ──────────────────────────────────────────────

async def _fetch_from_facebook(
    page: Page,
    city: str,
    state: str,
    request_count: int,
) -> tuple[list[Event], bool]:
    """
    Browse facebook.com/events/search/?q=[city].

    Returns (events, blocked) where blocked=True means FB demanded login.
    """
    query = f"{city}, {state}"
    url = f"{FB_BASE}/events/search/?q={query.replace(' ', '+')}"

    events: list[Event] = []
    blocked = False

    try:
        logger.info(f"Facebook: loading {url}")
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        await _random_delay(2.0, 4.0)

        # Detect login wall
        current_url = page.url
        page_text = await page.evaluate("() => document.body.innerText")

        block_signals = [
            "log in" in page_text.lower() and "to see" in page_text.lower(),
            "login" in current_url.lower(),
            "checkpoint" in current_url.lower(),
            "You must log in" in page_text,
            "create an account" in page_text.lower() and len(page_text) < 2000,
        ]
        if any(block_signals):
            logger.warning(f"Facebook: login wall detected for {city} — falling back to Google search")
            blocked = True
            return events, blocked

        # Scroll to load more events
        await _human_scroll(page, iterations=random.randint(4, 7))
        await _random_delay(1.5, 3.0)

        # Extract event cards via JS
        raw_cards: list[dict] = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();

                // Facebook event search results use role="article" or specific class patterns
                const containers = [
                    ...Array.from(document.querySelectorAll('[role="article"]')),
                    ...Array.from(document.querySelectorAll('[data-testid*="event"]')),
                    ...Array.from(document.querySelectorAll('a[href*="/events/"]'))
                        .map(a => a.closest('[role="article"], li, div[class*="event"]'))
                        .filter(Boolean),
                ].filter((el, i, arr) => el && arr.indexOf(el) === i);

                for (const container of containers) {
                    try {
                        // Title: first heading or strong text
                        const titleEl = container.querySelector('h2, h3, h4, strong, [role="heading"]');
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        if (!title || seen.has(title)) continue;
                        seen.add(title);

                        // URL
                        const linkEl = container.querySelector('a[href*="/events/"]');
                        const url = linkEl ? linkEl.href : '';

                        // Date/time: look for time element or patterns
                        const timeEl = container.querySelector('time, [class*="date"], [class*="time"]');
                        const date = timeEl
                            ? (timeEl.getAttribute('datetime') || timeEl.innerText).trim()
                            : '';

                        // Venue: usually second or third line of text
                        const spans = Array.from(container.querySelectorAll('span, div')).filter(
                            el => el.children.length === 0 && el.innerText.trim().length > 2
                        );
                        const venue = spans.length > 2 ? spans[2].innerText.trim() : '';

                        // Attendees
                        const attendeeEl = Array.from(container.querySelectorAll('span')).find(
                            el => /interested|going|attending/i.test(el.innerText)
                        );
                        const attendees = attendeeEl ? attendeeEl.innerText.trim() : '';

                        // Image
                        const imgEl = container.querySelector('img[src]');
                        const image = imgEl ? imgEl.src : null;

                        results.push({ title, url, date, venue, attendees, image, description: '', price: '' });
                    } catch (e) {
                        // skip
                    }
                }
                return results;
            }
        """)

        events = _parse_fb_cards(raw_cards, city, state)
        logger.info(f"Facebook: extracted {len(events)} events for {city} (direct)")

    except PwTimeout:
        logger.warning(f"Facebook: timeout for {city}")
    except Exception as exc:
        logger.error(f"Facebook: error for {city}: {exc}")

    return events, blocked


# ──────────────────────────────────────────────
# Fallback: Google search → facebook.com/events
# ──────────────────────────────────────────────

async def _fetch_via_google(
    page: Page,
    city: str,
    state: str,
) -> list[Event]:
    """
    Fall back to Googling: site:facebook.com/events [city state]
    Collects the event URLs from Google results, then visits each to extract data.
    """
    query = f'site:facebook.com/events {city} {state} events'
    search_url = f"{GOOGLE_SEARCH}?q={query.replace(' ', '+')}&num=20"

    events: list[Event] = []

    try:
        logger.info(f"Facebook fallback: Google search for {city}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25_000)
        await _random_delay(2.0, 4.0)

        # Extract FB event URLs from Google results
        fb_urls: list[str] = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links
                    .map(a => a.href)
                    .filter(href => href.includes('facebook.com/events/') && !href.includes('google'))
                    .slice(0, 15);
            }
        """)

        logger.info(f"Facebook fallback: found {len(fb_urls)} event URLs via Google for {city}")

        # Visit each event page to extract details
        for fb_url in fb_urls[:10]:  # Cap at 10 individual pages
            try:
                event = await _fetch_single_fb_event(page, fb_url, city, state)
                if event:
                    events.append(event)
                await _random_delay(2.5, 5.0)
            except Exception as exc:
                logger.debug(f"FB fallback event page error ({fb_url}): {exc}")
                continue

    except PwTimeout:
        logger.warning(f"Facebook fallback: Google search timeout for {city}")
    except Exception as exc:
        logger.error(f"Facebook fallback error for {city}: {exc}")

    return events


async def _fetch_single_fb_event(page: Page, url: str, city: str, state: str) -> Event | None:
    """
    Visit a single public Facebook event page and extract details.
    Returns None if login is required or extraction fails.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await _random_delay(1.5, 3.0)

        page_text = await page.evaluate("() => document.body.innerText")

        # Check login wall
        if "log in" in page_text.lower() and "to see" in page_text.lower():
            logger.debug(f"FB event page requires login: {url}")
            return None

        data: dict = await page.evaluate("""
            () => {
                // Title: og:title or h1
                const ogTitle = document.querySelector('meta[property="og:title"]');
                const title = ogTitle
                    ? ogTitle.getAttribute('content')
                    : (document.querySelector('h1, h2') || {}).innerText || '';

                // Description: og:description or first paragraph
                const ogDesc = document.querySelector('meta[property="og:description"]');
                const description = ogDesc
                    ? ogDesc.getAttribute('content')
                    : (document.querySelector('p, [data-testid="event-description"]') || {}).innerText || '';

                // Image: og:image
                const ogImage = document.querySelector('meta[property="og:image"]');
                const image = ogImage ? ogImage.getAttribute('content') : null;

                // Date: look for time elements or JSON-LD
                let date = '';
                const timeEl = document.querySelector('time');
                if (timeEl) date = timeEl.getAttribute('datetime') || timeEl.innerText;

                // JSON-LD structured data
                let venue = '';
                let price = '';
                try {
                    const lds = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
                    for (const ld of lds) {
                        const data = JSON.parse(ld.textContent);
                        if (data['@type'] === 'Event') {
                            date = date || data.startDate || '';
                            venue = (data.location && (data.location.name || data.location.address)) || '';
                            price = (data.offers && data.offers.price != null)
                                ? ('$' + data.offers.price)
                                : (data.offers && data.offers.description) || '';
                        }
                    }
                } catch (e) {}

                // Attendees
                const attendeeEls = Array.from(document.querySelectorAll('span')).filter(
                    el => /interested|going|attending/i.test(el.innerText)
                );
                const attendees = attendeeEls.length ? attendeeEls[0].innerText.trim() : '';

                return { title, description, image, date, venue, price, attendees };
            }
        """)

        title = (data.get("title") or "").strip()
        if not title:
            return None

        price_range, price_note = _parse_price(data.get("price") or "")
        attendee_count = _parse_attendee_count(data.get("attendees") or "")
        category = _guess_category(f"{title} {data.get('description', '')}")

        return Event(
            id=_make_id(url, title),
            title=title,
            description=(data.get("description") or "")[:500],
            category=category,
            scenario="",
            source="facebook",
            source_url=url,
            venue=(data.get("venue") or "").strip(),
            address="",
            city=city,
            state=state,
            lat=0.0,
            lon=0.0,
            date_start=None,
            date_end=None,
            time_info=(data.get("date") or "").strip(),
            price_range=price_range,
            price_note=price_note,
            image_url=data.get("image"),
            camera_worthy=False,
            camera_note=None,
            tags=[],
            score=0,
            is_featured=False,
            attendee_count=attendee_count,
        )

    except PwTimeout:
        logger.debug(f"FB event page timeout: {url}")
    except Exception as exc:
        logger.debug(f"FB event page error ({url}): {exc}")

    return None


# ──────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────

async def fetch_facebook_events(
    city: str,
    state: str,
) -> list[Event]:
    """
    Fetch upcoming events from Facebook for a given city.

    Attempts Facebook Events search directly; falls back to Google if blocked.

    Params:
        city:  City display name (e.g. "Austin")
        state: State code (e.g. "TX")

    Returns:
        List of Event objects (un-scored)
    """
    all_events: list[Event] = []

    try:
        async with async_playwright() as pw:
            browser, context = await _new_context(pw)

            try:
                page = await context.new_page()
                await _inject_stealth(page)

                # Primary: direct FB search
                events, blocked = await _fetch_from_facebook(page, city, state, 0)
                all_events.extend(events)

                # Fallback if blocked or too few results
                if blocked or len(all_events) < 3:
                    logger.info(f"Facebook: using Google fallback for {city}")
                    await _random_delay(3.0, 6.0)
                    fallback_events = await _fetch_via_google(page, city, state)
                    # Merge fallback, avoiding duplicates
                    existing_ids = {e.id for e in all_events}
                    for ev in fallback_events:
                        if ev.id not in existing_ids:
                            all_events.append(ev)
                            existing_ids.add(ev.id)

            finally:
                await context.close()
                await browser.close()

    except Exception as exc:
        logger.error(f"Facebook: browser error for {city}: {exc}")

    logger.info(f"Facebook: total {len(all_events)} events for {city}, {state}")
    return all_events[:MAX_EVENTS_PER_CITY]
