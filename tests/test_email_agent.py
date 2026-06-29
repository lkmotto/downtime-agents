"""
Tests for the email-agent package.

Covers:
  - Model creation and validation (Event, CuratedWeekend)
  - Category mapping correctness
  - Email composition (subject, HTML, plain text)
  - Sender error handling
  - Configuration defaults
"""

import importlib.util
import os
import sys
import pytest
from datetime import datetime

_EMAIL_AGENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "email-agent")
)

# Ensure email-agent is on sys.path for modules that use plain "import X"
if _EMAIL_AGENT_DIR not in sys.path:
    sys.path.insert(0, _EMAIL_AGENT_DIR)


def _load_email_module(name, filename):
    """Load a module from email-agent/ by file path with a unique name."""
    filepath = os.path.join(_EMAIL_AGENT_DIR, filename)
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load email-agent/models.py under a unique name to avoid collision
# with event-agent/models.py
_email_models = _load_email_module("_email_agent_models", "models.py")
_email_config = _load_email_module("_email_agent_config", "config.py")


# ── Test Event model ──────────────────────────────────────────────────────────

class TestEventModel:
    """Tests for the email-agent Event Pydantic model."""

    def test_event_creation_with_minimal_fields(self):
        """Event can be created with only required fields."""
        Event = _email_models.Event
        event = Event(
            id="evt-001",
            title="DFW Photo Walk",
            source="ticketmaster",
        )
        assert event.id == "evt-001"
        assert event.title == "DFW Photo Walk"
        assert event.source == "ticketmaster"
        assert event.description == ""
        assert event.category == ""
        assert event.score == 0
        assert event.camera_worthy is False
        assert isinstance(event.tags, list)
        assert isinstance(event.created_at, datetime)

    def test_event_creation_with_all_fields(self):
        """Event can be created with all optional fields populated."""
        Event = _email_models.Event
        event = Event(
            id="evt-002",
            title="Jazz Night at The Balcony",
            description="An evening of smooth jazz overlooking the city.",
            category="music",
            scenario="date-night",
            source="seatgeek",
            source_url="https://example.com/jazz",
            venue="The Balcony Club",
            address="1825 Abrams Rd, Dallas, TX",
            city="Dallas",
            state="TX",
            lat=32.8140,
            lon=-96.7240,
            date_start="2025-06-27T20:00:00",
            date_end="2025-06-27T23:00:00",
            time_info="Friday, June 27 at 8:00 PM",
            price_range="$25",
            price_note="General admission",
            image_url="https://example.com/img.jpg",
            camera_worthy=True,
            camera_note="Low-light stage performance — perfect for testing high ISO limits.",
            tags=["jazz", "live-music", "date-night"],
            score=85,
            is_featured=True,
            email_category="Date Night",
            why_go="A perfect excuse to dress up and make a night of it.",
        )
        assert event.id == "evt-002"
        assert event.title == "Jazz Night at The Balcony"
        assert event.category == "music"
        assert event.scenario == "date-night"
        assert event.source == "seatgeek"
        assert event.lat == pytest.approx(32.8140)
        assert event.lon == pytest.approx(-96.7240)
        assert event.price_range == "$25"
        assert event.camera_worthy is True
        assert event.score == 85
        assert event.is_featured is True
        assert "jazz" in event.tags
        assert event.email_category == "Date Night"
        assert event.why_go.startswith("A perfect excuse")

    def test_event_default_values(self):
        """Event fields have sensible defaults."""
        Event = _email_models.Event
        event = Event(id="evt-003", title="Default Test", source="google")
        assert event.description == ""
        assert event.category == ""
        assert event.scenario == ""
        assert event.source_url == ""
        assert event.venue == ""
        assert event.lat == 0.0
        assert event.lon == 0.0
        assert event.price_range == ""
        assert event.camera_worthy is False
        assert event.tags == []
        assert event.score == 0
        assert event.is_featured is False
        assert event.email_category == ""
        assert event.why_go == ""


# ── Test CuratedWeekend ───────────────────────────────────────────────────────

class TestCuratedWeekend:
    """Tests for the CuratedWeekend dataclass."""

    def test_curated_weekend_creation(self):
        """CuratedWeekend can be created with buckets of events."""
        CuratedWeekend = _email_models.CuratedWeekend
        Event = _email_models.Event

        event_a = Event(
            id="evt-a",
            title="Outdoor Yoga",
            category="outdoor",
            source="ticketmaster",
        )
        event_b = Event(
            id="evt-b",
            title="Food Truck Fest",
            category="food",
            source="google",
        )

        weekend = CuratedWeekend(
            fetch_date=datetime(2025, 6, 26, 18, 0, 0),
            weekend_start="Friday, June 27",
            weekend_end="Sunday, June 29",
            city_label="Dallas\u2013Fort Worth",
            buckets={
                "Adventure / Outdoors": [event_a],
                "Food & Drink": [event_b],
            },
            total_fetched=150,
            total_scored=80,
        )

        assert weekend.weekend_start == "Friday, June 27"
        assert weekend.weekend_end == "Sunday, June 29"
        assert weekend.city_label == "Dallas\u2013Fort Worth"
        assert weekend.total_fetched == 150
        assert weekend.total_scored == 80
        assert len(weekend.buckets) == 2
        assert len(weekend.buckets["Adventure / Outdoors"]) == 1
        assert len(weekend.buckets["Food & Drink"]) == 1

    def test_all_events_property(self):
        """CuratedWeekend.all_events returns a flattened list."""
        CuratedWeekend = _email_models.CuratedWeekend
        Event = _email_models.Event

        e1 = Event(id="e1", title="E1", source="ticketmaster")
        e2 = Event(id="e2", title="E2", source="google")
        e3 = Event(id="e3", title="E3", source="seatgeek")

        weekend = CuratedWeekend(
            fetch_date=datetime.now(),
            weekend_start="Friday, June 27",
            weekend_end="Sunday, June 29",
            city_label="Dallas\u2013Fort Worth",
            buckets={
                "Date Night": [e1],
                "Arts & Culture": [e2, e3],
            },
            total_fetched=50,
            total_scored=30,
        )

        all_events = weekend.all_events
        assert len(all_events) == 3
        titles = {e.title for e in all_events}
        assert titles == {"E1", "E2", "E3"}

    def test_empty_buckets(self):
        """CuratedWeekend with empty buckets returns empty all_events."""
        CuratedWeekend = _email_models.CuratedWeekend

        weekend = CuratedWeekend(
            fetch_date=datetime.now(),
            weekend_start="Friday, June 27",
            weekend_end="Sunday, June 29",
            city_label="Dallas\u2013Fort Worth",
            buckets={},
        )
        assert weekend.all_events == []
        assert weekend.total_fetched == 0
        assert weekend.total_scored == 0


# ── Test category mappings ────────────────────────────────────────────────────

class TestCategoryMappings:
    """Tests for EMAIL_CATEGORIES, CATEGORY_BUCKET_MAP, CATEGORY_FALLBACK_MAP."""

    def test_email_categories_are_defined(self):
        """EMAIL_CATEGORIES list contains the expected categories."""
        cats = _email_models.EMAIL_CATEGORIES
        assert len(cats) == 5
        assert "Date Night" in cats
        assert "Adventure / Outdoors" in cats
        assert "Food & Drink" in cats
        assert "Arts & Culture" in cats
        assert "Free Things" in cats

    def test_category_bucket_map_keys_are_tuples(self):
        """All CATEGORY_BUCKET_MAP keys are (category, scenario) tuples."""
        bucket_map = _email_models.CATEGORY_BUCKET_MAP
        valid_values = {"Date Night", "Adventure / Outdoors", "Food & Drink", "Arts & Culture"}
        assert len(bucket_map) > 0
        for key, value in bucket_map.items():
            assert isinstance(key, tuple), f"Key {key!r} is not a tuple"
            assert len(key) == 2, f"Key {key!r} does not have 2 elements"
            assert isinstance(key[0], str)
            assert isinstance(key[1], str)
            assert value in valid_values

    def test_category_fallback_map_covers_common_categories(self):
        """CATEGORY_FALLBACK_MAP has entries for common event categories."""
        fallback = _email_models.CATEGORY_FALLBACK_MAP
        assert "music" in fallback
        assert "food" in fallback
        assert "outdoor" in fallback
        assert "arts" in fallback
        assert "festivals" in fallback
        assert fallback["music"] == "Date Night"
        assert fallback["outdoor"] == "Adventure / Outdoors"
        assert fallback["food"] == "Food & Drink"


# ── Test email composition ────────────────────────────────────────────────────

class TestEmailComposer:
    """Tests for the email_composer module."""

    @classmethod
    def setup_class(cls):
        """Import compose module once per class."""
        cls._composer = _load_email_module("_email_composer", "email_composer.py")

    def test_pick_subject_returns_non_empty_string(self):
        """pick_subject returns one of the known subject templates."""
        subject = self._composer.pick_subject()
        assert isinstance(subject, str)
        assert len(subject) > 0
        assert subject in self._composer.SUBJECT_TEMPLATES

    def test_compose_email_returns_expected_keys(self):
        """compose_email returns dict with subject, html, text keys."""
        CuratedWeekend = _email_models.CuratedWeekend
        Event = _email_models.Event

        event = Event(
            id="test-1",
            title="Test Event",
            source="google",
            venue="Test Venue",
            city="Dallas",
            state="TX",
            date_start="2025-06-28T10:00:00",
            time_info="Saturday, June 28 at 10:00 AM",
            price_range="Free",
            email_category="Free Things",
            why_go="A great free thing to do.",
        )
        weekend = CuratedWeekend(
            fetch_date=datetime.now(),
            weekend_start="Friday, June 27",
            weekend_end="Sunday, June 29",
            city_label="Dallas\u2013Fort Worth",
            buckets={"Free Things": [event]},
            total_fetched=10,
            total_scored=5,
        )

        result = self._composer.compose_email(weekend)
        assert isinstance(result, dict)
        assert "subject" in result
        assert "html" in result
        assert "text" in result
        assert len(result["subject"]) > 0
        assert len(result["html"]) > 0
        assert len(result["text"]) > 0

    def test_build_html_email_contains_expected_elements(self):
        """HTML email contains key structural elements."""
        CuratedWeekend = _email_models.CuratedWeekend
        Event = _email_models.Event

        event = Event(
            id="html-test-1",
            title="Downtown Photo Walk",
            description="Explore downtown with fellow photographers.",
            category="photography",
            source="google",
            source_url="https://example.com/photo-walk",
            venue="Main Street Garden",
            city="Dallas",
            state="TX",
            date_start="2025-06-28T09:00:00",
            time_info="Saturday, June 28 at 9:00 AM",
            price_range="Free",
            camera_worthy=True,
            email_category="Arts & Culture",
            why_go="Visually rich environment \u2014 the Lumix will love this one.",
        )
        weekend = CuratedWeekend(
            fetch_date=datetime.now(),
            weekend_start="Friday, June 27",
            weekend_end="Sunday, June 29",
            city_label="Dallas\u2013Fort Worth",
            buckets={"Arts & Culture": [event]},
            total_fetched=10,
            total_scored=8,
        )

        html = self._composer.build_html_email(weekend)
        assert "Dallas" in html
        assert "Downtown Photo Walk" in html
        assert "Friday, June 27" in html
        assert "Sunday, June 29" in html
        # FREE badge should appear for free events
        assert "FREE" in html
        assert "Camera-Worthy" in html
        # HTML structure checks
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_build_plain_text_contains_expected_elements(self):
        """Plain text email contains key content."""
        CuratedWeekend = _email_models.CuratedWeekend
        Event = _email_models.Event

        event = Event(
            id="text-test-1",
            title="Farmers Market",
            description="Local produce and crafts.",
            category="food",
            source="google",
            venue="Dallas Farmers Market",
            city="Dallas",
            state="TX",
            date_start="2025-06-28T08:00:00",
            time_info="Saturday, June 28 at 8:00 AM",
            price_range="Free",
            email_category="Food & Drink",
            why_go="Worth the drive \u2014 the food is the feature.",
            source_url="https://example.com/market",
        )
        weekend = CuratedWeekend(
            fetch_date=datetime.now(),
            weekend_start="Friday, June 27",
            weekend_end="Sunday, June 29",
            city_label="Dallas\u2013Fort Worth",
            buckets={"Food & Drink": [event]},
        )

        text = self._composer.build_plain_text(weekend)
        assert "DOWNTIME" in text
        assert "Farmers Market" in text
        assert "Friday, June 27" in text
        assert "Dallas Farmers Market" in text
        assert "Free" in text
        assert "https://example.com/market" in text


# ── Test sender module ────────────────────────────────────────────────────────

class TestSender:
    """Tests for the sender module."""

    @classmethod
    def setup_class(cls):
        """Import sender module once per class."""
        cls._sender = _load_email_module("_email_sender", "sender.py")

    def test_send_error_is_exception(self):
        """SendError is a proper Exception subclass."""
        SendError = self._sender.SendError
        error = SendError("Email delivery failed")
        assert isinstance(error, Exception)
        assert str(error) == "Email delivery failed"

    def test_send_error_can_be_raised_and_caught(self):
        """SendError can be raised and caught like a normal exception."""
        SendError = self._sender.SendError
        with pytest.raises(SendError, match="test error message"):
            raise SendError("test error message")

    def test_send_email_requires_api_key(self):
        """send_email raises ValueError when RESEND_API_KEY is not set."""
        send_email = self._sender.send_email
        with pytest.raises(ValueError, match="RESEND_API_KEY"):
            send_email(
                subject="Test Subject",
                html_body="<p>Hello</p>",
                text_body="Hello",
            )


# ── Test configuration module ─────────────────────────────────────────────────

class TestConfig:
    """Tests for the email-agent config module."""

    def test_config_defaults_are_sensible(self):
        """Config module loads with sensible default values."""
        assert _email_config.CITY == "Dallas"
        assert _email_config.STATE == "TX"
        assert isinstance(_email_config.CITY_LAT, float)
        assert isinstance(_email_config.CITY_LON, float)
        assert _email_config.CITY_LAT == pytest.approx(32.7767)
        assert _email_config.CITY_LON == pytest.approx(-96.7970)

        # Email defaults
        assert isinstance(_email_config.FROM_EMAIL, str)
        assert len(_email_config.FROM_EMAIL) > 0
        assert isinstance(_email_config.RECIPIENT_EMAIL, str)
        assert "@" in _email_config.RECIPIENT_EMAIL

        # Curation defaults
        assert _email_config.TOP_N_EVENTS == 10
        assert _email_config.FETCH_DAYS_AHEAD == 4
        assert _email_config.FETCH_PAGE_SIZE == 100

    def test_user_interests_is_list(self):
        """USER_INTERESTS is a non-empty list of strings."""
        interests = _email_config.USER_INTERESTS
        assert isinstance(interests, list)
        assert len(interests) > 0
        for interest in interests:
            assert isinstance(interest, str)

    def test_config_api_keys_default_to_empty(self):
        """API keys default to empty strings (no secrets leaked)."""
        assert _email_config.RESEND_API_KEY == ""
        assert _email_config.TM_API_KEY == ""
        assert _email_config.SG_CLIENT_ID == ""
        assert _email_config.SERPAPI_KEY == ""
        assert _email_config.OTM_API_KEY == ""
