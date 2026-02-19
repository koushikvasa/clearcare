# routes/estimate.py
# POST /api/estimate — main endpoint for ClearCare.
#
# This is the single endpoint the frontend calls.
# It orchestrates the full pipeline:
# 1. Load returning user context from memory
# 2. Run the LangGraph agent
# 3. Run the self-critique loop
# 4. Save the session to memory
# 5. Return the complete result
#
# All other routes (voice, image) feed into this one.
# Voice transcribes audio and sends text here.
# Image parses the card and sends text here.

import uuid
from fastapi import APIRouter, HTTPException  # type: ignore[reportMissingImports]
from pydantic import BaseModel, Field  # type: ignore[reportMissingImports]
from typing import Optional

from agent.graph import run_agent
from agent.critique import run_critique_loop
from agent.memory import save_session, get_returning_user_context


# APIRouter is a mini FastAPI app
# It gets registered in main.py with the /api/estimate prefix
router = APIRouter()


# ── REQUEST MODEL ─────────────────────────────────────
# Defines exactly what the frontend must send.
# Pydantic validates this automatically before our code runs.
# If a required field is missing, FastAPI returns 422 automatically.

class EstimateRequest(BaseModel):
    # What care the user needs — required
    # Example: "knee MRI", "colonoscopy", "annual physical"
    care_needed: str = Field(
        ...,
        min_length=2,
        description="Medical procedure or care needed"
    )

    # 5-digit zip code for hospital search — required
    zip_code: str = Field(
        ...,
        min_length=5,
        max_length=10,
        description="User zip code for nearby hospital search"
    )

    # Insurance plan text — optional
    # Empty string triggers the default Medicare path
    insurance_input: str = Field(
        default="",
        description="Insurance plan name or description"
    )

    # How the insurance was provided — text, image, or pdf
    input_type: str = Field(
        default="text",
        description="text, image, or pdf"
    )

    # Path to uploaded file — only needed for image/pdf
    file_path: Optional[str] = Field(
        default="",
        description="Server path to uploaded insurance card or document"
    )

    # Optional medical history for severity assessment
    medical_history: Optional[str] = Field(
        default="",
        description="Past medical records or diagnoses text"
    )

    # Session ID from the frontend browser
    # Used to load/save memory across requests
    # If not provided we generate a new one
    session_id: Optional[str] = Field(
        default="",
        description="Browser session ID for memory"
    )


# ── RESPONSE MODEL ────────────────────────────────────
# Defines what we send back to the frontend.
# Optional fields may not always be present.

class HospitalResult(BaseModel):
    hospital:       str
    address:        str
    phone:          str
    network_status: str
    estimated_cost: float


class ScoreIteration(BaseModel):
    iteration:    int
    completeness: int
    accuracy:     int
    clarity:      int
    safety:       int
    composite:    int


class EstimateResponse(BaseModel):
    # Core answer fields
    headline:                str
    spoken_summary:          str
    next_step:               str
    in_network_cost:         Optional[float]
    out_of_network_cost:     Optional[float]
    alternative_cost:        Optional[float]
    alternative_description: Optional[str]
    confidence:              float

    # Hospital results for the map
    hospitals:               list[HospitalResult]

    # Self-critique data for the score meter
    score_history:           list[ScoreIteration]
    final_score:             int
    iterations:              int

    # Context flags
    used_defaults:           bool
    session_id:              str
    is_returning_user:       bool
    greeting:                Optional[str]


# ── MAIN ENDPOINT ─────────────────────────────────────

@router.post("/", response_model=None)
async def estimate(request: EstimateRequest):
    """
    Main ClearCare endpoint. Runs the full agent pipeline.

    Accepts insurance details and care needed, returns cost
    estimates, hospital matches, alternatives, and a spoken summary.

    The async keyword means FastAPI runs this without blocking
    other requests while it waits for LLM and API responses.
    Important for performance when multiple users hit the app.
    """

    # ── Step 1: Session setup ─────────────────────────
    # Generate a session ID if the frontend did not send one
    # This happens on first visit before any session exists
    session_id = request.session_id or str(uuid.uuid4())

    # Load returning user context
    # This checks if we have saved plan details for this session
    user_context = get_returning_user_context(session_id)

    # If user did not provide insurance but we have it saved,
    # use their saved insurance automatically
    insurance_input = request.insurance_input
    if not insurance_input and user_context.get("is_returning"):
        insurance_input = user_context.get("insurance_input", "")

    # Same for zip code
    zip_code = request.zip_code
    if not zip_code and user_context.get("zip_code"):
        zip_code = user_context.get("zip_code", "")

    # ── Step 2: Validate we have enough to work with ──
    if not request.care_needed:
        raise HTTPException(
            status_code=400,
            detail="care_needed is required. Example: 'knee MRI' or 'colonoscopy'"
        )

    if not zip_code:
        raise HTTPException(
            status_code=400,
            detail="zip_code is required for hospital search"
        )

    # ── Step 3: Run the agent ─────────────────────────
    # This triggers the full LangGraph pipeline:
    # extract_plan -> assess_severity -> find_hospitals ->
    # check_network -> estimate_cost -> find_alternatives ->
    # generate_answer
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
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {str(e)}"
        )

    # ── Step 4: Run the self-critique loop ────────────
    # Scores the answer and rewrites if below 80
    # Attaches score_history for the frontend meter
    has_insurance = bool(insurance_input)
    try:
        final_result = run_critique_loop(
            answer=agent_result,
            care_needed=request.care_needed,
            has_insurance=has_insurance,
        )
    except Exception as e:
        # Critique failure should not kill the response
        # Return the agent result without critique scores
        final_result = agent_result
        final_result["score_history"] = []
        final_result["final_score"]   = 0
        final_result["iterations"]    = 0

    # ── Step 5: Save session to memory ───────────────
    # Save in the background — don't let a memory failure
    # affect the response the user receives
    plan_details = final_result.get("plan_details", {})
    save_session(
        session_id=session_id,
        insurance_input=insurance_input,
        plan_details=plan_details,
        care_needed=request.care_needed,
        zip_code=zip_code,
    )

    # ── Step 6: Build and return response ────────────
    # Merge agent result with session context
    response = {
        # Core answer
        "headline":                final_result.get("headline", ""),
        "spoken_summary":          final_result.get("spoken_summary", ""),
        "next_step":               final_result.get("next_step", ""),
        "in_network_cost":         final_result.get("in_network_cost"),
        "out_of_network_cost":     final_result.get("out_of_network_cost"),
        "alternative_cost":        final_result.get("alternative_cost"),
        "alternative_description": final_result.get("alternative_description"),
        "confidence":              final_result.get("confidence", 0.0),

        # Hospitals for the map
        "hospitals": final_result.get("hospitals", []),

        # Self-critique data for the score meter
        "score_history": final_result.get("score_history", []),
        "final_score":   final_result.get("final_score", 0),
        "iterations":    final_result.get("iterations", 0),

        # Context
        "used_defaults":       final_result.get("used_defaults", False),
        "session_id":          session_id,
        "is_returning_user":   user_context.get("is_returning", False),
        "greeting":            user_context.get("greeting", ""),
    }

    return response


# ── CONTEXT ENDPOINT ──────────────────────────────────
# Lightweight endpoint the frontend calls on page load
# to check if this is a returning user and pre-fill their data

@router.get("/context/{session_id}")
async def get_context(session_id: str):
    """
    Returns saved context for a returning user.
    Called on page load to pre-fill insurance details.
    """
    context = get_returning_user_context(session_id)
    return context


# ── CLEAR SESSION ENDPOINT ────────────────────────────

@router.delete("/session/{session_id}")
async def clear_user_session(session_id: str):
    """
    Deletes all saved data for a session.
    Called when user clicks clear my data in the UI.
    """
    from agent.memory import clear_session
    success = clear_session(session_id)
    return {"cleared": success, "session_id": session_id}