# agent/graph.py
import re
import json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END  # type: ignore
from langchain_openai import ChatOpenAI             # type: ignore
from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore
import httpx # type: ignore
from config import NPI_REGISTRY_URL, AIRIA_API_KEY, OPENAI_API_KEY
from agent.tools import (
    extract_plan_details,
    find_hospitals,
    check_network_status,
    estimate_cost,
    find_alternatives,
    ALL_TOOLS,
)
from agent.prompts import COST_ESTIMATION_PROMPT, SEVERITY_ASSESSMENT_PROMPT

# Use Airia gateway when AIRIA_API_KEY is set; otherwise direct OpenAI
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=AIRIA_API_KEY or OPENAI_API_KEY,
    base_url="https://api.airia.ai/v1" if AIRIA_API_KEY else None,
)


# ── SYMPTOM MAPPING PROMPT ────────────────────────────
SYMPTOM_MAPPING_PROMPT = """
You are a medical triage assistant helping Medicare patients understand what care they need.

Given a patient's description of their symptoms or health concern, identify:
1. The most likely medical procedure or care they need
2. A plain-English explanation of why their symptoms suggest this care
3. The urgency level

Return JSON only, no markdown:
{
  "care_needed": "knee MRI",
  "reason": "Chronic knee pain with difficulty climbing stairs suggests soft tissue damage such as a torn meniscus or ligament injury. An MRI is the standard diagnostic tool to confirm this.",
  "urgency": "routine"
}

Urgency options: "urgent" (within days), "soon" (within weeks), "routine" (within months)

If the input is already a specific medical procedure (like "knee MRI", "colonoscopy"), 
return it as-is with a brief explanation.
"""


# ── STATE ─────────────────────────────────────────────
class AgentState(TypedDict):
    insurance_input:     str
    input_type:          str
    care_needed:         str
    zip_code:            str
    file_path:           Optional[str]
    medical_history:     Optional[str]
    has_insurance:       Optional[bool]
    plan_details:        Optional[dict]
    symptom_reason:      Optional[str]
    urgency:             Optional[str]
    severity:            Optional[str]
    hospitals:           Optional[list]
    network_results:     Optional[list]
    cost_estimate:       Optional[dict]
    alternatives:        Optional[str]
    signal_confidence:   Optional[int]   # 0-100, computed from measurable signals
    confidence_signals:  Optional[dict]  # breakdown of what contributed
    final_answer:        Optional[dict]
    error:               Optional[str]


# ── HELPERS ───────────────────────────────────────────
def parse_dollar(text: str, label: str) -> float:
    try:
        for line in text.split("\n"):
            if label.lower() in line.lower():
                match = re.search(r"\$?([\d,]+\.?\d*)", line)
                if match:
                    return float(match.group(1).replace(",", ""))
    except Exception:
        pass
    return 0.0

def parse_percent(text: str, label: str) -> float:
    try:
        for line in text.split("\n"):
            if label.lower() in line.lower():
                match = re.search(r"([\d.]+)%", line)
                if match:
                    return float(match.group(1))
    except Exception:
        pass
    return 20.0

def parse_field(text: str, label: str) -> str:
    try:
        for line in text.split("\n"):
            if label.lower() in line.lower():
                value = line.split(":", 1)[-1].strip()
                if value and value not in ("None", "Not found"):
                    return value
    except Exception:
        pass
    return ""

def parse_hospitals(text: str) -> list:
    hospitals = []
    blocks = text.split("---")
    for block in blocks:
        if "Name:" not in block:
            continue
        hospital = {}
        for line in block.strip().split("\n"):
            if line.startswith("Name:"):
                hospital["hospital"] = line.replace("Name:", "").strip()
            elif line.startswith("Address:"):
                hospital["address"] = line.replace("Address:", "").strip()
            elif line.startswith("Phone:"):
                hospital["phone"] = line.replace("Phone:", "").strip()
            elif line.startswith("NPI:"):
                hospital["npi"] = line.replace("NPI:", "").strip()
        if hospital.get("hospital"):
            hospitals.append(hospital)
    return hospitals


# ── DEFAULT PLAN ──────────────────────────────────────
DEFAULT_PLAN = {
    "plan_name":          "Original Medicare (Part A/B)",
    "plan_type":          "Original Medicare",
    "insurance_company":  "Medicare",
    "deductible":         240,
    "out_of_pocket_max":  None,
    "copay_primary_care": 0,
    "copay_specialist":   0,
    "coinsurance":        20,
    "is_default":         True,
}


# ── NODES ─────────────────────────────────────────────

def node_check_inputs(state: AgentState) -> dict:
    raw = state.get("insurance_input", "").strip()
    no_insurance_signals = {"none", "no", "skip", "n/a", "na", "unknown", ""}
    has_insurance = len(raw) > 5 and raw.lower() not in no_insurance_signals
    return {"has_insurance": has_insurance}


def node_extract_plan(state: AgentState) -> dict:
    result = extract_plan_details.invoke({
        "input_type": state["input_type"],
        "text_input": state["insurance_input"],
        "file_path":  state.get("file_path", "")
    })
    return {"plan_details": {
        "raw_output":         result,
        "plan_name":          parse_field(result, "Plan Name:"),
        "plan_type":          parse_field(result, "Plan Type:"),
        "insurance_company":  parse_field(result, "Insurance Company:"),
        "deductible":         parse_dollar(result, "Deductible:"),
        "out_of_pocket_max":  parse_dollar(result, "Out-of-Pocket Max:"),
        "copay_specialist":   parse_dollar(result, "Copay Specialist:"),
        "copay_primary_care": parse_dollar(result, "Copay Primary Care:"),
        "coinsurance":        parse_percent(result, "Coinsurance:"),
        "is_default":         False,
    }}


def node_use_defaults(state: AgentState) -> dict:
    return {"plan_details": DEFAULT_PLAN}


def node_map_symptoms(state: AgentState) -> dict:
    """
    Node 3: Map patient symptoms to medical procedure.
    If input looks like a procedure already, pass through with explanation.
    If input is symptoms, use GPT-4o to identify the likely procedure.
    """
    symptoms = state.get("care_needed", "").strip()

    # Keywords that indicate it's already a procedure name
    procedure_keywords = [
        "mri", "ct scan", "ct", "xray", "x-ray", "colonoscopy",
        "ultrasound", "surgery", "scan", "biopsy", "endoscopy",
        "mammogram", "echocardiogram", "ekg", "ecg", "dialysis",
        "chemotherapy", "radiation", "physical therapy", "blood test"
    ]

    # Even if it's a procedure, still run through GPT to get the reason
    # so AI Analysis can explain it to the user
    try:
        response = llm.invoke([
            SystemMessage(content=SYMPTOM_MAPPING_PROMPT),
            HumanMessage(content=f"Patient description: {symptoms}")
        ])

        # Strip markdown fences if present
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        return {
            "care_needed":    data.get("care_needed", symptoms),
            "symptom_reason": data.get("reason", ""),
            "urgency":        data.get("urgency", "routine"),
        }

    except Exception as e:
        print(f"ERROR node_map_symptoms: {e}")
        # Fallback — use original text, no reason
        return {
            "care_needed":    symptoms,
            "symptom_reason": "",
            "urgency":        "routine",
        }


def node_assess_severity(state: AgentState) -> dict:
    history = state.get("medical_history", "").strip()
    if not history:
        return {"severity": "moderate"}
    response = llm.invoke([
        SystemMessage(content=SEVERITY_ASSESSMENT_PROMPT),
        HumanMessage(content=f"Medical history:\n{history}")
    ])
    try:
        data = json.loads(response.content)
        return {"severity": data.get("severity", "moderate")}
    except Exception:
        return {"severity": "moderate"}


def node_find_hospitals(state: AgentState) -> dict:
    zip_code = state.get("zip_code", "")
    care     = state.get("care_needed", "").lower()

    specialty_map = {
        "mri":         "radiology",
        "ct scan":     "radiology",
        "x-ray":       "radiology",
        "ultrasound":  "radiology",
        "heart":       "cardiology",
        "cardiac":     "cardiology",
        "surgery":     "surgery",
        "mental":      "psychiatry",
        "therapy":     "physical therapy",
        "colonoscopy": "gastroenterology",
        "endoscopy":   "gastroenterology",
        "orthopedic":  "orthopedics",
        "knee":        "orthopedics",
        "hip":         "orthopedics",
        "back":        "orthopedics",
        "spine":       "orthopedics",
        "chest":       "cardiology",
        "breathing":   "pulmonology",
        "lung":        "pulmonology",
        "stomach":     "gastroenterology",
        "digestive":   "gastroenterology",
        "vision":      "ophthalmology",
        "eye":         "ophthalmology",
        "skin":        "dermatology",
        "rash":        "dermatology",
    }

    specialty = "hospital"
    for keyword, spec in specialty_map.items():
        if keyword in care:
            specialty = spec
            break

    def _fetch(params: dict) -> list:
        try:
            r = httpx.get(NPI_REGISTRY_URL, params=params, timeout=10)
            r.raise_for_status()
            return r.json().get("results", [])
        except Exception:
            return []

    def _parse(results: list) -> list:
        hospitals = []
        for p in results:
            basic = p.get("basic", {})
            addr  = (p.get("addresses") or [{}])[0]
            name  = (
                basic.get("organization_name") or
                f"Dr. {basic.get('first_name','')} {basic.get('last_name','')}".strip()
            )
            if not name or name.strip() == "Dr.":
                continue
            hospitals.append({
                "hospital":       name.strip(),
                "address":        f"{addr.get('address_1','')}, {addr.get('city','')}, {addr.get('state','')} {addr.get('postal_code','')}".strip(", "),
                "phone":          addr.get("telephone_number", "N/A"),
                "npi":            p.get("number", ""),
                "network_status": "unknown",
                "estimated_cost": 0,
            })
        return hospitals

    hospitals = []
    base = {"version": "2.1", "postal_code": zip_code, "limit": 8}

    # Tier 1: organizations matching the specialty
    if specialty != "hospital":
        results = _fetch({**base, "taxonomy_description": specialty, "entity_type_code": "2"})
        hospitals = _parse(results)

    # Tier 2: any organization (hospital) in this zip
    if not hospitals:
        results = _fetch({**base, "taxonomy_description": "hospital", "entity_type_code": "2"})
        hospitals = _parse(results)

    # Tier 3: any provider (individual or org) in this zip, no specialty filter
    if not hospitals:
        results = _fetch({**base})
        hospitals = _parse(results)

    # Tier 4: try a broader 3-digit zip prefix area
    if not hospitals and len(zip_code) >= 3:
        results = _fetch({"version": "2.1", "postal_code": zip_code[:3], "limit": 5})
        hospitals = _parse(results)

    return {"hospitals": hospitals}


def node_check_network(state: AgentState) -> dict:
    hospitals    = state.get("hospitals", []) or []
    plan_details = state.get("plan_details", {}) or {}
    plan_name    = plan_details.get("plan_name", "")
    plan_type    = (plan_details.get("plan_type") or "").lower()
    is_default   = plan_details.get("is_default", False)
    insurer      = plan_details.get("insurance_company", "")
    zip_code     = state.get("zip_code", "")

    # Original Medicare and Medicare Supplement don't have networks —
    # providers either accept Medicare assignment or they don't.
    # Since NPI-registered hospitals are required to accept assignment,
    # any provider we found in the NPI registry accepts Medicare.
    is_original_medicare = (
        is_default
        or "original medicare" in plan_type
        or "supplement" in plan_type
        or "medigap" in plan_type
        or ("medicare" in plan_type and "advantage" not in plan_type)
    )

    network_results = []

    for hospital in hospitals[:4]:
        name = hospital.get("hospital", "")
        if not name:
            continue

        if is_original_medicare:
            # No network concept — NPI-registered = accepts Medicare
            status = "accepts-medicare"
            print(f"[network] {name[:40]} -> accepts-medicare (Original Medicare plan)")

        else:
            # Medicare Advantage: try Tavily, fall back gracefully
            try:
                result = check_network_status.invoke({
                    "hospital_name":    name,
                    "insurance_plan":   plan_name,
                    "insurance_company": insurer,
                    "zip_code":         zip_code,
                })
                raw = result.lower()
                # Sanitize to ASCII before printing — Tavily content can contain
                # Unicode arrows/symbols that crash on Windows cp1252 consoles
                safe = result[:120].encode("ascii", errors="replace").decode()
                print(f"[network] {name[:40]} -> {safe}")

                if "out-of-network" in raw and "in-network" not in raw:
                    status = "out-of-network"
                elif "in-network" in raw or "in network" in raw:
                    status = "in-network"
                else:
                    # Could not determine — for MA plans default to in-network
                    # with a note. Most major hospitals are in-network for MA.
                    status = "accepts-medicare"
                    print(f"[network] {name[:40]} -> unclear, defaulting to accepts-medicare")

            except Exception as e:
                print(f"[network] ERROR check_network for {name[:40]}: {e}")
                status = "accepts-medicare"

        network_results.append({
            "hospital": name,
            "address":  hospital.get("address", ""),
            "phone":    hospital.get("phone", "N/A"),
            "status":   status,
        })

    return {"network_results": network_results}


def node_estimate_cost(state: AgentState) -> dict:
    plan_details    = state.get("plan_details", {})
    network_results = state.get("network_results", []) or []
    care            = state.get("care_needed", "")
    severity        = state.get("severity", "moderate")
    plan_name       = plan_details.get("plan_name", "Original Medicare")

    cost_results = []

    for hospital in network_results:
        name = hospital.get("hospital", "")
        try:
            result = estimate_cost.invoke({
                "procedure":      care,
                "insurance_plan": plan_name,
                "network_status": hospital["status"],
                "severity":       severity,
                "deductible":     float(plan_details.get("deductible") or 240),
                "coinsurance":    float(plan_details.get("coinsurance") or 20),
                "copay":          float(plan_details.get("copay_specialist") or 0),
                "deductible_met": False,
            })
            cost           = parse_dollar(result, "Your estimated cost:")
            breakdown      = parse_field(result, "Cost breakdown:")
            # Full Medicare benchmark rate before insurance — used for savings calc
            procedure_cost = parse_dollar(result, "Severity-adjusted cost:")
        except Exception as e:
            print(f"ERROR estimate_cost for {name}: {e}")
            cost           = 0
            breakdown      = ""
            procedure_cost = 0

        cost_results.append({
            "hospital":        name,
            "address":         hospital.get("address", ""),
            "phone":           hospital.get("phone", "N/A"),
            "network_status":  hospital["status"],
            "estimated_cost":  cost,
            "cost_breakdown":  breakdown,
            "procedure_cost":  procedure_cost,
        })

    cost_results.sort(key=lambda x: x["estimated_cost"] if x["estimated_cost"] > 0 else 9999)

    return {"cost_estimate": {"hospitals": cost_results}}


def node_find_alternatives(state: AgentState) -> dict:
    care      = state.get("care_needed", "")
    zip_code  = state.get("zip_code", "")
    hospitals = (state.get("cost_estimate") or {}).get("hospitals", [])
    cheapest  = hospitals[0]["estimated_cost"] if hospitals and hospitals[0]["estimated_cost"] > 0 else 500.0

    try:
        result = find_alternatives.invoke({
            "procedure":    care,
            "zip_code":     zip_code,
            "current_cost": cheapest
        })
    except Exception as e:
        print(f"ERROR find_alternatives: {e}")
        result = "No alternatives found."

    return {"alternatives": result}


def compute_signal_confidence(state: AgentState) -> tuple[int, dict]:
    """
    Compute confidence 0-100 from measurable facts, not LLM self-assessment.

    Signals and maximum points:
      providers_found      25 pts  — did NPI return any hospitals?
      insurance_recognized 20 pts  — did we parse a real plan (not defaults)?
      procedure_mapped     20 pts  — did GPT explain WHY the symptom → procedure?
      network_checked      15 pts  — did at least one provider accept the plan?
      costs_calculated     10 pts  — did we produce a non-zero cost figure?
      urgency_set          10 pts  — did we identify urgency level?
    Total max: 100

    Returned as (score: int, signals: dict) so the full breakdown
    can be shown in the UI and stored for debugging.
    """
    hospitals      = (state.get("cost_estimate") or {}).get("hospitals", [])
    plan_details   = state.get("plan_details") or {}
    urgency        = state.get("urgency") or ""
    symptom_reason = state.get("symptom_reason") or ""

    signals: dict = {}

    # ── providers_found ──────────────────────────────
    n = len(hospitals)
    if n >= 4:
        signals["providers_found"] = 25
    elif n >= 1:
        signals["providers_found"] = 15
    else:
        signals["providers_found"] = 0

    # ── insurance_recognized ─────────────────────────
    # is_default=True means we fell back to standard Medicare values
    signals["insurance_recognized"] = 0 if plan_details.get("is_default", True) else 20

    # ── procedure_mapped ─────────────────────────────
    # symptom_reason means GPT explained the symptom→procedure link
    if len(symptom_reason) > 20:
        signals["procedure_mapped"] = 20
    elif state.get("care_needed"):
        signals["procedure_mapped"] = 10
    else:
        signals["procedure_mapped"] = 0

    # ── network_checked ──────────────────────────────
    in_network = [
        h for h in hospitals
        if h.get("network_status") in ("in-network", "accepts-medicare")
    ]
    signals["network_checked"] = 15 if in_network else 0

    # ── costs_calculated ─────────────────────────────
    with_cost = [h for h in hospitals if (h.get("estimated_cost") or 0) > 0]
    signals["costs_calculated"] = 10 if with_cost else 0

    # ── urgency_set ──────────────────────────────────
    signals["urgency_set"] = 10 if urgency else 0

    score = sum(signals.values())
    return score, signals


def node_generate_answer(state: AgentState) -> dict:
    plan_details    = state.get("plan_details", {})
    hospitals       = (state.get("cost_estimate") or {}).get("hospitals", [])
    alternatives    = state.get("alternatives", "")
    care            = state.get("care_needed", "")
    is_default      = plan_details.get("is_default", False)
    symptom_reason  = state.get("symptom_reason", "")
    urgency         = state.get("urgency", "routine")

    in_network  = [h for h in hospitals if h["network_status"] in ("in-network", "accepts-medicare")]
    out_network = [h for h in hospitals if h["network_status"] == "out-of-network"]
    cheapest_in  = in_network[0]  if in_network  else None
    cheapest_out = out_network[0] if out_network else None

    cheapest_in_phone  = (cheapest_in  or {}).get("phone", "N/A")
    cheapest_out_phone = (cheapest_out or {}).get("phone", "N/A")
    top_hospital_name  = (cheapest_in or (hospitals[0] if hospitals else {})).get("hospital", "")
    top_hospital_phone = (cheapest_in or (hospitals[0] if hospitals else {})).get("phone", "N/A")
    plan_name_str      = plan_details.get("plan_name", "Original Medicare")

    # Build a concrete next_step template so the LLM doesn't fall back to "call your doctor"
    if top_hospital_phone and top_hospital_phone != "N/A":
        next_step_template = (
            f"Call {top_hospital_name} at {top_hospital_phone} to schedule a {care}. "
            f"Let them know you have {plan_name_str} so they can confirm coverage before you come in."
        )
    else:
        next_step_template = (
            f"Contact {top_hospital_name} to schedule a {care} "
            f"and confirm they accept {plan_name_str} before booking."
        )

    context = f"""
Patient symptoms/description: {state.get("care_needed", "")}
Identified procedure: {care}
Symptom analysis: {symptom_reason}
Urgency: {urgency}
Insurance plan: {plan_name_str}
Plan type: {plan_details.get("plan_type", "unknown")}
Deductible: ${plan_details.get("deductible", "unknown")}
Out-of-pocket max: ${plan_details.get("out_of_pocket_max", "no limit")}
Using default values: {is_default}

CHEAPEST COVERED OPTION:
{f"{cheapest_in['hospital']} | phone: {cheapest_in_phone} | cost: ${cheapest_in['estimated_cost']}" if cheapest_in else "None found"}

CHEAPEST OUT-OF-NETWORK:
{f"{cheapest_out['hospital']} | phone: {cheapest_out_phone} | cost: ${cheapest_out['estimated_cost']}" if cheapest_out else "None found"}

ALL OPTIONS:
{json.dumps(hospitals, indent=2)}

CHEAPER ALTERNATIVES:
{alternatives}

REQUIRED NEXT STEP (use this exactly, only improve the wording slightly if needed):
{next_step_template}
"""

    try:
        response = llm.invoke([
            SystemMessage(content=COST_ESTIMATION_PROMPT),
            HumanMessage(content=context)
        ])
        try:
            answer = json.loads(response.content)
        except Exception:
            answer = {
                "spoken_summary": response.content,
                "headline":       f"Cost estimate for {care}",
                "confidence":     0.75
            }
    except Exception as e:
        print(f"ERROR node_generate_answer: {e}")
        answer = {
            "spoken_summary": f"We found {len(hospitals)} providers near you for {care}.",
            "headline":       f"Cost estimate for {care}",
            "confidence":     0.5
        }

    # Compute signal-based confidence from measurable facts
    sig_score, sig_signals = compute_signal_confidence(state)

    answer["hospitals"]           = hospitals
    answer["plan_details"]        = plan_details
    answer["alternatives"]        = alternatives
    answer["used_defaults"]       = is_default
    answer["symptom_reason"]      = symptom_reason
    answer["urgency"]             = urgency
    answer["signal_confidence"]   = sig_score
    answer["confidence_signals"]  = sig_signals

    return {
        "final_answer":       answer,
        "signal_confidence":  sig_score,
        "confidence_signals": sig_signals,
    }


# ── ROUTING ───────────────────────────────────────────
def route_after_check(state: AgentState) -> str:
    return "extract_plan" if state.get("has_insurance") else "use_defaults"


# ── GRAPH ASSEMBLY ────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("check_inputs",      node_check_inputs)
    graph.add_node("extract_plan",      node_extract_plan)
    graph.add_node("use_defaults",      node_use_defaults)
    graph.add_node("map_symptoms",      node_map_symptoms)      # NEW
    graph.add_node("assess_severity",   node_assess_severity)
    graph.add_node("find_hospitals",    node_find_hospitals)
    graph.add_node("check_network",     node_check_network)
    graph.add_node("estimate_cost",     node_estimate_cost)
    graph.add_node("find_alternatives", node_find_alternatives)
    graph.add_node("generate_answer",   node_generate_answer)

    graph.add_edge(START, "check_inputs")

    graph.add_conditional_edges("check_inputs", route_after_check, {
        "extract_plan": "extract_plan",
        "use_defaults": "use_defaults",
    })

    # Both paths now go to map_symptoms first
    graph.add_edge("extract_plan",      "map_symptoms")         # changed
    graph.add_edge("use_defaults",      "map_symptoms")         # changed
    graph.add_edge("map_symptoms",      "assess_severity")      # new
    graph.add_edge("assess_severity",   "find_hospitals")
    graph.add_edge("find_hospitals",    "check_network")
    graph.add_edge("check_network",     "estimate_cost")
    graph.add_edge("estimate_cost",     "find_alternatives")
    graph.add_edge("find_alternatives", "generate_answer")
    graph.add_edge("generate_answer",   END)

    return graph.compile()


agent = build_graph()


# ── PUBLIC INTERFACE ──────────────────────────────────
def run_agent(
    insurance_input: str,
    care_needed:     str,
    zip_code:        str,
    input_type:      str = "text",
    file_path:       str = "",
    medical_history: str = ""
) -> dict:
    initial_state: AgentState = {
        "insurance_input":    insurance_input,
        "input_type":         input_type,
        "care_needed":        care_needed,
        "zip_code":           zip_code,
        "file_path":          file_path,
        "medical_history":    medical_history,
        "has_insurance":      None,
        "plan_details":       None,
        "symptom_reason":     None,
        "urgency":            None,
        "severity":           None,
        "hospitals":          None,
        "network_results":    None,
        "cost_estimate":      None,
        "alternatives":       None,
        "signal_confidence":  None,
        "confidence_signals": None,
        "final_answer":       None,
        "error":              None,
    }
    try:
        final_state = agent.invoke(initial_state)
        return final_state.get("final_answer", {})
    except Exception as e:
        return {
            "error":          str(e),
            "spoken_summary": "I encountered an error. Please try again.",
            "hospitals":      [],
            "confidence":     0,
            "used_defaults":  False,
        }