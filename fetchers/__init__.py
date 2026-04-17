"""
Event fetchers for DownTime Agent.

Available fetchers:
  - allevents.fetch_allevents_events(city, state) -> list[Event]
  - facebook_events.fetch_facebook_events(city, state) -> list[Event]
  - eventbrite.fetch_eventbrite_events_sync(lat, lon) -> list[dict]
"""
from fetchers.allevents import fetch_allevents_events
from fetchers.facebook_events import fetch_facebook_events
from fetchers.eventbrite import fetch_eventbrite_events_sync

__all__ = [
    "fetch_allevents_events",
    "fetch_facebook_events",
    "fetch_eventbrite_events_sync",
]
