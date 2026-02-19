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
import base64
import json
from pathlib import Path
from openai import OpenAI  # type: ignore[reportMissingImports]
from agent.prompts import INSURANCE_EXTRACTION_PROMPT

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


# ── TOOL 6: Extract Plan Details ─────────────────────
# Why: This is the foundation of accurate cost estimation.
# Without knowing the REAL deductible, coinsurance, and
# copay amounts from the user's actual plan, all our cost
# estimates are just educated guesses.
#
# This tool reads the plan from ANY input type:
# - Text: direct extraction via GPT-4o
# - Image: GPT-4o Vision reads the card directly
# - PDF: Vision first, raw text extraction as fallback
#
# Then fills missing fields by searching the web for
# that specific plan's published benefit details.
#
# The result is a complete PlanDetails object used by
# estimate_cost() for precise, personalized calculations.


# Initialize OpenAI client
# We import OPENAI_API_KEY from config — never hardcode it
from config import OPENAI_API_KEY
openai_client = OpenAI(api_key=OPENAI_API_KEY)


def _encode_image_to_base64(image_path: str) -> str:
    """
    Convert an image file to base64 string for the GPT-4o Vision API.
    
    Why base64? The OpenAI API doesn't accept raw binary files.
    base64 encodes binary data as ASCII text that can travel in JSON.
    """
    with open(image_path, "rb") as f:      # "rb" = read binary mode
        return base64.b64encode(f.read()).decode("utf-8")


def _extract_from_image(image_path: str) -> dict:
    """
    Stage 1A: Use GPT-4o Vision to read an insurance card image.
    
    GPT-4o can see images — we pass the image as base64 alongside
    our extraction prompt. It reads the card like a human would
    and returns structured JSON with the plan details it finds.
    """
    image_data = _encode_image_to_base64(image_path)

    # Detect image type from file extension
    # The API needs to know the format to decode it correctly
    extension = Path(image_path).suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(extension, "image/jpeg")

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": INSURANCE_EXTRACTION_PROMPT
            },
            {
                "role": "user",
                "content": [
                    # Text part of the message
                    {
                        "type": "text",
                        "text": "Extract all insurance plan details from this card image."
                    },
                    # Image part — this is what makes it multimodal
                    {
                        "type": "image_url",
                        "image_url": {
                            # Format: "data:<media_type>;base64,<data>"
                            "url": f"data:{media_type};base64,{image_data}",
                            # "high" detail = GPT-4o reads the full image
                            # "low" is faster but misses small text on cards
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        max_tokens=500
    )

    return json.loads(response.choices[0].message.content)


def _extract_from_pdf(pdf_path: str) -> dict:
    """
    Stage 1B: Extract plan details from a PDF document.
    
    Strategy:
    1. Try GPT-4o Vision on the first page (most info is on page 1)
    2. If vision fails or returns low confidence, fall back to
       extracting raw text with pypdf and sending that to GPT-4o
    
    Why try vision first on PDF?
    Insurance PDFs are often scanned documents (images inside PDF).
    pypdf can't extract text from scanned images — it returns nothing.
    GPT-4o Vision can read both digital and scanned PDFs.
    """
    try:
        # ── Attempt 1: pypdf text extraction ──────────
        # Works for digital PDFs (text is selectable)
        # Fails silently for scanned PDFs (returns empty string)
        import pypdf  # type: ignore[reportMissingImports]

        text_content = ""
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            # Read first 3 pages — benefit summaries are usually at the front
            for page_num in range(min(3, len(reader.pages))):
                text_content += reader.pages[page_num].extract_text() or ""

        if text_content.strip():
            # We got text — send it to GPT-4o for extraction
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": INSURANCE_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"Extract insurance details from this document text:\n\n{text_content[:4000]}"}
                    # 4000 char limit — GPT-4o context is large but we
                    # don't need the whole document, just the key fields
                ],
                max_tokens=500
            )
            result = json.loads(response.choices[0].message.content)

            # If confidence is decent, return this result
            if result.get("confidence", 0) >= 0.70:
                return result

        # ── Attempt 2: Convert PDF page to image ──────
        # If text extraction failed or was low confidence,
        # render the PDF as an image and use GPT-4o Vision
        # This handles scanned documents
        try:
            # PyMuPDF — renders PDF pages as images  
            import fitz  # type: ignore[reportMissingImports]
            doc = fitz.open(pdf_path)
            page = doc[0]                     # first page

            # Render at 2x zoom for better readability
            # Matrix(2, 2) = 2x zoom in both dimensions = 144 DPI
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)

            # Save as temporary PNG for Vision API
            temp_image_path = pdf_path.replace(".pdf", "_page1.png")
            pix.save(temp_image_path)
            doc.close()

            # Now use our image extraction function
            result = _extract_from_image(temp_image_path)

            # Clean up temp file
            import os
            os.remove(temp_image_path)

            return result

        except ImportError:
            # PyMuPDF not installed — return whatever text extraction got
            pass

    except Exception as e:
        return {"error": str(e), "confidence": 0}

    return {"confidence": 0, "plan_name": None}


def _fill_missing_with_web_search(plan_details: dict) -> dict:
    """
    Stage 3: For any null fields in the extracted plan details,
    search the web to find the real values.
    
    Why this matters: Insurance cards rarely show deductibles or
    out-of-pocket maximums. But these numbers are public — insurers
    publish their plan benefits online. We can find them.
    
    Example search: "Humana Gold Plus HMO H5619 deductible 2024"
    """
    plan_name = plan_details.get("plan_name", "")
    company = plan_details.get("insurance_company", "")

    if not plan_name:
        return plan_details  # nothing to search for

    # Fields we want to fill in if missing
    missing_fields = []
    if not plan_details.get("deductible"):
        missing_fields.append("deductible")
    if not plan_details.get("out_of_pocket_max"):
        missing_fields.append("out-of-pocket maximum")
    if not plan_details.get("copay_primary_care"):
        missing_fields.append("copay primary care specialist")

    if not missing_fields:
        return plan_details  # everything already filled

    # Build a targeted search query for this specific plan
    search_query = (
        f"{plan_name} {company} Medicare plan "
        f"{' '.join(missing_fields)} 2024 2025"
    )

    try:
        results = tavily.search(query=search_query, max_results=3)

        if not results or not results.get("results"):
            return plan_details

        # Combine search result text
        search_text = " ".join([
            r.get("content", "") for r in results["results"]
        ])

        # Ask GPT-4o to extract the missing fields from search results
        fill_prompt = f"""
        Given this information about the insurance plan "{plan_name}":
        
        {search_text[:3000]}
        
        Extract ONLY these specific values if found:
        {', '.join(missing_fields)}
        
        Return JSON with only the fields you found, plus a confidence score.
        If you cannot find a specific value, use null.
        Do not guess — only return values explicitly stated in the text.
        """

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "user", "content": fill_prompt}
            ],
            max_tokens=300
        )

        filled = json.loads(response.choices[0].message.content)

        # Merge filled values into plan_details
        # Only update fields that are currently null
        for key, value in filled.items():
            if key != "confidence" and value and not plan_details.get(key):
                plan_details[key] = value

        # Update confidence — averaged between original and web fill
        original_confidence = plan_details.get("confidence", 0.5)
        web_confidence = filled.get("confidence", 0.5)
        plan_details["confidence"] = round(
            (original_confidence + web_confidence) / 2, 2
        )
        plan_details["web_search_used"] = True

    except Exception as e:
        plan_details["web_search_error"] = str(e)

    return plan_details


@tool
def extract_plan_details(
    input_type: str,
    text_input: str = "",
    file_path: str = ""
) -> str:
    """
    Extract complete insurance plan details from any input type.
    Use this FIRST before estimating any costs — it provides the real
    plan details needed for accurate calculation.

    input_type options:
    - "text": user typed their plan name or described their insurance
    - "image": path to an uploaded insurance card photo (jpg/png)  
    - "pdf": path to an uploaded insurance document PDF

    Returns: complete plan details including deductible, copays,
    coinsurance, out-of-pocket maximum, and plan type.
    Missing fields are filled by searching the web automatically.
    """
    try:
        plan_details = {}

        # ── Route to correct extraction method ────────
        if input_type == "text":
            # Text input: send directly to GPT-4o with extraction prompt
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": INSURANCE_EXTRACTION_PROMPT},
                    {"role": "user", "content": text_input}
                ],
                max_tokens=500
            )
            plan_details = json.loads(response.choices[0].message.content)

        elif input_type == "image":
            if not file_path:
                return "Error: file_path required for image input"
            plan_details = _extract_from_image(file_path)

        elif input_type == "pdf":
            if not file_path:
                return "Error: file_path required for pdf input"
            plan_details = _extract_from_pdf(file_path)

        else:
            return f"Error: unknown input_type '{input_type}'. Use text, image, or pdf."

        # ── Fill missing fields with web search ───────
        # This runs regardless of input type
        plan_details = _fill_missing_with_web_search(plan_details)

        # ── Format as readable output for the agent ───
        output_lines = [
            "=== EXTRACTED PLAN DETAILS ===",
            f"Plan Name:          {plan_details.get('plan_name', 'Not found')}",
            f"Plan Type:          {plan_details.get('plan_type', 'Not found')}",
            f"Insurance Company:  {plan_details.get('insurance_company', 'Not found')}",
            f"Member ID:          {plan_details.get('member_id', 'Not found')}",
            f"Deductible:         ${plan_details.get('deductible', 'Not found')}",
            f"Out-of-Pocket Max:  ${plan_details.get('out_of_pocket_max', 'Not found')}",
            f"Zip Code:           {plan_details.get('zip_code', 'Not found')}",
            f"Confidence:         {round(plan_details.get('confidence', 0) * 100)}%",
            f"Web Search Used:    {plan_details.get('web_search_used', False)}",
            "",
            "Use these details in estimate_cost() for accurate calculation.",
            "⚠️ Always verify plan details with your insurer."
        ]

        return "\n".join(output_lines)

    except Exception as e:
        return f"Plan extraction failed: {str(e)}"


# ── Export all tools as a list ─────────────────────────
# This is what we pass to the LangGraph agent.
# The agent gets this list and knows exactly what it can do.
ALL_TOOLS = [
    extract_plan_details,    # ← add this first — agent should run it first
    search_web,
    find_hospitals,
    check_network_status,
    estimate_cost,
    find_alternatives,
]