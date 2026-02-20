# routes/voice.py
# POST /api/voice/transcribe
#
# Accepts an audio file from the frontend microphone.
# Sends it to OpenAI Whisper for transcription.
# Cleans up the transcription with GPT-4o.
# Returns clean text ready to send to /api/estimate.

import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException  # type: ignore[reportMissingImports]
from langchain_openai import ChatOpenAI  # type: ignore[reportMissingImports]
from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore[reportMissingImports]
from openai import OpenAI  # type: ignore[reportMissingImports]

from config import OPENAI_API_KEY
from agent.prompts import VOICE_CLEANUP_PROMPT

router = APIRouter()

openai_client = OpenAI(api_key=OPENAI_API_KEY)

cleanup_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=OPENAI_API_KEY
)


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Transcribe voice input to text using OpenAI Whisper.

    Accepts any common audio format: webm, mp4, wav, m4a.
    The browser's MediaRecorder API typically produces webm.

    Flow:
    1. Save uploaded audio to a temp file
    2. Send to Whisper API
    3. Clean up medical term mishearings with GPT-4o
    4. Return clean text

    The frontend sends this directly to /api/estimate
    as the insurance_input or care_needed field.
    """

    # Validate file type
    # Whisper supports: mp3, mp4, mpeg, mpga, m4a, wav, webm
    # Check loosely — browser often sends "audio/webm;codecs=opus"
# which won't match an exact set check
    content_type = audio.content_type or "audio/webm"
    is_allowed = any(
        content_type.startswith(t) for t in [
            "audio/webm", "audio/mp4", "audio/wav",
            "audio/mpeg", "audio/m4a", "audio/x-m4a",
            "audio/ogg", "audio/"
        ]
    )

    if not is_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type: {content_type}"
        )

    # Save to temp file
    # Whisper needs a real file path, not a stream
    # tempfile creates a file that deletes itself when closed
    suffix = ".webm"
    if audio.filename:
        ext = os.path.splitext(audio.filename)[-1]
        if ext:
            suffix = ext

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False
        ) as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Send to Whisper
        # model="whisper-1" is the only available Whisper model via API
        with open(tmp_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                # language hint improves accuracy for medical terms
                language="en"
            )

        raw_text = transcription.text

        if not raw_text or not raw_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No speech detected in audio"
            )

        # Clean up the transcription
        # Whisper often mishears medical terms like
        # "colonoscopy" as "colon oscopy" or
        # "Humana" as "human a"
        cleanup_response = cleanup_llm.invoke([
            SystemMessage(content=VOICE_CLEANUP_PROMPT),
            HumanMessage(content=raw_text)
        ])

        clean_text = cleanup_response.content.strip()

        return {
            "raw_transcription":   raw_text,
            "clean_transcription": clean_text,
            "success":             True
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {str(e)}"
        )

    finally:
        # Always clean up the temp file
        # even if an error occurred
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

from pydantic import BaseModel  # type: ignore[reportMissingImports]

class ClassifyRequest(BaseModel):
    text: str

@router.post("/classify")
async def classify_voice(request: ClassifyRequest):
    """
    Classify transcribed voice input into structured fields.
    Uses GPT-4o to extract insurance plan, care needed, and zip code
    from a single natural language sentence.
    """
    classify_prompt = """
You are extracting structured fields from a voice input for a Medicare cost estimator.

The user spoke one sentence describing what they need. Extract these fields:
- insurance_input: the insurance plan name if mentioned (e.g. "Humana Gold Plus HMO")
- care_needed: the medical procedure or care they need (e.g. "knee MRI", "colonoscopy")
- zip_code: 5-digit zip code if mentioned

RULES:
- Only extract what was explicitly said
- If a field was not mentioned return null
- care_needed is the most important field — always try to extract it
- Return valid JSON only

EXAMPLES:

Input: "I need a knee MRI with my Humana Gold Plus plan in zip 11201"
Output: {"insurance_input": "Humana Gold Plus", "care_needed": "knee MRI", "zip_code": "11201"}

Input: "colonoscopy near Brooklyn"
Output: {"insurance_input": null, "care_needed": "colonoscopy", "zip_code": null}

Input: "I have Aetna Medicare Advantage"
Output: {"insurance_input": "Aetna Medicare Advantage", "care_needed": null, "zip_code": null}

Input: "annual physical zip code 10001"
Output: {"insurance_input": null, "care_needed": "annual physical", "zip_code": "10001"}
"""

    try:
        from openai import OpenAI  # type: ignore[reportMissingImports]
        import json
        from config import OPENAI_API_KEY

        client   = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": classify_prompt},
                {"role": "user",   "content": request.text}
            ],
            max_tokens=150
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "insurance_input": result.get("insurance_input"),
            "care_needed":     result.get("care_needed"),
            "zip_code":        result.get("zip_code"),
            "original_text":   request.text,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Classification failed: {str(e)}"
        )
