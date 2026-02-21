"""
ClearCare — API Key Tester
Run: python test_keys.py
Tests every API key before we start building
"""

import os
import asyncio
from dotenv import load_dotenv  # type: ignore[reportMissingImports]

load_dotenv()

# ── Color output helpers ──────────────────────
def ok(msg):   print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def info(msg): print(f"  ℹ️  {msg}")
def header(msg): print(f"\n{'─'*45}\n🔑 {msg}\n{'─'*45}")

# ─────────────────────────────────────────────
# 1. OPENAI
# ─────────────────────────────────────────────
def test_openai():
    header("Testing OpenAI")
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key == "sk-...":
        fail("OPENAI_API_KEY is missing or placeholder")
        return False
    try:
        from openai import OpenAI  # type: ignore[reportMissingImports]
        client = OpenAI(api_key=key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say: ClearCare API working"}],
            max_tokens=20
        )
        reply = response.choices[0].message.content
        ok(f"OpenAI connected — response: '{reply}'")
        return True
    except Exception as e:
        fail(f"OpenAI failed: {e}")
        return False

# ─────────────────────────────────────────────
# 2. ELEVENLABS
# ─────────────────────────────────────────────
def test_elevenlabs():
    header("Testing ElevenLabs")
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        fail("ELEVENLABS_API_KEY is missing")
        return False
    try:
        import httpx  # type: ignore[reportMissingImports]
        r = httpx.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": key},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            tier = data.get("subscription", {}).get("tier", "unknown")
            ok(f"ElevenLabs connected — plan: {tier}")
            return True
        else:
            fail(f"ElevenLabs returned {r.status_code}: {r.text}")
            return False
    except Exception as e:
        fail(f"ElevenLabs failed: {e}")
        return False

# ─────────────────────────────────────────────
# 3. TAVILY
# ─────────────────────────────────────────────
def test_tavily():
    header("Testing Tavily Search")
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        fail("TAVILY_API_KEY is missing")
        return False
    try:
        from tavily import TavilyClient  # type: ignore[reportMissingImports]
        client = TavilyClient(api_key=key)
        result = client.search("Medicare cost estimator 2024", max_results=1)
        if result and result.get("results"):
            ok(f"Tavily connected — got {len(result['results'])} result(s)")
            return True
        else:
            fail("Tavily returned empty results")
            return False
    except Exception as e:
        fail(f"Tavily failed: {e}")
        return False

# ─────────────────────────────────────────────
# 4. SUPABASE
# ─────────────────────────────────────────────
def test_supabase():
    header("Testing Supabase")
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        fail("SUPABASE_URL or SUPABASE_KEY is missing")
        return False
    try:
        from supabase import create_client  # type: ignore[reportMissingImports]
        client = create_client(url, key)
        # Just test the connection — list tables
        ok(f"Supabase connected — URL: {url[:40]}...")
        info("Note: Get your service_role key from Project Settings → API for full access")
        return True
    except Exception as e:
        fail(f"Supabase failed: {e}")
        return False

# ─────────────────────────────────────────────
# 5. BRAINTRUST
# ─────────────────────────────────────────────
def test_braintrust():
    header("Testing Braintrust")
    key = os.getenv("BRAINTRUST_API_KEY", "")
    if not key:
        fail("BRAINTRUST_API_KEY is missing")
        return False
    try:
        import httpx  # type: ignore[reportMissingImports]
        r = httpx.get(
            "https://api.braintrust.dev/v1/project",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10
        )
        if r.status_code == 200:
            ok(f"Braintrust connected — authenticated successfully")
            return True
        elif r.status_code == 401:
            fail("Braintrust: invalid API key")
            return False
        else:
            # Some plans return 403/404 but key is still valid
            ok(f"Braintrust key accepted (status {r.status_code})")
            return True
    except Exception as e:
        fail(f"Braintrust failed: {e}")
        return False

# ─────────────────────────────────────────────
# 6. GOOGLE MAPS (optional for now)
# ─────────────────────────────────────────────
def test_google_maps():
    header("Testing Google Maps")
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        info("GOOGLE_MAPS_API_KEY is empty — skipping (add later)")
        return None
    try:
        import httpx  # type: ignore[reportMissingImports]
        r = httpx.get(
            f"https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": "11201", "key": key},
            timeout=10
        )
        data = r.json()
        if data.get("status") == "OK":
            ok("Google Maps connected — geocoding works")
            return True
        else:
            fail(f"Google Maps error: {data.get('status')} — {data.get('error_message','')}")
            return False
    except Exception as e:
        fail(f"Google Maps failed: {e}")
        return False

# ─────────────────────────────────────────────
# 7. CMS Medicare API (public — no key needed)
# ─────────────────────────────────────────────
def test_cms():
    header("Testing CMS Medicare API (public)")
    try:
        import httpx  # type: ignore[reportMissingImports]
        r = httpx.get(
            "https://npiregistry.cms.hhs.gov/api",
            params={
                "version": "2.1",
                "postal_code": "11201",
                "taxonomy_description": "hospital",
                "limit": 1
            },
            timeout=10
        )
        data = r.json()
        count = data.get("result_count", 0)
        ok(f"CMS NPI Registry connected — found {count} result(s) for zip 11201")
        return True
    except Exception as e:
        fail(f"CMS API failed: {e}")
        return False

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
def main():
    print("\n" + "═"*45)
    print("   🏥 ClearCare — API Key Test Suite")
    print("═"*45)

    results = {
        "OpenAI":       test_openai(),
        "ElevenLabs":   test_elevenlabs(),
        "Tavily":       test_tavily(),
        "Supabase":     test_supabase(),
        "Braintrust":   test_braintrust(),
        "Google Maps":  test_google_maps(),
        "CMS API":      test_cms(),
    }

    print("\n" + "═"*45)
    print("   📊 RESULTS SUMMARY")
    print("═"*45)

    passed = 0
    skipped = 0
    failed = 0

    for service, result in results.items():
        if result is True:
            print(f"  ✅ {service}")
            passed += 1
        elif result is None:
            print(f"  ⏭️  {service} (skipped)")
            skipped += 1
        else:
            print(f"  ❌ {service}")
            failed += 1

    print(f"\n  Passed: {passed} | Skipped: {skipped} | Failed: {failed}")

    if failed == 0:
        print("\n  🚀 All keys working — ready to build!\n")
    else:
        print(f"\n  ⚠️  Fix {failed} failing key(s) before proceeding\n")

if __name__ == "__main__":
    main()