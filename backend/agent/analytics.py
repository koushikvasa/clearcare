# agent/analytics.py
# Logs every query to Supabase so the Lightdash dashboard stays live.
#
# Design notes:
# - Retries up to 3 times with backoff so a transient Supabase hiccup
#   doesn't silently drop a row.
# - Uses structured print lines (prefix [analytics]) so they're easy
#   to grep in Railway / production logs.
# - signal_confidence (0-100 int) is stored as a 0.0-1.0 float in the
#   existing `confidence` column so Lightdash averages stay meaningful.

import time
import traceback
from config import SUPABASE_URL, SUPABASE_KEY

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client  # type: ignore[reportMissingImports]
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[analytics] Supabase client initialized")
    except Exception as e:
        print(f"[analytics] Failed to init Supabase client: {e}")
else:
    print("[analytics] SUPABASE_URL or SUPABASE_KEY not set — logging disabled")


def log_query(
    session_id:        str,
    symptoms:          str,
    care_needed:       str,
    zip_code:          str,
    insurance:         str,
    hospitals_found:   int,
    confidence:        float,       # signal_confidence / 100 — NOT LLM self-report
    final_score:       int,
    used_defaults:     bool,
    urgency:           str,
    signal_confidence: int = 0,     # raw 0-100 signal score (for debugging)
):
    if not supabase:
        print("[analytics] Skipping log — Supabase not configured")
        return

    payload = {
        "session_id":      session_id,
        "symptoms":        symptoms,
        "care_needed":     care_needed,
        "zip_code":        zip_code,
        "insurance":       insurance,
        "hospitals_found": hospitals_found,
        "confidence":      round(confidence, 4),
        "final_score":     final_score,
        "used_defaults":   used_defaults,
        "urgency":         urgency,
    }

    for attempt in range(1, 4):
        try:
            supabase.table("clearcare_queries").insert(payload).execute()
            print(
                f"[analytics] Logged query — session={session_id[:8]}… "
                f"signal={signal_confidence}/100 hospitals={hospitals_found} "
                f"(attempt {attempt})"
            )
            return
        except Exception as e:
            print(f"[analytics] Insert attempt {attempt}/3 failed: {e}")
            print(traceback.format_exc())
            if attempt < 3:
                time.sleep(attempt * 1.5)   # 1.5 s, 3 s between retries

    print(
        f"[analytics] All 3 insert attempts failed — query lost. "
        f"session={session_id[:8]}… symptoms={symptoms[:40]}"
    )
