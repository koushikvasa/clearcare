// components/AIAnalysis.tsx
// AI-generated plain English summary shown below the input panel.
// Shows spoken summary, recommended next step, and a
// disclaimer if default Medicare values were used.

"use client"

import { useState } from "react"

interface AIAnalysisProps {
  spokenSummary: string
  nextStep:      string
  usedDefaults:  boolean
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function AIAnalysis({
  spokenSummary,
  nextStep,
  usedDefaults,
}: AIAnalysisProps) {

  const [isPlaying,  setIsPlaying]  = useState(false)
  const [audioError, setAudioError] = useState("")

  const handlePlay = async () => {
    if (isPlaying) return
    setIsPlaying(true)
    setAudioError("")

    try {
      const response = await fetch(`${API_URL}/api/voice/speak`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ text: spokenSummary }),
      })

      if (!response.ok) throw new Error("Voice unavailable")

      const blob        = await response.blob()
      const audioUrl    = URL.createObjectURL(blob)
      const audio       = new Audio(audioUrl)

      audio.onended = () => {
        setIsPlaying(false)
        URL.revokeObjectURL(audioUrl)
      }

      audio.onerror = () => {
        setIsPlaying(false)
        setAudioError("Could not play audio")
      }

      await audio.play()

    } catch {
      setIsPlaying(false)
      setAudioError("Voice playback unavailable")
    }
  }

  return (
    <div className="card ai-analysis">

      {/* Default values disclaimer */}
      {usedDefaults && (
        <div className="defaults-banner">
          <span className="defaults-icon">i</span>
          <p className="defaults-text">
            These estimates use standard Medicare rates. Add your insurance
            plan details above for a more accurate cost based on your
            specific deductibles and copays.
          </p>
        </div>
      )}

      {/* Header */}
      <div className="analysis-header">
        <div>
          <h3 className="analysis-title">AI Analysis</h3>
          <p className="analysis-subtitle">Plain English summary</p>
        </div>

        {/* Play button */}
        <button
          className={`play-btn ${isPlaying ? "play-btn--playing" : ""}`}
          onClick={handlePlay}
          disabled={isPlaying}
          title="Listen to summary"
        >
          {isPlaying ? (
            <span className="play-icon play-icon--pause">
              <span />
              <span />
            </span>
          ) : (
            <span className="play-icon play-icon--play" />
          )}
        </button>
      </div>

      {/* Spoken summary */}
      <div className="analysis-body">
        <p className="analysis-text">{spokenSummary}</p>
      </div>

      {/* Next step */}
      {nextStep && (
        <div className="next-step-box">
          <p className="next-step-label">Recommended Next Step</p>
          <p className="next-step-text">{nextStep}</p>
        </div>
      )}

      {/* Audio error */}
      {audioError && (
        <p className="audio-error">{audioError}</p>
      )}

    </div>
  )
}