"""
Scoring engine for DownTime Event Collection Agent.

Ported from /downtime-product/backend/scoring.py — kept in sync.

Scores events 0–100 based on:
  - Category match to user interests (25 pts)
  - Camera/photography value (25 pts)
  - Price value (20 pts)
  - Proximity to city centre (15 pts)
  - Uniqueness factor (15 pts)

Also assigns:
  - camera_worthy boolean + camera_note with specific shot ideas
  - scenario (date-night, solo, weekend-adventure, travel)
"""
import math
import re
from models import Event


# ──────────────────────────────────────────────
# Scenario assignment
# ──────────────────────────────────────────────

SCENARIO_RULES = {
    "date-night": {
        "categories": {"music", "arts", "food", "nightlife", "film"},
        "keywords": [
            "dinner", "wine", "cocktail", "jazz", "romantic", "couples",
            "tasting", "rooftop", "lounge", "ballet", "symphony", "theater",
            "comedy", "speakeasy", "candlelight", "sunset", "date",
        ],
        "time_hints": ["evening", "pm", "night"],
    },
    "solo": {
        "categories": {"arts", "outdoor", "photography", "food"},
        "keywords": [
            "museum", "gallery", "hike", "trail", "coffee", "bookstore",
            "workshop", "class", "meditation", "yoga", "park", "garden",
            "market", "walk", "solo", "self", "free",
        ],
        "time_hints": ["morning", "am", "afternoon"],
    },
    "weekend-adventure": {
        "categories": {"outdoor", "festivals", "sports", "motorsports"},
        "keywords": [
            "festival", "fair", "carnival", "adventure", "kayak", "bike",
            "climb", "zipline", "tour", "day trip", "road trip", "camping",
            "race", "marathon", "5k", "beach", "lake", "mountain",
            "brewery tour", "winery", "escape room",
        ],
        "time_hints": [],
    },
    "travel": {
        "categories": {"outdoor", "arts", "food"},
        "keywords": [
            "landmark", "monument", "historic", "attraction", "scenic",
            "viewpoint", "national park", "state park", "architecture",
            "downtown", "district", "neighborhood", "cultural", "heritage",
        ],
        "time_hints": [],
    },
}


def _assign_scenario(event: Event) -> str:
    scores: dict[str, int] = {}
    text = f"{event.title} {event.description} {' '.join(event.tags)}".lower()

    for scenario, rules in SCENARIO_RULES.items():
        score = 0
        if event.category in rules["categories"]:
            score += 3
        for kw in rules["keywords"]:
            if kw in text:
                score += 2
        time_lower = event.time_info.lower()
        for hint in rules["time_hints"]:
            if hint in time_lower:
                score += 1
        scores[scenario] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        category_defaults = {
            "music": "date-night",
            "sports": "weekend-adventure",
            "arts": "solo",
            "food": "date-night",
            "outdoor": "weekend-adventure",
            "nightlife": "date-night",
            "film": "date-night",
            "festivals": "weekend-adventure",
            "photography": "solo",
            "motorsports": "weekend-adventure",
        }
        return category_defaults.get(event.category, "solo")
    return best


# ──────────────────────────────────────────────
# Camera-worthiness
# ──────────────────────────────────────────────

CAMERA_WORTHY_CATEGORIES = {"outdoor", "festivals", "photography", "arts"}

CAMERA_SHOT_IDEAS = {
    "music": [
        "Capture the stage lighting and crowd energy",
        "Shoot from the side of the stage for dramatic silhouettes",
        "Use burst mode for dynamic performer shots",
    ],
    "sports": [
        "Fast shutter speed for action shots — try 1/1000s+",
        "Capture the crowd reactions and stadium atmosphere",
    ],
    "arts": [
        "Look for interesting compositions in the exhibits",
        "Capture the architecture and interior details",
        "Street photography opportunity in the surrounding area",
    ],
    "food": [
        "Overhead flat-lay shots of dishes and presentations",
        "Capture the ambiance and plating details",
    ],
    "outdoor": [
        "Golden hour is your best friend — arrive early or stay late",
        "Wide panoramic shots plus intimate detail close-ups",
        "Bring a polarizer for richer skies and water reflections",
    ],
    "nightlife": [
        "Low-light challenge — use wide aperture and embrace motion blur",
        "Neon signs and street reflections make great subjects",
    ],
    "film": ["Capture the venue atmosphere and marquee"],
    "festivals": [
        "Vibrant colours and crowds — shoot wide to capture the energy",
        "Detail shots of food, art, and costumes tell the story",
        "Golden hour + festival lights = magic",
    ],
    "photography": [
        "Meta! Bring your best gear and learn from fellow photographers",
        "Practice techniques you've been wanting to try",
    ],
    "motorsports": [
        "Panning shots at slow shutter speed for motion blur effect",
        "Capture the pit lane energy and mechanical details",
    ],
}

CAMERA_WORTHY_KEYWORDS = [
    "outdoor", "park", "garden", "beach", "sunset", "sunrise", "mural",
    "street art", "scenic", "view", "waterfront", "rooftop", "skyline",
    "festival", "parade", "fireworks", "neon", "historic", "architecture",
    "nature", "trail", "lake", "river", "mountain", "canyon",
    "gallery", "art walk", "photo walk", "exhibit",
]


def _assign_camera(event: Event) -> tuple[bool, str | None]:
    if event.camera_worthy and event.camera_note:
        return event.camera_worthy, event.camera_note

    text = f"{event.title} {event.description} {' '.join(event.tags)}".lower()
    is_worthy = event.category in CAMERA_WORTHY_CATEGORIES

    for kw in CAMERA_WORTHY_KEYWORDS:
        if kw in text:
            is_worthy = True
            break

    venue_lower = event.venue.lower()
    for hint in ["park", "garden", "amphitheater", "amphitheatre", "field", "beach", "pier", "plaza", "square"]:
        if hint in venue_lower:
            is_worthy = True
            break

    note = None
    if is_worthy:
        ideas = CAMERA_SHOT_IDEAS.get(event.category, ["A visually interesting spot worth capturing"])
        note = ideas[0]

    return is_worthy, note


# ──────────────────────────────────────────────
# Sub-scorers
# ──────────────────────────────────────────────

def _score_category_match(event: Event, user_interests: list[str] | None = None) -> int:
    if not user_interests:
        popular = {
            "music": 20, "festivals": 20, "food": 18, "outdoor": 18,
            "arts": 15, "nightlife": 15, "sports": 14, "film": 12,
            "photography": 12, "motorsports": 10,
        }
        return popular.get(event.category, 12)
    if event.category in user_interests:
        return 25
    related = {
        "music": ["nightlife", "festivals"],
        "outdoor": ["photography", "sports"],
        "arts": ["film", "photography"],
        "food": ["nightlife", "festivals"],
        "festivals": ["music", "food", "outdoor"],
        "nightlife": ["music", "food"],
    }
    for interest in user_interests:
        if event.category in related.get(interest, []):
            return 15
    return 5


def _score_camera_value(event: Event) -> int:
    if not event.camera_worthy:
        return 5
    score = 15
    text = f"{event.title} {event.description} {' '.join(event.tags)}".lower()
    visual_bonuses = [
        ("sunset", 3), ("sunrise", 3), ("mural", 2), ("street art", 2),
        ("skyline", 3), ("panoramic", 3), ("fireworks", 3), ("waterfront", 2),
        ("neon", 2), ("garden", 2), ("festival", 2), ("outdoor", 2),
        ("scenic", 3), ("viewpoint", 3), ("rooftop", 2),
    ]
    bonus = sum(pts for kw, pts in visual_bonuses if kw in text)
    return min(score + bonus, 25)


def _parse_price_value(price_range: str) -> float | None:
    if not price_range:
        return None
    lower = price_range.lower()
    if lower in ("free", "$0"):
        return 0.0
    if lower in ("unknown", "varies", "see link"):
        return None
    match = re.search(r"\$?(\d+(?:\.\d{2})?)", price_range)
    if match:
        return float(match.group(1))
    return None


def _score_price_value(event: Event) -> int:
    price = _parse_price_value(event.price_range)
    if price is None:
        return 10
    if price == 0:
        return 20
    if price <= 15:
        return 18
    if price <= 30:
        return 15
    if price <= 50:
        return 12
    if price <= 100:
        return 8
    if price <= 200:
        return 5
    return 3


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _score_proximity(event: Event, city_lat: float, city_lon: float) -> int:
    if event.lat == 0.0 and event.lon == 0.0:
        return 8
    dist = _haversine_km(event.lat, event.lon, city_lat, city_lon)
    if dist <= 5:
        return 15
    if dist <= 10:
        return 13
    if dist <= 20:
        return 10
    if dist <= 40:
        return 7
    if dist <= 80:
        return 4
    return 2


def _score_uniqueness(event: Event) -> int:
    text = f"{event.title} {event.description}".lower()
    unique_keywords = [
        "festival", "premiere", "grand opening", "one night only",
        "special", "exclusive", "limited", "popup", "pop-up",
        "farewell", "final", "inaugural", "annual", "celebration",
    ]
    recurring_keywords = [
        "every week", "weekly", "every day", "daily", "recurring",
        "open daily", "permanent", "ongoing", "always",
    ]
    unique_score = 8
    for kw in unique_keywords:
        if kw in text:
            unique_score += 2
    for kw in recurring_keywords:
        if kw in text:
            unique_score -= 2
    if event.date_start:
        unique_score += 2
    # Boost for high attendee interest (Facebook-specific)
    if event.attendee_count and event.attendee_count > 500:
        unique_score += 2
    return max(0, min(unique_score, 15))


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def score_event(
    event: Event,
    city_lat: float = 0.0,
    city_lon: float = 0.0,
    user_interests: list[str] | None = None,
) -> Event:
    """Score a single event and assign scenario + camera metadata."""
    camera_worthy, camera_note = _assign_camera(event)

    category_score = _score_category_match(event, user_interests)
    camera_score = _score_camera_value(event.model_copy(update={"camera_worthy": camera_worthy}))
    price_score = _score_price_value(event)
    proximity_score = _score_proximity(event, city_lat, city_lon)
    uniqueness_score = _score_uniqueness(event)

    total = max(0, min(category_score + camera_score + price_score + proximity_score + uniqueness_score, 100))
    scenario = _assign_scenario(event)

    return event.model_copy(
        update={
            "score": total,
            "camera_worthy": camera_worthy,
            "camera_note": camera_note,
            "scenario": scenario,
            "is_featured": total >= 80,
        }
    )


def score_events(
    events: list[Event],
    city_lat: float = 0.0,
    city_lon: float = 0.0,
    user_interests: list[str] | None = None,
) -> list[Event]:
    """Score and sort events by score descending."""
    scored = [score_event(e, city_lat, city_lon, user_interests) for e in events]
    scored.sort(key=lambda e: e.score, reverse=True)
    return scored
