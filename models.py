"""
Pydantic data models for DownTime Event Collection Agent.

Mirrors the backend models.py — keep in sync.
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
    source: str          # allevents, facebook
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
    score: int = 0        # 0-100 — set by scoring engine
    is_featured: bool = False
    attendee_count: Optional[int] = None   # Facebook-specific
    created_at: datetime = Field(default_factory=datetime.utcnow)
