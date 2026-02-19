# agent/critique.py
# Self-improvement loop for ClearCare agent responses.
#
# How it works:
# 1. Take the agent's generated answer
# 2. Score it across 4 dimensions (0-100 each)
# 3. If composite score is below 80, rewrite with specific instructions
# 4. Repeat up to 3 times total
# 5. Return the best version with full score history
#
# The score history is what gets displayed live on the
# frontend as the confidence meter climbing.
# That is the demo moment that wins the hackathon.

import json
from langchain_openai import ChatOpenAI  # type: ignore[reportMissingImports]
from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore[reportMissingImports]

from config import OPENAI_API_KEY
from agent.prompts import SELF_CRITIQUE_PROMPT, COST_ESTIMATION_PROMPT


# Separate LLM instance for critique
# temperature=0 for consistent, deterministic scoring
critique_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=OPENAI_API_KEY
)

# Maximum rewrite attempts before we stop and return best version
MAX_ITERATIONS = 3

# Minimum composite score to stop rewriting
SCORE_THRESHOLD = 80


def parse_llm_json(raw: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code fences.

    LLMs sometimes wrap JSON in markdown fences like:
```json
    { ... }
```
    This strips those fences before parsing.
    Without this, json.loads fails on the first character.
    """
    text = raw.strip()

    # Remove opening fence (```json or ```)
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]

    # Remove closing fence
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0].strip()

    return json.loads(text)


def score_answer(answer: dict, care_needed: str, has_insurance: bool) -> dict:
    """
    Score the agent's answer across 4 quality dimensions.

    Dimensions:
    - completeness: did it answer everything the user asked
    - accuracy:     are cost figures reasonable and grounded in data
    - clarity:      would a non-expert Medicare patient understand this
    - safety:       does it include appropriate disclaimers

    Returns scores 0-100, composite score, whether rewrite is needed,
    and specific instructions for what to improve.
    """
    spoken        = answer.get("spoken_summary", "")
    headline      = answer.get("headline", "")
    hospitals     = answer.get("hospitals", [])
    used_defaults = answer.get("used_defaults", False)

    in_network_hospitals  = [h for h in hospitals if h.get("network_status") == "in-network"]
    out_network_hospitals = [h for h in hospitals if h.get("network_status") == "out-of-network"]

    content_to_score = f"""
HEADLINE: {headline}

SPOKEN SUMMARY: {spoken}

NEXT STEP: {answer.get("next_step", "none")}

STRUCTURED DATA:
- Hospitals found: {len(hospitals)}
- In-network hospitals: {len(in_network_hospitals)}
- Out-of-network hospitals: {len(out_network_hospitals)}
- In-network cost: ${answer.get("in_network_cost", "not provided")}
- Out-of-network cost: ${answer.get("out_of_network_cost", "not provided")}
- Alternative cost: ${answer.get("alternative_cost", "not provided")}
- Alternative description: {answer.get("alternative_description", "none")}
- Used default Medicare values: {used_defaults}
- Insurance info provided: {has_insurance}
- Confidence stated: {answer.get("confidence", "not stated")}

ACCURACY NOTE: If out-of-network hospitals is 0, do NOT penalize for
missing out-of-network costs. Score accuracy based on data that was
actually available, not what ideally should exist.
"""

    scoring_prompt = f"""
{SELF_CRITIQUE_PROMPT}

ADDITIONAL CONTEXT:
- User asked about: {care_needed}
- Insurance info provided: {has_insurance}
- Agent used default Medicare values: {used_defaults}

ANSWER TO SCORE:
{content_to_score}

SCORING NOTES:
- If used_defaults is True, the answer MUST mention this limitation
  to score full marks on safety
- If no out-of-network hospital was found, do not penalize accuracy
  for missing out-of-network cost
- The next_step must be specific and actionable, not generic
- Costs must be stated as estimates, not guarantees

Return valid JSON only. No markdown fences. No explanation.
"""

    try:
        response = critique_llm.invoke([
            HumanMessage(content=scoring_prompt)
        ])

        scores = parse_llm_json(response.content)

        # Handle both composite and composite_score field names
        # LLM sometimes returns one, sometimes the other
        if "composite_score" in scores and "composite" not in scores:
            scores["composite"] = scores["composite_score"]

        # Convert 0.0-1.0 floats to 0-100 integers for display
        completeness = round(scores.get("completeness", 0.7) * 100)
        accuracy     = round(scores.get("accuracy",     0.7) * 100)
        clarity      = round(scores.get("clarity",      0.7) * 100)
        safety       = round(scores.get("safety",       0.7) * 100)
        composite    = round((completeness + accuracy + clarity + safety) / 4)

        return {
            "completeness":          completeness,
            "accuracy":              accuracy,
            "clarity":               clarity,
            "safety":                safety,
            "composite":             composite,
            "needs_rewrite":         composite < SCORE_THRESHOLD,
            "weakest_dimension":     scores.get("weakest_dimension", "clarity"),
            "rewrite_instructions":  scores.get("rewrite_instructions", ""),
        }

    except Exception as e:
        # Scoring failed — return safe defaults that trigger a rewrite
        # We print the error so we can debug during development
        print(f"  Scoring error: {e}")
        return {
            "completeness":          70,
            "accuracy":              70,
            "clarity":               70,
            "safety":                70,
            "composite":             70,
            "needs_rewrite":         True,
            "weakest_dimension":     "unknown",
            "rewrite_instructions":  f"Scoring failed: {str(e)}. Rewrite for clarity and completeness.",
        }


def rewrite_answer(answer: dict, scores: dict, care_needed: str, iteration: int) -> dict:
    """
    Rewrite the answer based on critique scores and instructions.

    Takes the previous answer and specific improvement instructions
    and generates a better version.

    We pass the full previous answer so the LLM improves it
    rather than starting from scratch. This preserves what was
    already good while fixing the weak dimension.
    """
    weakest      = scores.get("weakest_dimension", "clarity")
    instructions = scores.get("rewrite_instructions", "Improve clarity and completeness.")

    rewrite_prompt = f"""
You are rewriting a Medicare cost estimate response to improve its quality.

PREVIOUS ANSWER TO IMPROVE:
Headline:       {answer.get("headline", "")}
Spoken summary: {answer.get("spoken_summary", "")}
Next step:      {answer.get("next_step", "")}
In-network cost:     ${answer.get("in_network_cost", "unknown")}
Out-of-network cost: ${answer.get("out_of_network_cost", "unknown")}
Alternative cost:    ${answer.get("alternative_cost", "unknown")}
Alternative:         {answer.get("alternative_description", "none")}
Used defaults:       {answer.get("used_defaults", False)}

QUALITY SCORES FROM REVIEW:
Completeness: {scores["completeness"]}/100
Accuracy:     {scores["accuracy"]}/100
Clarity:      {scores["clarity"]}/100
Safety:       {scores["safety"]}/100
Composite:    {scores["composite"]}/100

WEAKEST DIMENSION: {weakest}
SPECIFIC INSTRUCTIONS: {instructions}

THIS IS REWRITE ATTEMPT {iteration} of {MAX_ITERATIONS}.

REWRITE RULES:
- Focus on fixing the weakest dimension specifically
- Keep what was already scoring well
- spoken_summary must be under 120 words
- spoken_summary will be read aloud by a voice assistant
  to a Medicare patient, so write in plain conversational English
- Always state costs as estimates, not guarantees
- Always end with one specific, actionable next step
- If used_defaults is True, mention that real plan details
  would improve accuracy
- Do not use medical jargon without explaining it

Return the same JSON structure as before.
Return valid JSON only. No markdown fences. No explanation.

Required JSON fields:
headline, explanation, in_network_cost, out_of_network_cost,
alternative_cost, alternative_description, confidence,
spoken_summary, next_step
"""

    try:
        response = critique_llm.invoke([
            SystemMessage(content=COST_ESTIMATION_PROMPT),
            HumanMessage(content=rewrite_prompt)
        ])

        rewritten = parse_llm_json(response.content)

        # Preserve structured data from original answer
        # Only the text fields should change between rewrites
        rewritten["hospitals"]     = answer.get("hospitals", [])
        rewritten["plan_details"]  = answer.get("plan_details", {})
        rewritten["alternatives"]  = answer.get("alternatives", "")
        rewritten["used_defaults"] = answer.get("used_defaults", False)

        return rewritten

    except Exception as e:
        # If rewrite fails return original unchanged
        print(f"  Rewrite error: {e}")
        return answer


def run_critique_loop(answer: dict, care_needed: str, has_insurance: bool) -> dict:
    """
    Run the full self-critique and improvement loop.

    This is the only function called from outside this file.
    Route handlers call this after run_agent() completes.

    Args:
        answer:        Initial answer from run_agent()
        care_needed:   What the user asked about
        has_insurance: Whether real insurance info was provided

    Returns:
        Best answer found, with score_history attached.
        score_history is used by the frontend to animate
        the confidence meter climbing in real time.
    """
    score_history  = []
    current_answer = answer
    best_answer    = answer
    best_score     = 0

    for iteration in range(1, MAX_ITERATIONS + 1):

        print(f"Critique iteration {iteration}/{MAX_ITERATIONS}")

        # Score current answer
        scores = score_answer(current_answer, care_needed, has_insurance)

        # Record this iteration in history
        score_history.append({
            "iteration":    iteration,
            "completeness": scores["completeness"],
            "accuracy":     scores["accuracy"],
            "clarity":      scores["clarity"],
            "safety":       scores["safety"],
            "composite":    scores["composite"],
        })

        print(
            f"  completeness={scores['completeness']} "
            f"accuracy={scores['accuracy']} "
            f"clarity={scores['clarity']} "
            f"safety={scores['safety']} "
            f"composite={scores['composite']}"
        )

        # Track the best version seen so far
        if scores["composite"] > best_score:
            best_score  = scores["composite"]
            best_answer = current_answer

        # Stop early if we hit the threshold
        if not scores["needs_rewrite"]:
            print(f"  Score {scores['composite']} >= {SCORE_THRESHOLD}. Stopping early.")
            break

        # Stop if this was the last iteration
        if iteration == MAX_ITERATIONS:
            print(f"  Max iterations reached. Returning best version (score={best_score}).")
            break

        # Rewrite for next iteration
        print(f"  Score {scores['composite']} < {SCORE_THRESHOLD}. Rewriting...")
        current_answer = rewrite_answer(
            current_answer, scores, care_needed, iteration
        )

    # Attach score history to the best answer
    # Frontend uses this to animate the score meter
    best_answer["score_history"] = score_history
    best_answer["final_score"]   = best_score
    best_answer["iterations"]    = len(score_history)

    return best_answer