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
    allowed_types = {
        "audio/webm", "audio/mp4", "audio/wav",
        "audio/mpeg", "audio/m4a", "audio/x-m4a"
    }

    if audio.content_type and audio.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type: {audio.content_type}"
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