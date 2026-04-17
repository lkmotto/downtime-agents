"""
Pydantic data models for DownTime backend.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Event(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str = ""  # music, sports, arts, food, outdoor, nightlife, film, festivals, photography, motorsports
    scenario: str = ""  # date-night, solo, weekend-adventure, travel
    source: str  # ticketmaster, seatgeek, google, opentripmap
    source_url: str = ""
    venue: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    lat: float = 0.0
    lon: float = 0.0
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    time_info: str = ""
    price_range: str = ""
    price_note: str = ""
    image_url: Optional[str] = None
    camera_worthy: bool = False
    camera_note: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    score: int = 0  # 0-100
    is_featured: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class City(BaseModel):
    name: str
    state: str
    lat: float
    lon: float


class UserPreferences(BaseModel):
    user_id: str
    city: str = ""
    interests: list[str] = Field(default_factory=list)
    saved_events: list[str] = Field(default_factory=list)
    dismissed_events: list[str] = Field(default_factory=list)


class EventsResponse(BaseModel):
    events: list[Event]
    total: int
    city: str
    state: str
    cached: bool = False


class CityResponse(BaseModel):
    cities: list[City]
    total: int


class HealthResponse(BaseModel):
    status: str
    version: str
    cache_size: int
    supported_cities: int
