# agent/graph.py
# LangGraph agent pipeline for ClearCare.
# Connects all tools into a stateful multi-step pipeline.
#
# Flow:
# check_inputs
#   if insurance provided: extract_plan
#   if no insurance:       use_defaults
# both paths merge into: assess_severity
# then: find_hospitals, check_network, estimate_cost,
#       find_alternatives, generate_answer

import re
import json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END  # type: ignore[reportMissingImports]
from langchain_openai import ChatOpenAI  # type: ignore[reportMissingImports]
from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore[reportMissingImports]
import httpx  # type: ignore[reportMissingImports]
from config import NPI_REGISTRY_URL
from config import OPENAI_API_KEY  
from agent.tools import (
    extract_plan_details,
    find_hospitals,
    check_network_status,
    estimate_cost,
    find_alternatives,
    ALL_TOOLS,
)
from agent.prompts import (
    COST_ESTIMATION_PROMPT,
    SEVERITY_ASSESSMENT_PROMPT,
)


# LLM used for reasoning nodes
# temperature=0 means deterministic outputs
# same input always gives same output
# critical for cost estimation consistency
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=OPENAI_API_KEY
)


# ── STATE ─────────────────────────────────────────────
# The state is a dictionary that travels through every node.
# Each node reads from it and writes updates back to it.
# TypedDict enforces the shape so typos cause early errors.

class AgentState(TypedDict):
    # inputs set at the start, never modified
    insurance_input:   str
    input_type:        str
    care_needed:       str
    zip_code:          str
    file_path:         Optional[str]
    medical_history:   Optional[str]

    # filled progressively as nodes execute
    has_insurance:     Optional[bool]
    plan_details:      Optional[dict]
    severity:          Optional[str]
    hospitals:         Optional[list]
    network_results:   Optional[list]
    cost_estimate:     Optional[dict]
    alternatives:      Optional[str]

    # final output
    final_answer:      Optional[dict]
    error:             Optional[str]


# ── HELPERS ───────────────────────────────────────────
# Small parsing utilities used by nodes.
# Tools return formatted text strings.
# These extract the actual numbers and values from that text.

def parse_dollar(text: str, label: str) -> float:
    """Extract a dollar amount after a label in tool output."""
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
    """Extract a percentage after a label in tool output."""
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
    """Extract a text field after a label in tool output."""
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
    """Parse find_hospitals tool output into a list of dicts."""
    hospitals = []
    blocks = text.split("---")
    for block in blocks:
        if "Name:" not in block:
            continue
        hospital = {}
        for line in block.strip().split("\n"):
            if line.startswith("Name:"):
                hospital["name"] = line.replace("Name:", "").strip()
            elif line.startswith("Address:"):
                hospital["address"] = line.replace("Address:", "").strip()
            elif line.startswith("Phone:"):
                hospital["phone"] = line.replace("Phone:", "").strip()
            elif line.startswith("NPI:"):
                hospital["npi"] = line.replace("NPI:", "").strip()
        if hospital.get("name"):
            hospitals.append(hospital)
    return hospitals


# ── DEFAULT PLAN VALUES ───────────────────────────────
# Used when no insurance info is provided.
# Based on standard Original Medicare (Part A/B) rules.
# These are real 2024/2025 Medicare benchmarks from CMS.

DEFAULT_PLAN = {
    "plan_name":          "Original Medicare (Part A/B)",
    "plan_type":          "Original Medicare",
    "insurance_company":  "Medicare",
    "deductible":         240,      # 2024 Part B deductible
    "out_of_pocket_max":  None,     # Original Medicare has no OOP max
    "copay_primary_care": 0,        # covered after deductible
    "copay_specialist":   0,        # covered after deductible
    "coinsurance":        20,       # patient pays 20% after deductible
    "is_default":         True,     # flag so we can show the disclaimer
}


# ── NODES ─────────────────────────────────────────────
# Each node receives the full state, does one job,
# and returns a dict of fields to update in the state.
# LangGraph merges the returned dict automatically.

def node_check_inputs(state: AgentState) -> dict:
    """
    Node 1: Determine whether the user provided insurance info.
    This is the branching point of the graph.
    Sets has_insurance which the conditional edge reads.
    """
    raw = state.get("insurance_input", "").strip()

    # Consider insurance provided if the input is meaningful text
    # not just whitespace, "none", "no", "skip", or very short
    no_insurance_signals = {"none", "no", "skip", "n/a", "na", "unknown", ""}
    has_insurance = (
        len(raw) > 5 and
        raw.lower() not in no_insurance_signals
    )

    return {"has_insurance": has_insurance}


def node_extract_plan(state: AgentState) -> dict:
    """
    Node 2A: Extract real plan details from insurance input.
    Only runs when has_insurance is True.
    """
    result = extract_plan_details.invoke({
        "input_type": state["input_type"],
        "text_input": state["insurance_input"],
        "file_path":  state.get("file_path", "")
    })

    plan_dict = {
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
    }

    return {"plan_details": plan_dict}


def node_use_defaults(state: AgentState) -> dict:
    """
    Node 2B: Use standard Medicare defaults when no insurance provided.
    Only runs when has_insurance is False.
    The final answer will include a message explaining that
    providing real plan details would improve accuracy.
    """
    return {"plan_details": DEFAULT_PLAN}


def node_assess_severity(state: AgentState) -> dict:
    """
    Node 3: Assess severity from optional medical history.
    If no history provided, defaults to moderate.
    Severity adjusts the cost estimate up or down.
    """
    history = state.get("medical_history", "").strip()

    if not history:
        return {"severity": "moderate"}

    response = llm.invoke([
        SystemMessage(content=SEVERITY_ASSESSMENT_PROMPT),
        HumanMessage(content=f"Medical history:\n{history}")
    ])

    try:
        data = json.loads(response.content)
        severity = data.get("severity", "moderate")
        return {"severity": severity}
    except Exception:
        return {"severity": "moderate"}


def node_find_hospitals(state: AgentState) -> dict:
    zip_code = state.get("zip_code", "")
    care     = state.get("care_needed", "").lower()

    # Map care to specialty
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
    }

    specialty = "hospital"
    for keyword, spec in specialty_map.items():
        if keyword in care:
            specialty = spec
            break

    # Search for ORGANIZATIONS not individuals
    # entity_type_code=2 filters to organizations/facilities only
    # This prevents returning individual doctors instead of hospitals


    try:
        params = {
            "version":          "2.1",
            "postal_code":      zip_code,
            "taxonomy_description": specialty,
            "entity_type_code": "2",    # 2 = organizations only, 1 = individuals
            "limit":            8,
        }
        response = httpx.get(NPI_REGISTRY_URL, params=params, timeout=10)
        response.raise_for_status()
        data     = response.json()
        results  = data.get("results", [])

        # If no organizations found, fall back to general hospital search
        if not results:
            params["taxonomy_description"] = "hospital"
            response = httpx.get(NPI_REGISTRY_URL, params=params, timeout=10)
            data     = response.json()
            results  = data.get("results", [])

        hospitals = []
        for p in results:
            basic     = p.get("basic", {})
            addresses = p.get("addresses", [{}])
            addr      = addresses[0] if addresses else {}
            name      = basic.get("organization_name", "").strip()

            if not name:
                continue

            hospitals.append({
                "hospital":       name,
                "address":        f"{addr.get('address_1','')}, {addr.get('city','')}, {addr.get('state','')} {addr.get('postal_code','')}",
                "phone":          addr.get("telephone_number", "N/A"),
                "npi":            p.get("number", ""),
                "network_status": "unknown",   # gets updated later by cost node
                "estimated_cost": 0,           # gets updated later by cost node
            })

    except Exception as e:
        hospitals = []

    return {"hospitals": hospitals}


def node_check_network(state: AgentState) -> dict:
    """
    Node 5: Check network status for each hospital.
    In vs out of network is the single biggest factor
    in what the patient actually pays.
    If using default plan, marks all hospitals as unknown
    since we have no plan to check against.
    """
    hospitals    = state.get("hospitals", [])
    plan_details = state.get("plan_details", {})
    plan_name    = plan_details.get("plan_name", "")
    is_default   = plan_details.get("is_default", False)

    network_results = []

    for hospital in hospitals[:4]:
        name = hospital.get("name", "")
        if not name:
            continue

        if is_default:
            # Original Medicare has no network restriction
            # all providers who accept Medicare assignment are covered
            status = "accepts-medicare"
        else:
            result = check_network_status.invoke({
                "hospital_name":  name,
                "insurance_plan": plan_name,
                "zip_code":       state.get("zip_code", "")
            })
            if "in-network" in result.lower():
                status = "in-network"
            elif "out-of-network" in result.lower():
                status = "out-of-network"
            else:
                status = "unknown"

        network_results.append({
            "name":    name,
            "address": hospital.get("address", ""),
            "phone":   hospital.get("phone", ""),
            "status":  status,
        })

    return {"network_results": network_results}


def node_estimate_cost(state: AgentState) -> dict:
    """
    Node 6: Calculate out-of-pocket cost for each hospital.
    Uses real plan details if available, defaults otherwise.
    Calculates in-network and out-of-network separately.
    """
    plan_details    = state.get("plan_details", {})
    network_results = state.get("network_results", [])
    care            = state.get("care_needed", "")
    severity        = state.get("severity", "moderate")
    plan_name       = plan_details.get("plan_name", "Original Medicare")

    cost_results = []

    for hospital in network_results:
        result = estimate_cost.invoke({
            "procedure":      care,
            "insurance_plan": plan_name,
            "network_status": hospital["status"],
            "severity":       severity,
            "deductible_met": False
        })

        cost = parse_dollar(result, "Your estimated cost:")

        cost_results.append({
            "hospital":       hospital["name"],
            "address":        hospital.get("address", ""),
            "phone":          hospital.get("phone", ""),
            "network_status": hospital["status"],
            "estimated_cost": cost,
        })

    # Sort cheapest first
    cost_results.sort(key=lambda x: x["estimated_cost"] or 9999)

    return {"cost_estimate": {"hospitals": cost_results}}


def node_find_alternatives(state: AgentState) -> dict:
    """
    Node 7: Find cheaper alternatives for the same care.
    Always gives the user at least one lower cost option.
    """
    care      = state.get("care_needed", "")
    zip_code  = state.get("zip_code", "")
    cost_data = state.get("cost_estimate", {})
    hospitals = cost_data.get("hospitals", [])
    cheapest  = hospitals[0]["estimated_cost"] if hospitals else 500.0

    result = find_alternatives.invoke({
        "procedure":    care,
        "zip_code":     zip_code,
        "current_cost": cheapest
    })

    return {"alternatives": result}


def node_generate_answer(state: AgentState) -> dict:
    """
    Node 8: Generate the final plain-English answer.
    Synthesizes everything into a response the user can
    understand and act on. Spoken aloud by ElevenLabs.
    If defaults were used, includes a note explaining
    that real plan details would improve accuracy.
    """
    plan_details    = state.get("plan_details", {})
    cost_data       = state.get("cost_estimate", {})
    hospitals       = cost_data.get("hospitals", [])
    alternatives    = state.get("alternatives", "")
    care            = state.get("care_needed", "")
    is_default      = plan_details.get("is_default", False)

    in_network  = [h for h in hospitals if h["network_status"] in ("in-network", "accepts-medicare")]
    out_network = [h for h in hospitals if h["network_status"] == "out-of-network"]

    cheapest_in  = in_network[0]  if in_network  else None
    cheapest_out = out_network[0] if out_network else None

    context = f"""
Patient needs: {care}
Insurance plan: {plan_details.get("plan_name", "Original Medicare")}
Plan type: {plan_details.get("plan_type", "unknown")}
Deductible: ${plan_details.get("deductible", "unknown")}
Out-of-pocket max: ${plan_details.get("out_of_pocket_max", "no limit")}
Using default values: {is_default}

CHEAPEST COVERED OPTION:
{f"{cheapest_in['hospital']}: ${cheapest_in['estimated_cost']}" if cheapest_in else "None found"}

CHEAPEST OUT-OF-NETWORK:
{f"{cheapest_out['hospital']}: ${cheapest_out['estimated_cost']}" if cheapest_out else "None found"}

ALL OPTIONS:
{json.dumps(hospitals, indent=2)}

CHEAPER ALTERNATIVES:
{alternatives}

IMPORTANT: If is_default is True, end your spoken_summary with:
"These estimates use standard Medicare rates. For a more accurate cost
based on your specific plan, share your insurance details and I can
recalculate with your actual deductibles and copays."
"""

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

    answer["hospitals"]      = hospitals
    answer["plan_details"]   = plan_details
    answer["alternatives"]   = alternatives
    answer["used_defaults"]  = is_default

    return {"final_answer": answer}


# ── CONDITIONAL ROUTING ───────────────────────────────
# This function is called after node_check_inputs.
# It reads has_insurance and returns the name of the
# next node to execute.

def route_after_check(state: AgentState) -> str:
    """
    Routing function for the conditional edge after check_inputs.
    Returns the name of the next node to run.
    """
    if state.get("has_insurance"):
        return "extract_plan"
    return "use_defaults"


# ── GRAPH ASSEMBLY ────────────────────────────────────
# Wire all nodes together.
# add_edge: always goes A to B
# add_conditional_edges: branches based on routing function

def build_graph():
    graph = StateGraph(AgentState)

    # Register all nodes
    graph.add_node("check_inputs",       node_check_inputs)
    graph.add_node("extract_plan",       node_extract_plan)
    graph.add_node("use_defaults",       node_use_defaults)
    graph.add_node("assess_severity",    node_assess_severity)
    graph.add_node("find_hospitals",     node_find_hospitals)
    graph.add_node("check_network",      node_check_network)
    graph.add_node("estimate_cost",      node_estimate_cost)
    graph.add_node("find_alternatives",  node_find_alternatives)
    graph.add_node("generate_answer",    node_generate_answer)

    # Entry point
    graph.add_edge(START, "check_inputs")

    # Conditional branch after check_inputs
    # routes to extract_plan or use_defaults
    graph.add_conditional_edges(
        "check_inputs",
        route_after_check,
        {
            "extract_plan": "extract_plan",
            "use_defaults": "use_defaults",
        }
    )

    # Both paths merge into assess_severity
    graph.add_edge("extract_plan",  "assess_severity")
    graph.add_edge("use_defaults",  "assess_severity")

    # Fixed pipeline from here
    graph.add_edge("assess_severity",   "find_hospitals")
    graph.add_edge("find_hospitals",    "check_network")
    graph.add_edge("check_network",     "estimate_cost")
    graph.add_edge("estimate_cost",     "find_alternatives")
    graph.add_edge("find_alternatives", "generate_answer")
    graph.add_edge("generate_answer",   END)

    return graph.compile()


# Build once at module load time
agent = build_graph()


# ── PUBLIC INTERFACE ──────────────────────────────────
# Single function the route files call.
# Hides all LangGraph complexity behind a clean API.

def run_agent(
    insurance_input: str,
    care_needed:     str,
    zip_code:        str,
    input_type:      str = "text",
    file_path:       str = "",
    medical_history: str = ""
) -> dict:
    """
    Run the ClearCare agent end-to-end.

    Args:
        insurance_input: Plan name, card image path, or PDF path
        care_needed:     What medical care the user needs
        zip_code:        5-digit zip code for hospital search
        input_type:      text, image, or pdf
        file_path:       Path to uploaded file for image/pdf
        medical_history: Optional past records text

    Returns:
        Dict with hospitals, costs, alternatives, spoken_summary
    """
    initial_state: AgentState = {
        "insurance_input": insurance_input,
        "input_type":      input_type,
        "care_needed":     care_needed,
        "zip_code":        zip_code,
        "file_path":       file_path,
        "medical_history": medical_history,
        "has_insurance":   None,
        "plan_details":    None,
        "severity":        None,
        "hospitals":       None,
        "network_results": None,
        "cost_estimate":   None,
        "alternatives":    None,
        "final_answer":    None,
        "error":           None,
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