# config.py
# ─────────────────────────────────────────────────────
# Central configuration for ClearCare backend.
# All other files import settings from here.
# Never hardcode API keys anywhere else.
# ─────────────────────────────────────────────────────

import os
from dotenv import load_dotenv  # type: ignore[reportMissingImports]

# Load all variables from backend/.env into os.environ
# This must run before any os.getenv() calls
load_dotenv()

# ── LLM ───────────────────────────────────────────────
# GPT-4o handles vision (reading insurance cards, medical records)
# and powers the core agent reasoning
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Voice ─────────────────────────────────────────────
# ElevenLabs converts agent text responses into natural speech
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# This is the voice ID for "Rachel" — calm, clear, professional
# You can change this later from the ElevenLabs voice library
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

# ── Search ────────────────────────────────────────────
# Tavily gives the agent access to live web search
# Used for: insurance directories, drug prices, hospital info
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ── Maps ──────────────────────────────────────────────
# Google Maps renders the hospital map on the frontend
# Also used for geocoding zip codes into lat/lng coordinates
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── Database ──────────────────────────────────────────
# Supabase stores user sessions and insurance profiles
# So users don't have to re-enter their plan every time
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── Evals ─────────────────────────────────────────────
# Braintrust logs every self-critique loop
# Tracks confidence scores before and after rewrites
BRAINTRUST_API_KEY = os.getenv("BRAINTRUST_API_KEY", "")

# ── External APIs (no key needed — public) ────────────
# CMS NPI Registry: finds hospitals and providers by zip code
NPI_REGISTRY_URL = "https://npiregistry.cms.hhs.gov/api"

# CMS Medicare data: official plan pricing and coverage rules
CMS_BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

# ── App settings ──────────────────────────────────────
# Switches behavior between local dev and production
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Frontend URL — used for CORS (which requests are allowed in)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ── Safety check ──────────────────────────────────────
# This runs when config.py is imported — warns you immediately
# if a critical key is missing instead of failing silently later
def validate_config():
    required = {
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
        "TAVILY_API_KEY": TAVILY_API_KEY,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "BRAINTRUST_API_KEY": BRAINTRUST_API_KEY,
    }
    missing_keys = [key for key, value in required.items() if not value]
    if missing_keys:
        print(f" Warning: Missing environment variables: {missing_keys}")
    else:
        print(" All environment variables loaded successfully")