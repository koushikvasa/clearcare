# agent/memory.py
# Session memory for ClearCare using Supabase.
#
# Why memory matters:
# Without it every request starts from zero.
# The user re-enters their plan every time.
# With it the agent remembers their plan, zip code,
# and past searches across sessions.
#
# Two operations:
# save_session: called after every successful agent run
# load_session: called at the start of every new request
#
# Session ID is generated on the frontend and sent with
# every request. It is a simple UUID that lives in the
# browser's localStorage — no login required.

import json
from datetime import datetime
from typing import Optional

from supabase import create_client, Client  # type: ignore[reportMissingImports]
from config import SUPABASE_URL, SUPABASE_KEY


# Initialize Supabase client once at module level
# create_client takes the project URL and the anon/service key
# We use the service role key so we can read and write freely
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Name of the table we created in Supabase
TABLE = "sessions"


def save_session(
    session_id:      str,
    insurance_input: str,
    plan_details:    dict,
    care_needed:     str,
    zip_code:        str,
) -> bool:

    if not supabase:
        return None
    """
    Save or update a user session in Supabase.

    Called after every successful agent run so the user's
    plan details are remembered for next time.

    Uses upsert which means:
    - If session_id exists: update the row
    - If session_id is new: insert a new row
    This way we never create duplicate rows.

    Args:
        session_id:      Unique ID from the frontend (UUID)
        insurance_input: Raw insurance text the user entered
        plan_details:    Extracted plan details dict from the agent
        care_needed:     What procedure the user searched for
        zip_code:        User's zip code

    Returns:
        True if saved successfully, False if an error occurred
    """
    try:
        # Load existing session to get care history
        existing = load_session(session_id)

        # Build care history — a list of past searches
        # This lets us show "your recent searches" on the frontend
        care_history = []
        if existing and existing.get("care_history"):
            care_history = existing["care_history"]

        # Add current search to history if not already there
        if care_needed and care_needed not in care_history:
            care_history.append(care_needed)
            # Keep only the last 10 searches
            care_history = care_history[-10:]

        # Build the row to save
        # updated_at is set every time so we know when it was last used
        row = {
            "session_id":      session_id,
            "insurance_input": insurance_input,
            "plan_details":    plan_details,
            "care_history":    care_history,
            "zip_code":        zip_code,
            "updated_at":      datetime.utcnow().isoformat(),
        }

        # Upsert into Supabase
        # on_conflict tells Supabase what to do when session_id already exists
        supabase.table(TABLE).upsert(
            row,
            on_conflict="session_id"
        ).execute()

        return True

    except Exception as e:
        # Memory failures should never crash the main app
        # Log the error but return False gracefully
        print(f"Memory save error: {e}")
        return False


def load_session(session_id: str) -> Optional[dict]:
    """
    Load a user session from Supabase.

    Called at the start of every request to check if we
    already know this user's plan details.

    Args:
        session_id: Unique ID from the frontend

    Returns:
        Session dict if found, None if not found or error
    """
    try:
        response = (
            supabase.table(TABLE)
            .select("*")
            .eq("session_id", session_id)
            .single()               # returns one row or raises an error
            .execute()
        )

        # response.data contains the row as a dict
        if response.data:
            return response.data
        return None

    except Exception:
        # No session found is normal — return None quietly
        return None


def get_returning_user_context(session_id: str) -> dict:
    if not supabase:
        return {"is_returning": False, "greeting": ""}
    """
    Build a context dict for a returning user.

    This is what gets passed to the agent so it can
    pre-fill insurance details and personalize the response.

    Returns a dict with:
    - is_returning:     True if we have their data
    - insurance_input:  Their saved plan text
    - plan_details:     Their extracted plan details
    - zip_code:         Their saved zip code
    - care_history:     Their past searches
    - greeting:         A personalized message for the UI
    """
    session = load_session(session_id)

    if not session:
        return {
            "is_returning":    False,
            "insurance_input": "",
            "plan_details":    None,
            "zip_code":        "",
            "care_history":    [],
            "greeting":        "",
        }

    plan_name = ""
    if session.get("plan_details"):
        plan_name = session["plan_details"].get("plan_name", "")

    # Build a friendly greeting shown at the top of the UI
    # This makes the app feel personal and intelligent
    greeting = ""
    if plan_name:
        greeting = f"Welcome back. Using your {plan_name} plan."
    else:
        greeting = "Welcome back."

    return {
        "is_returning":    True,
        "insurance_input": session.get("insurance_input", ""),
        "plan_details":    session.get("plan_details"),
        "zip_code":        session.get("zip_code", ""),
        "care_history":    session.get("care_history", []),
        "greeting":        greeting,
    }


def clear_session(session_id: str) -> bool:
    if not supabase:
        return None
    """
    Delete a session from Supabase.

    Called when the user clicks "clear my data" in the UI.
    Important for privacy — users should always be able
    to delete their stored information.

    Args:
        session_id: Unique ID from the frontend

    Returns:
        True if deleted, False if error
    """
    try:
        supabase.table(TABLE).delete().eq(
            "session_id", session_id
        ).execute()
        return True
    except Exception as e:
        print(f"Memory clear error: {e}")
        return False