# test_memory.py
# Run: python test_memory.py

from agent.memory import save_session, load_session, get_returning_user_context, clear_session

TEST_SESSION_ID = "test-session-clearcare-001"

print("--- TEST 1: Save session ---")
success = save_session(
    session_id=TEST_SESSION_ID,
    insurance_input="I have Humana Gold Plus HMO",
    plan_details={
        "plan_name":         "Humana Gold Plus HMO",
        "plan_type":         "Medicare Advantage",
        "deductible":        250,
        "out_of_pocket_max": 4600,
        "coinsurance":       20,
    },
    care_needed="knee MRI",
    zip_code="11201"
)
print(f"Saved: {success}")

print("\n--- TEST 2: Load session ---")
session = load_session(TEST_SESSION_ID)
if session:
    print(f"Found session: {session['session_id']}")
    print(f"Insurance:     {session['insurance_input']}")
    print(f"Plan name:     {session['plan_details']['plan_name']}")
    print(f"Care history:  {session['care_history']}")
else:
    print("Session not found")

print("\n--- TEST 3: Returning user context ---")
context = get_returning_user_context(TEST_SESSION_ID)
print(f"Is returning:  {context['is_returning']}")
print(f"Greeting:      {context['greeting']}")
print(f"Care history:  {context['care_history']}")

print("\n--- TEST 4: Save second search ---")
save_session(
    session_id=TEST_SESSION_ID,
    insurance_input="I have Humana Gold Plus HMO",
    plan_details={"plan_name": "Humana Gold Plus HMO"},
    care_needed="colonoscopy",
    zip_code="11201"
)
session = load_session(TEST_SESSION_ID)
print(f"Care history now: {session['care_history']}")

print("\n--- TEST 5: Clear session ---")
cleared = clear_session(TEST_SESSION_ID)
print(f"Cleared: {cleared}")
session = load_session(TEST_SESSION_ID)
print(f"Session after clear: {session}")

print("\nAll memory tests done.")