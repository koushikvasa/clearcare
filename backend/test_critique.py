# test_critique.py
# Run: python test_critique.py

from agent.graph import run_agent
from agent.critique import run_critique_loop
import json

print("Running agent...")
answer = run_agent(
    insurance_input="I have Humana Gold Plus HMO",
    care_needed="knee MRI",
    zip_code="11201",
    input_type="text"
)

print("\nRunning critique loop...")
final = run_critique_loop(
    answer=answer,
    care_needed="knee MRI",
    has_insurance=True
)

print("\n--- SCORE PROGRESSION ---")
for s in final["score_history"]:
    iteration    = s["iteration"]
    completeness = s["completeness"]
    accuracy     = s["accuracy"]
    clarity      = s["clarity"]
    safety       = s["safety"]
    composite    = s["composite"]
    print(f"Iteration {iteration}: completeness={completeness} accuracy={accuracy} clarity={clarity} safety={safety} composite={composite}")

print("\n--- FINAL RESULT ---")
print(f"Final score:      {final['final_score']}/100")
print(f"Iterations used:  {final['iterations']}")
print(f"Spoken summary:   {final['spoken_summary']}")
print(f"Next step:        {final['next_step']}")