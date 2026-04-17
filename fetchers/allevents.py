"""
AllEvents.in Playwright fetcher.

Browses https://allevents.in/[city-slug] and extracts events using
Playwright with anti-detection measures.

Anti-detection:
  - Random user-agent from pool
  - Randomised viewport
  - Human-like scroll behaviour with random pauses
  - Random delays between page loads (2–8 s)
  - No more than MAX_REQUESTS_PER_SITE pages per run
  - Injects navigator overrides to hide automation

Structure of AllEvents.in pages:
  - City landing page lists event cards
  - Each card has: title, date/time, venue, category chip, price, link, image
  - Infinite-scroll / "Load more" button for pagination
"""
import asyncio
import hashlib
import logging
import random
import re
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PwTimeout

# playwright-stealth provides a battle-tested bundle of overrides
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

BASE_URL = "https://allevents.in"

# Map AllEvents category labels → DownTime categories
CATEGORY_MAP: dict[str, str] = {
    "music": "music",
    "concerts": "music",
    "live music": "music",
    "sports": "sports",
    "fitness": "sports",
    "arts": "arts",
    "theatre": "arts",
    "theater": "arts",
    "comedy": "arts",
    "art": "arts",
    "dance": "arts",
    "exhibitions": "arts",
    "gallery": "arts",
    "museum": "arts",
    "food": "food",
    "food & drink": "food",
    "drinks": "food",
    "wine": "food",
    "beer": "food",
    "outdoor": "outdoor",
    "nature": "outdoor",
    "adventure": "outdoor",
    "nightlife": "nightlife",
    "clubs": "nightlife",
    "parties": "nightlife",
    "party": "nightlife",
    "film": "film",
    "movies": "film",
    "cinema": "film",
    "screening": "film",
    "festival": "festivals",
    "festivals": "festivals",
    "fairs": "festivals",
    "fair": "festivals",
    "photography": "photography",
    "photo": "photography",
    "motorsports": "motorsports",
    "racing": "motorsports",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "music": ["concert", "live music", "band", "dj", "orchestra", "symphony", "jazz", "hip hop", "rock", "songwriter", "open mic"],
    "sports": ["game", "match", "tournament", "race", "marathon", "5k", "baseball", "basketball", "football", "soccer", "hockey"],
    "arts": ["art", "gallery", "exhibit", "museum", "theater", "theatre", "play", "musical", "ballet", "comedy", "stand-up"],
    "food": ["food", "wine", "beer", "tasting", "brunch", "dinner", "cooking", "chef", "culinary", "brewery", "distillery"],
    "outdoor": ["hike", "hiking", "trail", "park", "garden", "outdoor", "nature", "kayak", "bike", "cycling"],
    "nightlife": ["club", "nightclub", "party", "dj set", "rave", "bar crawl", "happy hour", "lounge", "karaoke"],
    "film": ["film", "movie", "cinema", "screening", "documentary"],
    "festivals": ["festival", "fest ", "fair", "carnival", "celebration", "block party", "street festival"],
    "photography": ["photo", "photography", "camera", "photo walk"],
    "motorsports": ["racing", "drag race", "nascar", "formula", "motocross", "monster truck"],
}


def _make_id(url: str, title: str) -> str:
    raw = f"ae_{url}_{title}"
    return f"ae_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _guess_category(text: str, chip_label: str = "") -> str:
    """Guess DownTime category from chip label or text."""
    chip_lower = chip_label.lower().strip()
    if chip_lower in CATEGORY_MAP:
        return CATEGORY_MAP[chip_lower]

    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return "arts"


def _parse_price(price_text: str) -> tuple[str, str]:
    """Extract normalised (price_range, price_note) from raw price text."""
    if not price_text:
        return ("Unknown", "Check event link for pricing")
    pt = price_text.lower().strip()
    if pt in ("free", "free entry", "$0", "no charge"):
        return ("Free", "Free event")
    # Extract dollar amounts
    amounts = re.findall(r"\$\s?(\d+(?:\.\d{2})?)", price_text)
    if amounts:
        nums = [float(a) for a in amounts]
        mn, mx = min(nums), max(nums)
        if mn == mx:
            return (f"${mn:.0f}", f"Tickets at ${mn:.0f}")
        return (f"${mn:.0f}–${mx:.0f}", f"Tickets from ${mn:.0f} to ${mx:.0f}")
    # Generic "paid" hint
    if any(kw in pt for kw in ["paid", "ticket", "purchase", "buy"]):
        return ("See link", "Paid event — check link for pricing")
    return ("Unknown", price_text[:120] if price_text else "Check event link for pricing")


def _parse_date(date_text: str) -> tuple[str | None, str]:
    """Return (iso_date_or_none, time_info_string)."""
    if not date_text:
        return (None, "")
    # Try to find date pattern like "Sat, Mar 15" or "March 15, 2025"
    # Return the raw string as time_info; attempt ISO parse of the date part
    text = date_text.strip()
    # ISO-like date present?
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        return (iso_match.group(1), text)
    # Month Day Year
    patterns = [
        r"(\w+ \d{1,2},?\s*\d{4})",      # "March 15 2025"
        r"(\w{3,},?\s*\w+ \d{1,2})",     # "Sat, Mar 15"
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return (None, text)  # Can't reliably parse to ISO without year
    return (None, text)


async def _random_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    """Sleep a random amount of time to mimic human browsing."""
    lo = min_s if min_s is not None else DELAY_MIN
    hi = max_s if max_s is not None else DELAY_MAX
    await asyncio.sleep(random.uniform(lo, hi))


async def _human_scroll(page: Page, iterations: int = 3) -> None:
    """Perform human-like scroll behaviour on a page."""
    for _ in range(iterations):
        # Random scroll distance 200–800px
        scroll_by = random.randint(200, 800)
        await page.evaluate(f"window.scrollBy(0, {scroll_by})")
        await asyncio.sleep(random.uniform(0.3, 1.2))
    # Sometimes scroll back a bit
    if random.random() < 0.3:
        await page.evaluate(f"window.scrollBy(0, -{random.randint(100, 300)})")
        await asyncio.sleep(random.uniform(0.2, 0.7))


async def _inject_stealth(page: Page) -> None:
    """
    Inject stealth overrides to mask Playwright automation signals.
    Uses playwright-stealth if available; falls back to manual JS overrides.
    """
    if _HAS_STEALTH:
        await _stealth_async(page)
        return

    # Manual fallback overrides
    await page.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Fake plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Fake languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Fake permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);

        // Remove automation-related chrome properties
        window.chrome = { runtime: {} };

        // Fake connection info
        Object.defineProperty(navigator, 'connection', {
            get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10 }),
        });
    """)


async def _new_context(playwright_instance: Any) -> tuple[Any, BrowserContext]:
    """Launch a browser and return (browser, context) with randomised fingerprint."""
    ua = random.choice(USER_AGENT_POOL)
    viewport = random.choice(VIEWPORT_POOL)

    browser = await playwright_instance.chromium.launch(
        headless=True,
        args=BROWSER_ARGS,
    )
    context = await browser.new_context(
        user_agent=ua,
        viewport=viewport,
        locale="en-US",
        timezone_id="America/Chicago",
        java_script_enabled=True,
        bypass_csp=False,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "DNT": "1",
        },
    )
    # Block unnecessary resources to speed up loading and reduce fingerprint
    await context.route(
        "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf}",
        lambda route: route.abort() if random.random() > 0.2 else route.continue_(),
    )
    return browser, context


def _extract_events_from_cards(cards: list[Any], city: str, state: str) -> list[Event]:
    """Parse a list of Playwright element handles (event cards) into Event objects."""
    events: list[Event] = []
    for card in cards:
        try:
            # These selectors work against the inner HTML obtained via evaluate
            data = card  # Already a dict from evaluate
            title = (data.get("title") or "").strip()
            if not title:
                continue

            url = (data.get("url") or "").strip()
            date_text = (data.get("date") or "").strip()
            venue = (data.get("venue") or "").strip()
            description = (data.get("description") or "").strip()
            category_label = (data.get("category") or "").strip()
            price_text = (data.get("price") or "").strip()
            image_url = (data.get("image") or None)

            date_start, time_info = _parse_date(date_text)
            price_range, price_note = _parse_price(price_text)
            category = _guess_category(f"{title} {description}", category_label)

            event = Event(
                id=_make_id(url, title),
                title=title,
                description=description,
                category=category,
                scenario="",
                source="allevents",
                source_url=url if url.startswith("http") else f"{BASE_URL}{url}",
                venue=venue,
                address="",
                city=city,
                state=state,
                lat=0.0,
                lon=0.0,
                date_start=date_start,
                date_end=None,
                time_info=time_info,
                price_range=price_range,
                price_note=price_note,
                image_url=image_url,
                camera_worthy=False,
                camera_note=None,
                tags=[t for t in [category_label.lower()] if t],
                score=0,
                is_featured=False,
            )
            events.append(event)
        except Exception as exc:
            logger.debug(f"AllEvents card parse error: {exc}")
            continue
    return events


async def _scrape_city_page(page: Page, url: str, city: str, state: str) -> list[Event]:
    """
    Navigate to an AllEvents.in city page and extract event cards.
    Returns a list of Event objects extracted from the page.
    """
    events: list[Event] = []
    try:
        logger.info(f"AllEvents: loading {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await _random_delay(1.5, 3.0)

        # Scroll to trigger lazy-load
        await _human_scroll(page, iterations=random.randint(3, 6))
        await _random_delay(1.0, 2.5)

        # Extract event card data via JS evaluation
        # AllEvents.in uses various card layouts; we try multiple selectors
        raw_cards: list[dict] = await page.evaluate("""
            () => {
                const results = [];

                // Primary card selector (li.event-item or article cards)
                const selectors = [
                    'li.event-item',
                    'article.event-card',
                    '.event-thumb',
                    '[class*="event-item"]',
                    '[data-id][class*="event"]',
                ];

                let cards = [];
                for (const sel of selectors) {
                    cards = Array.from(document.querySelectorAll(sel));
                    if (cards.length > 2) break;
                }

                // Fallback: look for any card-like blocks with an event link
                if (cards.length < 2) {
                    cards = Array.from(document.querySelectorAll('a[href*="/events/"]'))
                        .map(a => a.closest('li, article, div[class*="card"], div[class*="item"]'))
                        .filter(Boolean)
                        .filter((el, i, arr) => arr.indexOf(el) === i); // dedupe
                }

                for (const card of cards) {
                    try {
                        // Title
                        const titleEl = card.querySelector(
                            'h2, h3, h4, .title, [class*="title"], [class*="name"], .event-name'
                        );
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        if (!title) continue;

                        // URL
                        const linkEl = card.querySelector('a[href]');
                        const url = linkEl ? linkEl.href : '';

                        // Date / time
                        const dateEl = card.querySelector(
                            'time, .date, [class*="date"], [class*="time"], [itemprop="startDate"]'
                        );
                        const date = dateEl
                            ? (dateEl.getAttribute('datetime') || dateEl.innerText).trim()
                            : '';

                        // Venue
                        const venueEl = card.querySelector(
                            '.venue, [class*="venue"], [class*="location"], [itemprop="location"], address'
                        );
                        const venue = venueEl ? venueEl.innerText.trim() : '';

                        // Category chip
                        const catEl = card.querySelector(
                            '.category, [class*="category"], .tag, [class*="tag"], .badge'
                        );
                        const category = catEl ? catEl.innerText.trim() : '';

                        // Price
                        const priceEl = card.querySelector(
                            '.price, [class*="price"], [class*="cost"], [class*="ticket"]'
                        );
                        const price = priceEl ? priceEl.innerText.trim() : '';

                        // Image
                        const imgEl = card.querySelector('img[src], img[data-src]');
                        const image = imgEl
                            ? (imgEl.getAttribute('data-src') || imgEl.src)
                            : null;

                        // Description
                        const descEl = card.querySelector(
                            '.description, [class*="desc"], p'
                        );
                        const description = descEl ? descEl.innerText.trim().substring(0, 400) : '';

                        results.push({ title, url, date, venue, category, price, image, description });
                    } catch (e) {
                        // skip malformed card
                    }
                }
                return results;
            }
        """)

        events = _extract_events_from_cards(raw_cards, city, state)
        logger.info(f"AllEvents: extracted {len(events)} events from {url}")

    except PwTimeout:
        logger.warning(f"AllEvents: page timeout for {url}")
    except Exception as exc:
        logger.error(f"AllEvents: error scraping {url}: {exc}")

    return events


async def fetch_allevents_events(
    city: str,
    state: str,
    city_slug: str | None = None,
) -> list[Event]:
    """
    Fetch upcoming events from AllEvents.in for a given city.

    Params:
        city:      City display name (e.g. "Austin")
        state:     State code (e.g. "TX")
        city_slug: URL slug (e.g. "austin"); derived from city name if not provided

    Returns:
        List of Event objects (scored=False, scenario="")
    """
    slug = city_slug or city.lower().replace(" ", "-")
    all_events: list[Event] = []
    request_count = 0

    # Pages to try: main city page + category sub-pages
    city_url = f"{BASE_URL}/{slug}"
    pages_to_visit = [city_url]

    # Add popular category sub-pages
    categories = ["music", "nightlife", "arts", "food", "outdoor", "festivals"]
    for cat in categories:
        pages_to_visit.append(f"{BASE_URL}/{slug}/{cat}/")

    try:
        async with async_playwright() as pw:
            browser, context = await _new_context(pw)

            try:
                page = await context.new_page()
                await _inject_stealth(page)

                for page_url in pages_to_visit:
                    if request_count >= MAX_REQUESTS_PER_SITE:
                        logger.info(f"AllEvents: hit MAX_REQUESTS_PER_SITE ({MAX_REQUESTS_PER_SITE}) for {city}")
                        break
                    if len(all_events) >= MAX_EVENTS_PER_CITY:
                        logger.info(f"AllEvents: hit MAX_EVENTS_PER_CITY ({MAX_EVENTS_PER_CITY}) for {city}")
                        break

                    extracted = await _scrape_city_page(page, page_url, city, state)
                    all_events.extend(extracted)
                    request_count += 1

                    # Try to load more via "Load More" button or scroll-pagination
                    if extracted:
                        loaded_more = await _try_load_more(page, context, city, state, request_count)
                        if loaded_more:
                            all_events.extend(loaded_more)
                            request_count += 1

                    # Polite delay between category pages
                    if page_url != pages_to_visit[-1]:
                        await _random_delay()

            finally:
                await context.close()
                await browser.close()

    except Exception as exc:
        logger.error(f"AllEvents: browser error for {city}: {exc}")

    # Deduplicate within this city (same ID = same event)
    seen: set[str] = set()
    unique: list[Event] = []
    for ev in all_events:
        if ev.id not in seen:
            seen.add(ev.id)
            unique.append(ev)

    logger.info(f"AllEvents: total {len(unique)} unique events for {city}, {state}")
    return unique[:MAX_EVENTS_PER_CITY]


async def _try_load_more(
    page: Page,
    context: BrowserContext,
    city: str,
    state: str,
    request_count: int,
) -> list[Event]:
    """
    Attempt to click a 'Load More' / 'Next Page' button and extract new cards.
    Returns additional events or empty list if none found.
    """
    if request_count >= MAX_REQUESTS_PER_SITE:
        return []

    additional: list[Event] = []
    try:
        # Common selectors for "load more" triggers
        load_more_selectors = [
            "button:has-text('Load More')",
            "button:has-text('Show More')",
            "a:has-text('Load More')",
            "a:has-text('Next')",
            "[class*='load-more']",
            "[class*='loadmore']",
            "[data-action='load-more']",
        ]
        clicked = False
        for sel in load_more_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.scroll_into_view_if_needed()
                    await _random_delay(0.5, 1.5)
                    await btn.click()
                    await _random_delay(2.0, 4.0)
                    await _human_scroll(page, iterations=2)
                    clicked = True
                    break
            except Exception:
                continue

        if clicked:
            # Re-extract cards — new ones will appear after the original set
            url = page.url
            additional = await _scrape_city_page(page, url, city, state)

    except Exception as exc:
        logger.debug(f"AllEvents load-more failed: {exc}")

    return additional
