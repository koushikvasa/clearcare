# routes/image.py
# POST /api/image/parse-card  — reads insurance card photo
# POST /api/image/parse-records — reads medical records PDF
#
# Both endpoints:
# 1. Accept a file upload
# 2. Save it temporarily
# 3. Pass the path to extract_plan_details or severity assessment
# 4. Delete the temp file
# 5. Return extracted data

import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException  # type: ignore[reportMissingImports]
from langchain_openai import ChatOpenAI  # type: ignore[reportMissingImports]
from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore[reportMissingImports]
from openai import OpenAI  # type: ignore[reportMissingImports]
import base64
import json

from config import OPENAI_API_KEY
from agent.prompts import INSURANCE_EXTRACTION_PROMPT, SEVERITY_ASSESSMENT_PROMPT
from agent.tools import extract_plan_details

router = APIRouter()

openai_client = OpenAI(api_key=OPENAI_API_KEY)


def encode_image(path: str) -> tuple[str, str]:
    """
    Encode an image file to base64 for the Vision API.
    Returns tuple of (base64_data, media_type).
    """
    ext = os.path.splitext(path)[-1].lower()
    media_map = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".webp": "image/webp",
        ".pdf":  "application/pdf",
    }
    media_type = media_map.get(ext, "image/jpeg")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return data, media_type


@router.post("/parse-card")
async def parse_insurance_card(file: UploadFile = File(...)):
    """
    Extract insurance plan details from a card photo or PDF.

    Accepts: jpg, jpeg, png, webp, pdf
    Returns: extracted plan details including plan name,
             deductible, copays, and member ID.

    The returned insurance_input string goes directly into
    the insurance_input field of POST /api/estimate.
    """
    allowed = {
        "image/jpeg", "image/png", "image/webp",
        "application/pdf"
    }

    content_type = file.content_type or "image/jpeg"

    if content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}"
        )

    # Determine file extension for temp file
    ext_map = {
        "image/jpeg":       ".jpg",
        "image/png":        ".png",
        "image/webp":       ".webp",
        "application/pdf":  ".pdf",
    }
    suffix = ext_map.get(content_type, ".jpg")

    tmp_path = None
    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Determine input type for extract_plan_details
        input_type = "pdf" if suffix == ".pdf" else "image"

        # Call the extract_plan_details tool
        result = extract_plan_details.invoke({
            "input_type": input_type,
            "text_input": "",
            "file_path":  tmp_path
        })

        return {
            "extracted_text": result,
            "input_type":     input_type,
            "success":        True
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Card parsing failed: {str(e)}"
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/parse-records")
async def parse_medical_records(file: UploadFile = File(...)):
    """
    Extract severity and relevant history from medical records.

    Accepts: jpg, jpeg, png, pdf
    Returns: severity assessment and key conditions found.

    The returned medical_history string goes into the
    medical_history field of POST /api/estimate.
    """
    allowed = {
        "image/jpeg", "image/png",
        "image/webp", "application/pdf"
    }

    content_type = file.content_type or "image/jpeg"

    if content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}"
        )

    ext_map = {
        "image/jpeg":      ".jpg",
        "image/png":       ".png",
        "image/webp":      ".webp",
        "application/pdf": ".pdf",
    }
    suffix = ext_map.get(content_type, ".jpg")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # For PDFs extract text first
        # For images encode to base64 for Vision API
        if suffix == ".pdf":
            try:
                import pypdf  # type: ignore[reportMissingImports]
                text = ""
                with open(tmp_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages[:3]:
                        text += page.extract_text() or ""
                file_content = text[:4000]
                use_vision   = False
            except Exception:
                file_content = ""
                use_vision   = True
        else:
            file_content = ""
            use_vision   = True

        if use_vision:
            img_data, media_type = encode_image(tmp_path)
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": SEVERITY_ASSESSMENT_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Assess the severity and extract relevant medical history from these records."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{img_data}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
        else:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": SEVERITY_ASSESSMENT_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Assess severity from these medical records:\n\n{file_content}"
                    }
                ],
                max_tokens=500
            )

        result = json.loads(response.choices[0].message.content)

        return {
            "severity":         result.get("severity", "moderate"),
            "severity_score":   result.get("severity_score", 2),
            "key_conditions":   result.get("key_conditions", []),
            "relevant_history": result.get("relevant_history", ""),
            "disclaimer":       result.get("disclaimer", ""),
            "success":          True
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Records parsing failed: {str(e)}"
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)