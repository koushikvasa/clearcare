# agent/tools.py
# ─────────────────────────────────────────────────────
# All tools available to the ClearCare agent.
# Each tool is a Python function the LLM can decide to call.
# The docstring of each function is what the LLM reads
# to understand when and how to use the tool.
# ─────────────────────────────────────────────────────

import os
import httpx  # type: ignore[reportMissingImports]
from langchain_core.tools import tool  # type: ignore[reportMissingImports]
from tavily import TavilyClient  # type: ignore[reportMissingImports]

from config import TAVILY_API_KEY, NPI_REGISTRY_URL

# Initialize Tavily client once at module level
# so we don't recreate it on every tool call
tavily = TavilyClient(api_key=TAVILY_API_KEY)


# ── TOOL 1: Web Search ────────────────────────────────
# Why: Insurance directories, drug prices, and hospital
# network info change constantly. We need LIVE data,
# not data frozen in our training cutoff.
# Tavily is purpose-built for AI agents — it returns
# clean text, not raw HTML like a regular search API.

@tool
def search_web(query: str) -> str:
    """
    Search the live web for Medicare, insurance, and medical cost information.
    Use this for: insurance plan details, drug prices, hospital network status,
    Medicare coverage rules, and any information that changes frequently.
    Returns summarized text from the most relevant web sources.
    """
    try:
        results = tavily.search(
            query=query,
            max_results=4,
            # search_depth="advanced" gives better results
            # but uses more API credits — fine for hackathon
            search_depth="advanced"
        )

        if not results or not results.get("results"):
            return "No results found for this query."

        # Format results into clean text the LLM can read
        # We include the URL so the agent can cite sources
        formatted = []
        for r in results["results"]:
            formatted.append(
                f"Source: {r.get('url', 'unknown')}\n"
                f"Content: {r.get('content', '')}\n"
            )

        return "\n---\n".join(formatted)

    except Exception as e:
        # Never let a tool crash the whole agent
        # Return the error as text so the agent can handle it
        return f"Search failed: {str(e)}"


# ── TOOL 2: Find Hospitals ────────────────────────────
# Why: We use the CMS NPI (National Provider Identifier)
# Registry — the official US government database of every
# licensed healthcare provider. It's public, free, and
# always up to date. No API key needed.
#
# NPI Registry URL: npiregistry.cms.hhs.gov
# Every hospital and doctor in the US has an NPI number.

@tool
def find_hospitals(zip_code: str, specialty: str = "hospital") -> str:
    """
    Find hospitals and medical providers near a zip code.
    Uses the official CMS NPI Registry — the US government database
    of all licensed healthcare providers.
    Input: zip_code (5-digit US zip), specialty (e.g. 'hospital', 'radiology', 'cardiology')
    Returns: list of nearby providers with name, address, and phone number.
    """
    try:
        # NPI Registry API parameters
        # version 2.1 is the current stable version
        params = {
            "version": "2.1",
            "postal_code": zip_code,
            "taxonomy_description": specialty,
            "limit": 8,          # top 8 results is enough for our map
        }

        response = httpx.get(
            NPI_REGISTRY_URL,
            params=params,
            timeout=10           # 10 second timeout — don't hang the agent
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])

        if not results:
            return f"No providers found near zip code {zip_code} for {specialty}."

        # Format into readable text for the LLM
        providers = []
        for p in results:
            basic = p.get("basic", {})
            addresses = p.get("addresses", [{}])
            addr = addresses[0] if addresses else {}

            # Organization name for hospitals
            # or First + Last name for individual providers
            name = (
                basic.get("organization_name") or
                f"Dr. {basic.get('first_name', '')} {basic.get('last_name', '')}".strip()
            )

            providers.append(
                f"Name: {name}\n"
                f"NPI: {p.get('number', 'N/A')}\n"
                f"Address: {addr.get('address_1', '')}, "
                f"{addr.get('city', '')}, {addr.get('state', '')} "
                f"{addr.get('postal_code', '')}\n"
                f"Phone: {addr.get('telephone_number', 'N/A')}\n"
            )

        return f"Found {len(providers)} providers near {zip_code}:\n\n" + "\n---\n".join(providers)

    except httpx.TimeoutException:
        return "Hospital lookup timed out. Please try again."
    except Exception as e:
        return f"Hospital lookup failed: {str(e)}"


# ── TOOL 3: Check Network Status ──────────────────────
# Why: In-network vs out-of-network is the single biggest
# factor in what a patient pays. A $500 procedure can cost
# $2,000 out-of-network. We use Tavily to search the
# insurer's live provider directory for real-time status.
#
# Important: We score the result by counting signal words
# rather than trusting a binary yes/no, because web search
# results are messy and nuanced.

@tool
def check_network_status(hospital_name: str, insurance_plan: str, zip_code: str) -> str:
    """
    Check whether a hospital is in-network or out-of-network for a given insurance plan.
    Searches the insurer's live provider directory.
    Input: hospital_name, insurance_plan (full plan name), zip_code
    Returns: network status (in-network/out-of-network/unknown) with confidence level.
    """
    try:
        # Targeted search query for the insurer's provider directory
        query = (
            f'"{hospital_name}" "{insurance_plan}" '
            f'in-network provider directory {zip_code} site:*.com'
        )

        results = tavily.search(query=query, max_results=3)
        text = ""
        if results and results.get("results"):
            text = " ".join([
                r.get("content", "") for r in results["results"]
            ]).lower()

        # Count how many in-network vs out-of-network signals appear
        # This is more robust than looking for a single keyword
        in_signals  = ["in-network", "in network", "participating", "contracted provider"]
        out_signals = ["out-of-network", "out of network", "non-participating", "not contracted"]

        in_score  = sum(text.count(s) for s in in_signals)
        out_score = sum(text.count(s) for s in out_signals)

        # Determine status and confidence
        if in_score > out_score:
            status = "in-network"
            confidence = min(0.95, 0.65 + (in_score * 0.05))
        elif out_score > in_score:
            status = "out-of-network"
            confidence = min(0.95, 0.65 + (out_score * 0.05))
        else:
            status = "unknown"
            confidence = 0.40

        return (
            f"Hospital: {hospital_name}\n"
            f"Plan: {insurance_plan}\n"
            f"Network Status: {status}\n"
            f"Confidence: {round(confidence * 100)}%\n"
            f"Note: Always verify with your insurer before scheduling."
        )

    except Exception as e:
        return f"Network status check failed: {str(e)}"


# ── TOOL 4: Estimate Cost ─────────────────────────────
# Why: The core of ClearCare. We use CMS benchmark costs
# for common procedures and apply Medicare's standard
# cost-sharing rules (deductibles, coinsurance, copays).
#
# These are ESTIMATES not guarantees — actual costs vary
# by provider, year, and individual plan details.
# We make this clear in the output.
#
# Cost sharing rules used:
# Medicare Part B: 20% coinsurance after $240 deductible
# Medicare Advantage: varies by plan (we use typical ranges)
# Out-of-network: typically 40-55% of total cost

@tool
def estimate_cost(
    procedure: str,
    insurance_plan: str,
    network_status: str,
    severity: str = "moderate",
    deductible_met: bool = False
) -> str:
    """
    Estimate the patient's out-of-pocket cost for a medical procedure.
    Uses CMS Medicare benchmark pricing and standard cost-sharing rules.
    Input: procedure name, insurance_plan, network_status (in-network/out-of-network),
           severity (mild/moderate/severe/critical), deductible_met (true/false)
    Returns: estimated cost breakdown with in-network, out-of-network, and alternative costs.
    """

    # ── Step 1: Base cost from CMS benchmarks ─────────
    # These are approximate Medicare allowed amounts for common procedures
    # Real CMS data: cms.gov/medicare/payment/fee-schedules
    procedure_lower = procedure.lower()

    base_costs = {
        "mri":                  1500,
        "ct scan":               800,
        "x-ray":                 200,
        "colonoscopy":          2500,
        "ultrasound":            400,
        "blood test":            150,
        "lab":                   150,
        "surgery":             15000,
        "emergency":            3000,
        "physical":              250,
        "wellness visit":        250,
        "specialist":            350,
        "primary care":          200,
        "mental health":         200,
        "mammogram":             300,
        "ecg":                   300,
        "echocardiogram":       1200,
        "colonoscopy":          2500,
        "endoscopy":            1800,
        "biopsy":               1000,
        "infusion":             2000,
        "physical therapy":      200,
    }

    # Find the best matching procedure in our cost table
    base_cost = 1000  # default if nothing matches
    for key, cost in base_costs.items():
        if key in procedure_lower:
            base_cost = cost
            break

    # ── Step 2: Apply severity multiplier ─────────────
    # More severe conditions need more complex (expensive) care
    severity_multipliers = {
        "mild":     0.7,
        "moderate": 1.0,
        "severe":   1.6,
        "critical": 2.5
    }
    multiplier = severity_multipliers.get(severity, 1.0)
    adjusted_cost = base_cost * multiplier

    # ── Step 3: Apply insurance cost-sharing rules ─────
    plan_lower = insurance_plan.lower()

    if "medicare" in plan_lower and "advantage" not in plan_lower:
        # Original Medicare (Part A/B) rules:
        # Part B covers 80% after the annual deductible ($240 in 2024)
        # Patient pays 20% coinsurance
        if network_status == "in-network":
            if deductible_met:
                patient_cost = adjusted_cost * 0.20
            else:
                # Apply deductible first, then 20% on the rest
                deductible = 240
                if adjusted_cost <= deductible:
                    patient_cost = adjusted_cost
                else:
                    patient_cost = deductible + (adjusted_cost - deductible) * 0.20
        else:
            # Original Medicare has no network — but some providers
            # don't accept assignment, costing patients more
            patient_cost = adjusted_cost * 0.35

    else:
        # Medicare Advantage or commercial plan
        # These have copays and coinsurance that vary by plan
        if network_status == "in-network":
            if deductible_met:
                patient_cost = adjusted_cost * 0.20
            else:
                # Typical MA plan: copay + coinsurance
                copay = 40 if adjusted_cost < 500 else 0
                patient_cost = copay + (adjusted_cost * 0.25)
        else:
            # Out-of-network with MA = very expensive
            # Typically 40-50% of total cost or full cost
            patient_cost = adjusted_cost * 0.50

    # ── Step 4: Calculate alternative (cheaper option) ─
    # Outpatient facilities charge 30-40% less than hospitals
    alternative_cost = patient_cost * 0.65
    if "emergency" in procedure_lower:
        alternative_note = "Urgent care center (for non-life-threatening conditions)"
    elif any(x in procedure_lower for x in ["mri", "ct", "x-ray", "ultrasound"]):
        alternative_note = "Freestanding imaging center (same equipment, lower facility fee)"
    elif "surgery" in procedure_lower:
        alternative_note = "Ambulatory Surgery Center (outpatient, same procedure)"
    else:
        alternative_note = "Outpatient facility or community health center"

    return (
        f"Procedure: {procedure}\n"
        f"Plan: {insurance_plan}\n"
        f"Network: {network_status}\n"
        f"Severity: {severity}\n"
        f"Deductible met: {deductible_met}\n\n"
        f"--- COST ESTIMATE ---\n"
        f"Base Medicare cost: ${base_cost:,.0f}\n"
        f"Severity-adjusted cost: ${adjusted_cost:,.0f}\n"
        f"Your estimated cost: ${patient_cost:,.0f}\n"
        f"Alternative option: ${alternative_cost:,.0f} ({alternative_note})\n\n"
        f"⚠️ These are estimates based on CMS benchmark data. "
        f"Actual costs vary by provider. Always verify before scheduling."
    )


# ── TOOL 5: Find Alternatives ─────────────────────────
# Why: Giving the user a cheaper option for the same care
# is the most actionable thing ClearCare can do.
# This tool searches for real lower-cost alternatives
# — generic drugs, outpatient facilities, telehealth.

@tool
def find_alternatives(procedure: str, zip_code: str, current_cost: float) -> str:
    """
    Find cheaper alternatives for the same medical procedure or medication.
    Searches for outpatient facilities, generic drugs, or telehealth options
    that provide equivalent care at lower cost.
    Input: procedure name, zip_code, current_cost (estimated patient cost)
    Returns: list of alternatives with estimated savings.
    """
    try:
        query = (
            f"cheaper alternative to {procedure} near {zip_code} "
            f"Medicare covered outpatient lower cost"
        )
        results = tavily.search(query=query, max_results=3)

        alternatives = []

        # Add web search results
        if results and results.get("results"):
            for r in results["results"][:2]:
                alternatives.append(
                    f"• {r.get('title', 'Option')}: {r.get('content', '')[:200]}"
                )

        # Add procedure-specific known alternatives
        procedure_lower = procedure.lower()

        if any(x in procedure_lower for x in ["mri", "ct scan", "x-ray"]):
            savings = current_cost * 0.40
            alternatives.append(
                f"• Freestanding Imaging Center: Typically saves ${savings:,.0f} "
                f"vs hospital-based imaging. Same equipment and quality."
            )

        if "colonoscopy" in procedure_lower:
            alternatives.append(
                "• Ambulatory Surgery Center (ASC): Medicare covers colonoscopies "
                "at ASCs at the same rate as hospitals but facility fees are lower."
            )

        if "primary care" in procedure_lower or "visit" in procedure_lower:
            alternatives.append(
                "• Telehealth visit: Many Medicare plans cover telehealth at $0 copay. "
                "Available same-day for routine consultations."
            )

        if not alternatives:
            alternatives.append(
                "• Contact your plan's member services to ask about lower-cost "
                "in-network alternatives for this procedure."
            )

        savings_pct = 35
        return (
            f"Alternatives for {procedure} near {zip_code}:\n\n"
            + "\n\n".join(alternatives) +
            f"\n\n💡 Tip: Ask your doctor if any of these alternatives "
            f"are clinically appropriate for your situation."
        )

    except Exception as e:
        return f"Alternatives search failed: {str(e)}"


# ── Export all tools as a list ─────────────────────────
# This is what we pass to the LangGraph agent.
# The agent gets this list and knows exactly what it can do.
ALL_TOOLS = [
    search_web,
    find_hospitals,
    check_network_status,
    estimate_cost,
    find_alternatives,
]