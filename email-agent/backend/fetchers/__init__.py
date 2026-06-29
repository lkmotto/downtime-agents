"""
Event fetcher modules for DownTime.
Each fetcher handles one external API source.
"""
from fetchers.ticketmaster import fetch_ticketmaster_events
from fetchers.seatgeek import fetch_seatgeek_events
from fetchers.serpapi_google import fetch_google_events
from fetchers.opentripmap import fetch_opentripmap_places

__all__ = [
    "fetch_ticketmaster_events",
    "fetch_seatgeek_events",
    "fetch_google_events",
    "fetch_opentripmap_places",
]
