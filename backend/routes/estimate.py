# routes/estimate.py
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional

from agent.graph import run_agent
from agent.critique import run_critique_loop
from agent.memory import save_session, get_returning_user_context

router = APIRouter()


class EstimateRequest(BaseModel):
    care_needed:     str           = Field(..., min_length=2)
    zip_code:        str           = Field(..., min_length=5, max_length=10)
    insurance_input: str           = Field(default="")
    input_type:      str           = Field(default="text")
    file_path:       Optional[str] = Field(default="")
    medical_history: Optional[str] = Field(default="")
    session_id:      Optional[str] = Field(default="")


@router.post("/", response_model=None)
async def estimate(request: EstimateRequest, background_tasks: BackgroundTasks):

    # ── Session setup ─────────────────────────────────
    session_id = request.session_id or str(uuid.uuid4())
    user_context = get_returning_user_context(session_id)

    insurance_input = request.insurance_input
    if not insurance_input and user_context.get("is_returning"):
        insurance_input = user_context.get("insurance_input", "")

    zip_code = request.zip_code
    if not zip_code and user_context.get("zip_code"):
        zip_code = user_context.get("zip_code", "")

    if not request.care_needed:
        raise HTTPException(status_code=400, detail="care_needed is required")
    if not zip_code:
        raise HTTPException(status_code=400, detail="zip_code is required")

    # ── Run agent ─────────────────────────────────────
    try:
        agent_result = run_agent(
            insurance_input=insurance_input,
            care_needed=request.care_needed,
            zip_code=zip_code,
            input_type=request.input_type,
            file_path=request.file_path or "",
            medical_history=request.medical_history or "",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # ── Run critique ──────────────────────────────────
    has_insurance = bool(insurance_input)
    try:
        final_result = run_critique_loop(
            answer=agent_result,
            care_needed=request.care_needed,
            has_insurance=has_insurance,
        )
    except Exception as e:
        print(f"Critique error: {e}")
        final_result = agent_result
        final_result["score_history"] = []
        final_result["final_score"]   = 0
        final_result["iterations"]    = 0

    # ── Save session in background ────────────────────
    plan_details = final_result.get("plan_details", {})
    background_tasks.add_task(
        save_session,
        session_id=session_id,
        insurance_input=insurance_input,
        plan_details=plan_details,
        care_needed=request.care_needed,
        zip_code=zip_code,
    )

    # ── Map costs from hospitals ──────────────────────
    # node_generate_answer never sets in_network_cost directly
    # We derive it here from the hospitals list
    hospitals = final_result.get("hospitals", [])

    in_network  = [h for h in hospitals if h.get("network_status") in ("in-network", "accepts-medicare")]
    out_network = [h for h in hospitals if h.get("network_status") == "out-of-network"]

    in_network_cost     = in_network[0]["estimated_cost"]  if in_network  else None
    out_of_network_cost = out_network[0]["estimated_cost"] if out_network else None

    # Use whatever cost exists as the display cost
    # Priority: in-network > out-of-network > first hospital
    display_cost = (
        in_network_cost or
        out_of_network_cost or
        (hospitals[0]["estimated_cost"] if hospitals else None)
    )

    # Parse alternative cost from alternatives text
    alternative_cost        = final_result.get("alternative_cost")
    alternative_description = final_result.get("alternative_description")

    # If not set directly, try to parse from alternatives string
    if not alternative_cost and final_result.get("alternatives"):
        import re
        alt_text = str(final_result.get("alternatives", ""))
        match = re.search(r"\$?([\d,]+)", alt_text)
        if match:
            try:
                alternative_cost = float(match.group(1).replace(",", ""))
                alternative_description = alt_text[:100] if len(alt_text) > 10 else None
            except Exception:
                pass

    # ── Build response ────────────────────────────────
    return {
        "headline":                final_result.get("headline", f"Cost estimate for {request.care_needed}"),
        "spoken_summary":          final_result.get("spoken_summary", ""),
        "next_step":               final_result.get("next_step", ""),
        "in_network_cost":         display_cost,
        "out_of_network_cost":     out_of_network_cost,
        "alternative_cost":        alternative_cost,
        "alternative_description": alternative_description,
        "confidence":              float(final_result.get("confidence", 0.0)),
        "hospitals":               hospitals,
        "score_history":           final_result.get("score_history", []),
        "final_score":             final_result.get("final_score", 0),
        "iterations":              final_result.get("iterations", 0),
        "used_defaults":           final_result.get("used_defaults", False),
        "session_id":              session_id,
        "is_returning_user":       user_context.get("is_returning", False),
        "greeting":                user_context.get("greeting", ""),
    }


@router.get("/context/{session_id}")
async def get_context(session_id: str):
    return get_returning_user_context(session_id)


@router.delete("/session/{session_id}")
async def clear_user_session(session_id: str):
    from agent.memory import clear_session
    success = clear_session(session_id)
    return {"cleared": success, "session_id": session_id}