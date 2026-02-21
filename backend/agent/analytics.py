# agent/analytics.py
from config import SUPABASE_URL, SUPABASE_KEY

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client # type: ignore[reportMissingImports]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def log_query(
    session_id:      str,
    symptoms:        str,
    care_needed:     str,
    zip_code:        str,
    insurance:       str,
    hospitals_found: int,
    confidence:      float,
    final_score:     int,
    used_defaults:   bool,
    urgency:         str,
):
    if not supabase:
        return
    try:
        supabase.table("clearcare_queries").insert({
            "session_id":      session_id,
            "symptoms":        symptoms,
            "care_needed":     care_needed,
            "zip_code":        zip_code,
            "insurance":       insurance,
            "hospitals_found": hospitals_found,
            "confidence":      confidence,
            "final_score":     final_score,
            "used_defaults":   used_defaults,
            "urgency":         urgency,
        }).execute()
    except Exception as e:
        print(f"Analytics log error: {e}")