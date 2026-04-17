"""
Configuration — loads API keys and settings from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# API Keys
TM_API_KEY = os.getenv("TM_API_KEY", "")
SG_CLIENT_ID = os.getenv("SG_CLIENT_ID", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
OTM_API_KEY = os.getenv("OTM_API_KEY", "")

# Server
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
ENV = os.getenv("ENV", "development")

# CORS — allowed origins for the frontend
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,https://*.netlify.app",
).split(",")

# Cache TTL in seconds (6 hours)
CACHE_TTL = int(os.getenv("CACHE_TTL", str(6 * 60 * 60)))

# Fetch settings
FETCH_DAYS_AHEAD = int(os.getenv("FETCH_DAYS_AHEAD", "14"))
FETCH_PAGE_SIZE = int(os.getenv("FETCH_PAGE_SIZE", "100"))
