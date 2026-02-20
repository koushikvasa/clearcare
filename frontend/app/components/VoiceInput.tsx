// components/VoiceInput.tsx
// Voice input mode for ClearCare.
// Records audio via browser MediaRecorder API.
// Sends to Whisper for transcription.
// Shows clean transcription before submitting.

"use client"

import { useState, useRef, useCallback } from "react"

interface VoiceInputProps {
  onResult:     (text: string) => void
  isLoading:    boolean
  onSubmit:     () => void
  insuranceInput: string
  careNeeded:   string
  zipCode:      string
  setZipCode:   (val: string) => void
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function VoiceInput({
  onResult,
  isLoading,
  onSubmit,
  insuranceInput,
  careNeeded,
  zipCode,
  setZipCode,
}: VoiceInputProps) {

  const [isRecording,     setIsRecording]     = useState(false)
  const [isTranscribing,  setIsTranscribing]  = useState(false)
  const [transcription,   setTranscription]   = useState("")
  const [error,           setError]           = useState("")

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef        = useRef<BlobPart[]>([])

  const startRecording = useCallback(async () => {
    setError("")
    setTranscription("")

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4"
      })

      chunksRef.current = []

      recorder.ondataavailable = e => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        // Stop all audio tracks to release the microphone
        stream.getTracks().forEach(t => t.stop())

        const mimeType = recorder.mimeType || "audio/webm"
        const blob     = new Blob(chunksRef.current, { type: mimeType })
        const ext      = mimeType.includes("mp4") ? "m4a" : "webm"

        setIsTranscribing(true)

        try {
          const formData = new FormData()
          formData.append("audio", blob, `recording.${ext}`)

          const response = await fetch(`${API_URL}/api/voice/transcribe`, {
            method: "POST",
            body:   formData,
          })

          if (!response.ok) throw new Error("Transcription failed")

          const data = await response.json()
          const text = data.clean_transcription || data.raw_transcription || ""

          setTranscription(text)
          onResult(text)

        } catch {
          setError("Could not transcribe audio. Please try again or use text input.")
        } finally {
          setIsTranscribing(false)
        }
      }

      mediaRecorderRef.current = recorder
      recorder.start()
      setIsRecording(true)

    } catch {
      setError("Microphone access denied. Please allow microphone access and try again.")
    }
  }, [onResult])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }, [isRecording])

  const handleOrbClick = () => {
    if (isLoading || isTranscribing) return
    if (isRecording) stopRecording()
    else             startRecording()
  }

  const handleClear = () => {
    setTranscription("")
    setError("")
  }

  return (
    <div className="voice-tab">

      {/* Animated orb */}
      <div className="orb-wrap">
        <button
          className={`voice-orb ${isRecording ? "voice-orb--recording" : ""} ${isTranscribing ? "voice-orb--processing" : ""}`}
          onClick={handleOrbClick}
          disabled={isLoading || isTranscribing}
        >
          {isTranscribing ? (
            <span className="orb-spinner" />
          ) : isRecording ? (
            <span className="orb-stop" />
          ) : (
            <span className="orb-mic">
              <span className="mic-body" />
              <span className="mic-stand" />
              <span className="mic-base" />
            </span>
          )}
        </button>

        <p className="orb-label">
          {isTranscribing ? "Transcribing..."  :
           isRecording    ? "Tap to stop"      :
           transcription  ? "Tap to record again" :
                            "Tap to speak"}
        </p>
      </div>

      {/* Transcription preview */}
      {transcription && !isRecording && (
        <div className="transcription-box">
          <div className="transcription-header">
            <span className="transcription-label">Heard</span>
            <button className="transcription-clear" onClick={handleClear}>
              Clear
            </button>
          </div>
          <p className="transcription-text">{transcription}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="input-error">{error}</div>
      )}

      {/* Zip code — still needed in voice mode */}
      <div className="field-group">
        <label className="input-label">Zip Code</label>
        <input
          type="text"
          className="input-field"
          placeholder="e.g. 11201"
          value={zipCode}
          onChange={e => setZipCode(e.target.value)}
          disabled={isLoading}
          maxLength={10}
        />
      </div>

      {/* Submit */}
      {transcription && (
        <button
          className="btn-primary"
          onClick={onSubmit}
          disabled={isLoading || !zipCode.trim()}
        >
          {isLoading ? "Finding your cost..." : "Find My Cost"}
        </button>
      )}

    </div>
  )
}