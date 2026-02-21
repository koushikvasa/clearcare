"use client"

import { useState, useRef } from "react"

interface AIAnalysisProps {
  spokenSummary: string
  nextStep:      string
  usedDefaults:  boolean
  symptomReason: string | null   // ADD
  urgency:       string | null   // ADD
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function AIAnalysis({
  spokenSummary,
  nextStep,
  usedDefaults,
  symptomReason,   // ADD
  urgency,         // ADD
}: AIAnalysisProps) {

  const [isPlaying,  setIsPlaying]  = useState(false)
  const [isLoading,  setIsLoading]  = useState(false)
  const [audioError, setAudioError] = useState("")

  const audioRef = useRef<HTMLAudioElement | null>(null)

  const handleStop = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
    }
    setIsPlaying(false)
    setIsLoading(false)
  }

  const handlePlay = async () => {
    setAudioError("")
    setIsLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/voice/speak`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ text: spokenSummary }),
      })

      if (!response.ok) throw new Error("Voice unavailable")

      const blob     = await response.blob()
      const audioUrl = URL.createObjectURL(blob)
      const audio    = new Audio(audioUrl)

      audioRef.current = audio

      audio.onplay  = () => { setIsPlaying(true);  setIsLoading(false) }
      audio.onended = () => {
        setIsPlaying(false)
        URL.revokeObjectURL(audioUrl)
        audioRef.current = null
      }
      audio.onerror = () => {
        setIsPlaying(false)
        setIsLoading(false)
        setAudioError("Could not play audio")
      }

      await audio.play()

    } catch {
      setIsLoading(false)
      setIsPlaying(false)
      setAudioError("Voice playback unavailable")
    }
  }

  return (
    <div className="card ai-analysis">

      {usedDefaults && (
        <div className="defaults-banner">
          <span className="defaults-icon">i</span>
          <p className="defaults-text">
            These estimates use standard Medicare rates. Add your insurance
            plan details above for a more accurate cost.
          </p>
        </div>
      )}
      {symptomReason && (
      <div className="symptom-banner">
        <p className="symptom-label">
          {urgency === "urgent" ? "⚠️ Urgent" : urgency === "soon" ? "📅 See Soon" : "🩺 Routine Care"}
        </p>
        <p className="symptom-text">{symptomReason}</p>
      </div>
    )}

      <div className="analysis-header">
        <div>
          <h3 className="analysis-title">AI Analysis</h3>
          <p className="analysis-subtitle">Plain English summary</p>
        </div>

        {/* Play / Stop button */}
        <button
          className={`play-btn ${isPlaying ? "play-btn--playing" : ""} ${isLoading ? "play-btn--loading" : ""}`}
          onClick={isPlaying ? handleStop : handlePlay}
          disabled={isLoading}
          title={isPlaying ? "Stop" : "Listen"}
        >
          {isLoading ? (
            <span className="orb-spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
          ) : isPlaying ? (
            /* Stop square */
            <span style={{
              display:       "block",
              width:         14,
              height:        14,
              background:    "white",
              borderRadius:  2,
            }} />
          ) : (
            /* Play triangle */
            <span className="play-icon play-icon--play" />
          )}
        </button>
      </div>

      <div className="analysis-body">
        <p className="analysis-text">{spokenSummary}</p>
      </div>

      {nextStep && (
        <div className="next-step-box">
          <p className="next-step-label">Recommended Next Step</p>
          <p className="next-step-text">{nextStep}</p>
        </div>
      )}

      {audioError && (
        <p className="audio-error">{audioError}</p>
      )}

    </div>
  )
}