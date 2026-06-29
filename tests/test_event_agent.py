"""
Tests for the event-agent package.

Covers:
  - Event model creation and validation
  - CityConfig dataclass and get_city lookup
  - Scoring engine: haversine, price, proximity, scenario, camera
  - Fetcher module exports
  - Configuration defaults
"""

import importlib.util
import os
import sys
import pytest
from datetime import datetime

_EVENT_AGENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "event-agent")
)


def _load_event_module(name, filename):
    """Load a module from event-agent/ by file path with a unique name."""
    filepath = os.path.join(_EVENT_AGENT_DIR, filename)
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Load event-agent modules with unique names to avoid collision ─────────────

# Load models as "event_models" to avoid collision with email-agent/models.py
_event_models = _load_event_module("_event_agent_models", "models.py")
_event_config = _load_event_module("_event_agent_config", "config.py")

# For scoring.py: it does `from models import Event`, so we need "models"
# in sys.modules to point to event-agent/models.py.
# Use a unique name and also register it as "models" temporarily.
# But we must not break email-agent tests. The cleanest approach:
# Load scoring via importlib AFTER ensuring event-agent is on sys.path
# and the correct "models" is cached.
#
# Strategy: put event-agent dir at front of sys.path, clear any stale
# "models" import, then load scoring.
_need_path_fix = _EVENT_AGENT_DIR not in sys.path
if _need_path_fix:
    sys.path.insert(0, _EVENT_AGENT_DIR)

# Ensure "models" resolves to event-agent/models.py for scoring.py's import
# Overwrite whatever "models" might be cached
_event_models_direct = _load_event_module("models", "models.py")

_event_scoring = _load_event_module("_event_scoring", "scoring.py")

# Also load fetchers init
_event_fetchers = _load_event_module("_event_fetchers", os.path.join("fetchers", "__init__.py"))


# ── Test Event model ──────────────────────────────────────────────────────────

class TestEventModel:
    """Tests for the event-agent Event Pydantic model."""

    def test_event_creation_with_minimal_fields(self):
        """Event can be created with only required fields."""
        Event = _event_models.Event
        event = Event(
            id="evt-001",
            title="Austin City Limits Festival",
            source="allevents",
        )
        assert event.id == "evt-001"
        assert event.title == "Austin City Limits Festival"
        assert event.source == "allevents"
        assert event.description == ""
        assert event.category == ""
        assert event.scenario == ""
        assert event.score == 0
        assert event.camera_worthy is False
        assert event.is_featured is False
        assert isinstance(event.tags, list)
        assert isinstance(event.created_at, datetime)

    def test_event_creation_with_full_fields(self):
        """Event can be created with all optional fields populated."""
        Event = _event_models.Event
        event = Event(
            id="evt-full-001",
            title="Denver Beer Festival",
            description="Annual craft beer festival with 100+ breweries.",
            category="festivals",
            scenario="weekend-adventure",
            source="facebook",
            source_url="https://fb.com/events/123",
            venue="Civic Center Park",
            address="101 W 14th Ave, Denver, CO",
            city="Denver",
            state="CO",
            lat=39.7392,
            lon=-104.9903,
            date_start="2025-07-04T12:00:00",
            date_end="2025-07-04T22:00:00",
            time_info="Friday, July 4 at 12:00 PM",
            price_range="$35",
            price_note="Early bird available",
            image_url="https://example.com/beer-fest.jpg",
            camera_worthy=True,
            camera_note="Vibrant colours and crowds \u2014 shoot wide to capture the energy.",
            tags=["beer", "festival", "craft"],
            score=92,
            is_featured=True,
            attendee_count=1500,
        )
        assert event.id == "evt-full-001"
        assert event.city == "Denver"
        assert event.state == "CO"
        assert event.lat == pytest.approx(39.7392)
        assert event.lon == pytest.approx(-104.9903)
        assert event.category == "festivals"
        assert event.scenario == "weekend-adventure"
        assert event.price_range == "$35"
        assert event.score == 92
        assert event.is_featured is True
        assert event.camera_worthy is True
        assert event.attendee_count == 1500
        assert "beer" in event.tags
        assert "festival" in event.tags

    def test_event_model_dump_includes_all_fields(self):
        """Event.model_dump() returns a dict with all fields."""
        Event = _event_models.Event
        event = Event(
            id="evt-dump-001",
            title="Free Concert in the Park",
            category="music",
            source="allevents",
            city="Austin",
            state="TX",
            lat=30.2672,
            lon=-97.7431,
            price_range="Free",
            tags=["free", "music", "outdoor"],
            attendee_count=300,
        )
        data = event.model_dump()
        assert data["id"] == "evt-dump-001"
        assert data["title"] == "Free Concert in the Park"
        assert data["category"] == "music"
        assert data["source"] == "allevents"
        assert data["city"] == "Austin"
        assert data["state"] == "TX"
        assert data["lat"] == pytest.approx(30.2672)
        assert data["price_range"] == "Free"
        assert data["attendee_count"] == 300


# ── Test CityConfig and get_city ──────────────────────────────────────────────

class TestCityConfig:
    """Tests for the CityConfig dataclass and get_city lookup."""

    def test_city_config_default_slug(self):
        """CityConfig auto-generates a slug from the name."""
        CityConfig = _event_config.CityConfig
        city = CityConfig("New York", "NY", 40.7128, -74.0060)
        assert city.name == "New York"
        assert city.state == "NY"
        assert city.lat == pytest.approx(40.7128)
        assert city.lon == pytest.approx(-74.0060)
        assert city.slug == "new-york"

    def test_city_config_explicit_slug(self):
        """CityConfig accepts an explicit slug override."""
        CityConfig = _event_config.CityConfig
        city = CityConfig("Washington", "DC", 38.9072, -77.0369, slug="washington-dc")
        assert city.slug == "washington-dc"

    def test_get_city_finds_existing_city(self):
        """get_city returns a CityConfig for a known city (case-insensitive)."""
        get_city = _event_config.get_city
        city = get_city("dallas")
        assert city is not None
        assert city.name == "Dallas"
        assert city.state == "TX"
        assert city.lat == pytest.approx(32.7767)

    def test_get_city_with_state_filter(self):
        """get_city with state filter returns the correct city."""
        get_city = _event_config.get_city
        city = get_city("Austin", state="TX")
        assert city is not None
        assert city.name == "Austin"
        assert city.state == "TX"

    def test_get_city_returns_none_for_unknown_city(self):
        """get_city returns None for a city not in the list."""
        get_city = _event_config.get_city
        city = get_city("Zzyzx")
        assert city is None

    def test_cities_list_is_non_empty(self):
        """The CITIES list contains at least 50 entries."""
        CITIES = _event_config.CITIES
        assert len(CITIES) >= 50
        city_names = {c.name for c in CITIES}
        assert "New York" in city_names
        assert "Los Angeles" in city_names
        assert "Chicago" in city_names
        assert "Dallas" in city_names
        assert "Austin" in city_names


# ── Test scoring module ───────────────────────────────────────────────────────

class TestScoring:
    """Tests for the event-agent scoring engine."""

    def test_haversine_same_point_is_zero(self):
        """Distance from a point to itself is zero."""
        dist = _event_scoring._haversine_km(32.7767, -96.7970, 32.7767, -96.7970)
        assert dist == pytest.approx(0.0, abs=1e-6)

    def test_haversine_dallas_to_austin(self):
        """Distance from Dallas to Austin is approximately 293 km."""
        dist = _event_scoring._haversine_km(32.7767, -96.7970, 30.2672, -97.7431)
        assert 250 < dist < 330

    def test_haversine_ny_to_la(self):
        """Distance from New York to Los Angeles is approximately 3940 km."""
        dist = _event_scoring._haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3800 < dist < 4100

    def test_score_price_free_is_max(self):
        """Free events get the maximum price score (20)."""
        Event = _event_models.Event
        event = Event(
            id="free-1", title="Free Event", source="allevents",
            price_range="Free",
        )
        score = _event_scoring._score_price_value(event)
        assert score == 20

    def test_score_price_zero_dollar(self):
        """$0 events also get maximum price score."""
        Event = _event_models.Event
        event = Event(
            id="zero-1", title="Zero Dollar Event", source="allevents",
            price_range="$0",
        )
        score = _event_scoring._score_price_value(event)
        assert score == 20

    def test_score_price_cheap(self):
        """Inexpensive events (<= $15) get high price score (18)."""
        Event = _event_models.Event
        event = Event(
            id="cheap-1", title="Cheap Event", source="allevents",
            price_range="$10",
        )
        score = _event_scoring._score_price_value(event)
        assert score == 18

    def test_score_price_expensive(self):
        """Very expensive events (>$200) get low price score (3)."""
        Event = _event_models.Event
        event = Event(
            id="expensive-1", title="Expensive Event", source="allevents",
            price_range="$250",
        )
        score = _event_scoring._score_price_value(event)
        assert score == 3

    def test_score_price_mid_range(self):
        """Mid-range events ($30-50) get score 12."""
        Event = _event_models.Event
        event = Event(
            id="mid-1", title="Mid Range Event", source="allevents",
            price_range="$35",
        )
        score = _event_scoring._score_price_value(event)
        assert score == 12

    def test_score_proximity_center(self):
        """Events within 5km of city center get max proximity score (15)."""
        Event = _event_models.Event
        event = Event(
            id="near-1", title="Nearby Event", source="allevents",
            lat=32.7800, lon=-96.8000,
        )
        score = _event_scoring._score_proximity(event, city_lat=32.7767, city_lon=-96.7970)
        assert score == 15

    def test_score_proximity_far(self):
        """Events far from city center get low proximity score (2)."""
        Event = _event_models.Event
        event = Event(
            id="far-1", title="Far Event", source="allevents",
            lat=29.7604, lon=-95.3698,  # Houston
        )
        score = _event_scoring._score_proximity(event, city_lat=32.7767, city_lon=-96.7970)
        assert score == 2

    def test_assign_scenario_music_date_night(self):
        """Music events default to date-night scenario."""
        Event = _event_models.Event
        event = Event(
            id="music-1", title="Jazz Night", source="allevents",
            category="music",
        )
        scenario = _event_scoring._assign_scenario(event)
        assert scenario == "date-night"

    def test_assign_scenario_outdoor_with_keywords(self):
        """Outdoor events with adventure keywords get weekend-adventure."""
        Event = _event_models.Event
        event = Event(
            id="outdoor-adv-1",
            title="Kayak Adventure on the Lake",
            description="Join us for a day trip kayaking and exploring.",
            category="outdoor",
            source="allevents",
            tags=["kayak", "adventure", "lake"],
            time_info="Morning",
        )
        scenario = _event_scoring._assign_scenario(event)
        # "kayak" matches weekend-adventure keywords,
        # "adventure" matches weekend-adventure keywords,
        # "day trip" in description matches weekend-adventure,
        # "lake" matches weekend-adventure
        assert scenario == "weekend-adventure"

    def test_assign_scenario_keyword_match(self):
        """Keywords in title/description influence scenario assignment."""
        Event = _event_models.Event
        event = Event(
            id="kw-1",
            title="Sunset Dinner Cruise",
            description="Romantic evening on the water with wine and jazz.",
            category="outdoor",
            source="allevents",
            tags=["sunset", "wine"],
            time_info="evening",
        )
        scenario = _event_scoring._assign_scenario(event)
        # "dinner", "wine", "sunset", "romantic", "jazz" match date-night
        # "evening" time hint matches date-night
        assert scenario == "date-night"

    def test_assign_camera_worthy_category(self):
        """Events in camera-worthy categories are flagged."""
        Event = _event_models.Event
        event = Event(
            id="cam-1",
            title="Sunset at the Park",
            description="Beautiful sunset views.",
            category="outdoor",
            source="allevents",
            venue="White Rock Lake Park",
        )
        is_worthy, note = _event_scoring._assign_camera(event)
        assert is_worthy is True
        assert note is not None
        assert len(note) > 0

    def test_assign_camera_not_worthy(self):
        """Non-photogenic categories without keywords are not camera-worthy."""
        Event = _event_models.Event
        event = Event(
            id="not-cam-1",
            title="Weekly Trivia Night",
            description="Come test your knowledge at the bar.",
            category="nightlife",
            source="allevents",
            venue="Joe's Bar",
        )
        is_worthy, note = _event_scoring._assign_camera(event)
        assert is_worthy is False

    def test_score_event_returns_scored_event(self):
        """score_event returns an Event with updated score and metadata."""
        Event = _event_models.Event
        event = Event(
            id="score-me-1",
            title="Dallas Art Fair",
            description="Contemporary art exhibition featuring galleries from around the world.",
            category="arts",
            source="allevents",
            city="Dallas",
            state="TX",
            lat=32.7800,
            lon=-96.8000,
            date_start="2025-07-05T10:00:00",
            time_info="Saturday, July 5 at 10:00 AM",
            price_range="$20",
            venue="Dallas Museum of Art",
        )
        scored = _event_scoring.score_event(
            event,
            city_lat=32.7767,
            city_lon=-96.7970,
            user_interests=["arts", "photography", "food"],
        )
        assert scored.score > 0
        assert scored.score <= 100
        assert scored.camera_worthy in (True, False)
        assert scored.scenario != ""
        assert scored.score >= 30

    def test_score_events_sorts_by_score_descending(self):
        """score_events returns events sorted by score descending."""
        Event = _event_models.Event
        e1 = Event(
            id="s1", title="Free Park Yoga", category="outdoor",
            source="allevents", lat=32.78, lon=-96.80, price_range="Free",
        )
        e2 = Event(
            id="s2", title="Expensive Gala", category="nightlife",
            source="facebook", lat=32.90, lon=-96.95, price_range="$500",
        )
        e3 = Event(
            id="s3", title="Photography Workshop", category="photography",
            source="allevents", lat=32.78, lon=-96.80, price_range="$25",
        )
        scored = _event_scoring.score_events(
            [e1, e2, e3],
            city_lat=32.7767,
            city_lon=-96.7970,
            user_interests=["photography", "outdoor", "food"],
        )
        assert len(scored) == 3
        for i in range(len(scored) - 1):
            assert scored[i].score >= scored[i + 1].score
        for event in scored:
            assert event.scenario != ""


# ── Test fetchers module ──────────────────────────────────────────────────────

class TestFetchers:
    """Tests for the event-agent fetchers package."""

    def test_fetchers_init_exports_all_expected(self):
        """fetchers/__init__.py exports the three expected functions."""
        fetcher_all = _event_fetchers.__all__
        assert "fetch_allevents_events" in fetcher_all
        assert "fetch_facebook_events" in fetcher_all
        assert "fetch_eventbrite_events_sync" in fetcher_all

    def test_fetchers_are_callable(self):
        """All exported fetcher functions are callable."""
        assert callable(_event_fetchers.fetch_allevents_events)
        assert callable(_event_fetchers.fetch_facebook_events)
        assert callable(_event_fetchers.fetch_eventbrite_events_sync)


# ── Test event-agent config module ────────────────────────────────────────────

class TestEventConfig:
    """Tests for the event-agent config module."""

    def test_data_dir_default(self):
        """DATA_DIR defaults to /app/data."""
        assert isinstance(_event_config.DATA_DIR, str)
        assert len(_event_config.DATA_DIR) > 0

    def test_fetch_days_ahead_is_positive_int(self):
        """FETCH_DAYS_AHEAD is a positive integer."""
        assert isinstance(_event_config.FETCH_DAYS_AHEAD, int)
        assert _event_config.FETCH_DAYS_AHEAD > 0

    def test_max_events_per_city_is_positive_int(self):
        """MAX_EVENTS_PER_CITY is a positive integer."""
        assert isinstance(_event_config.MAX_EVENTS_PER_CITY, int)
        assert _event_config.MAX_EVENTS_PER_CITY > 0

    def test_anti_detection_config_exists(self):
        """Anti-detection settings (delay, viewport, user-agent) are configured."""
        assert isinstance(_event_config.DELAY_MIN, float)
        assert isinstance(_event_config.DELAY_MAX, float)
        assert _event_config.DELAY_MIN <= _event_config.DELAY_MAX
        assert len(_event_config.VIEWPORT_POOL) > 0
        assert len(_event_config.USER_AGENT_POOL) > 0
        assert len(_event_config.BROWSER_ARGS) > 0
