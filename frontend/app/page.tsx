// app/page.tsx
// Main page — holds all state and orchestrates the UI.
// Every component is a child of this page.
// This is the only file that talks to the backend API.

"use client"

import { useState, useEffect, useCallback } from "react"
import Header from "./components/Header"
import InputPanel from "./components/InputPanel"
import ResultsPanel from "./components/ResultsPanel"
import HospitalMap from "./components/HospitalMap"
import HospitalCards from "./components/HospitalCards"
import AIAnalysis from "./components/AIAnalysis"
import ScoreLoop from "./components/ScoreLoop"
import Footer from "./components/Footer"

// ── Types ─────────────────────────────────────────
// These match exactly what the backend returns
// so TypeScript catches mismatches early

export interface Hospital {
  hospital:       string
  address:        string
  phone:          string
  network_status: string
  estimated_cost: number
}

export interface ScoreIteration {
  iteration:    number
  completeness: number
  accuracy:     number
  clarity:      number
  safety:       number
  composite:    number
}

export interface EstimateResult {
  headline:                string
  spoken_summary:          string
  next_step:               string
  in_network_cost:         number | null
  out_of_network_cost:     number | null
  alternative_cost:        number | null
  alternative_description: string | null
  confidence:              number
  hospitals:               Hospital[]
  score_history:           ScoreIteration[]
  final_score:             number
  iterations:              number
  used_defaults:           boolean
  session_id:              string
  is_returning_user:       boolean
  greeting:                string
}

export type InputMode = "text" | "voice" | "upload"

// Agent pipeline steps shown during loading
const AGENT_STEPS = [
  "Extracting plan details...",
  "Assessing severity...",
  "Finding nearby hospitals...",
  "Checking network status...",
  "Estimating costs...",
  "Finding alternatives...",
  "Generating answer...",
  "Running quality check...",
]

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function Page() {

  // ── Input state ───────────────────────────────
  const [inputMode,       setInputMode]       = useState<InputMode>("text")
  const [insuranceInput,  setInsuranceInput]  = useState("")
  const [careNeeded,      setCareNeeded]      = useState("")
  const [zipCode,         setZipCode]         = useState("")
  const [medicalHistory,  setMedicalHistory]  = useState("")

  // ── Session state ─────────────────────────────
  const [sessionId,       setSessionId]       = useState("")
  const [isReturning,     setIsReturning]     = useState(false)
  const [greeting,        setGreeting]        = useState("")

  // ── Loading state ─────────────────────────────
  const [isLoading,       setIsLoading]       = useState(false)
  const [currentStep,     setCurrentStep]     = useState("")
  const [stepIndex,       setStepIndex]       = useState(0)

  // ── Result state ──────────────────────────────
  const [result,          setResult]          = useState<EstimateResult | null>(null)
  const [error,           setError]           = useState<string | null>(null)


  // ── Session setup on mount ────────────────────
  // Generate or load session ID from localStorage
  // Then check if this is a returning user
  useEffect(() => {
    const stored = localStorage.getItem("clearcare_session_id")
    const id = stored || crypto.randomUUID()

    if (!stored) {
      localStorage.setItem("clearcare_session_id", id)
    }
    setSessionId(id)

    // Check for returning user context
    fetch(`${API_URL}/api/estimate/context/${id}`)
      .then(res => res.json())
      .then(ctx => {
        if (ctx.is_returning) {
          setIsReturning(true)
          setGreeting(ctx.greeting || "")
          if (ctx.insurance_input) setInsuranceInput(ctx.insurance_input)
          if (ctx.zip_code)        setZipCode(ctx.zip_code)
        }
      })
      .catch(() => {
        // Returning user check failing should never block the app
      })
  }, [])


  // ── Agent step animation ──────────────────────
  // Cycles through steps every 2.5s while loading
  // Gives the user feedback during the 15-20s API call
  useEffect(() => {
    if (!isLoading) {
      setStepIndex(0)
      setCurrentStep("")
      return
    }

    setCurrentStep(AGENT_STEPS[0])
    const interval = setInterval(() => {
      setStepIndex(prev => {
        const next = prev + 1
        if (next < AGENT_STEPS.length) {
          setCurrentStep(AGENT_STEPS[next])
          return next
        }
        // Stay on last step until result arrives
        return prev
      })
    }, 2200)

    return () => clearInterval(interval)
  }, [isLoading])


  // ── Main API call ─────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!careNeeded.trim()) {
      setError("Please enter what care you need, e.g. knee MRI")
      return
    }
    if (!zipCode.trim()) {
      setError("Please enter your zip code")
      return
    }

    setError(null)
    setResult(null)
    setIsLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/estimate/`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          care_needed:      careNeeded.trim(),
          zip_code:         zipCode.trim(),
          insurance_input:  insuranceInput.trim(),
          input_type:       "text",
          medical_history:  medicalHistory.trim(),
          session_id:       sessionId,
        }),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || "Something went wrong")
      }

      const data: EstimateResult = await response.json()
      setResult(data)

      // Update greeting if this was a new session
      if (data.greeting) setGreeting(data.greeting)

    } catch (err: any) {
      setError(err.message || "Failed to get estimate. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }, [careNeeded, zipCode, insuranceInput, medicalHistory, sessionId])


  // ── Voice input callback ──────────────────────
  // Called by VoiceInput component with clean transcription
  const handleVoiceResult = useCallback((text: string) => {
    // Try to parse care needed from voice
    // Simple heuristic: if it mentions a plan, put in insurance
    // otherwise put in care needed
    const planKeywords = ["humana", "aetna", "united", "cigna", "medicare", "plan", "hmo", "ppo"]
    const hasPlan = planKeywords.some(k => text.toLowerCase().includes(k))

    if (hasPlan) {
      setInsuranceInput(text)
    } else {
      setCareNeeded(text)
    }
  }, [])


  // ── Upload callback ───────────────────────────
  // Called by InsuranceUpload with extracted plan text
  const handleUploadResult = useCallback((extractedText: string) => {
    setInsuranceInput(extractedText)
  }, [])


  // ── Clear session ─────────────────────────────
  const handleClearData = useCallback(async () => {
    if (!sessionId) return
    await fetch(`${API_URL}/api/estimate/session/${sessionId}`, {
      method: "DELETE"
    })
    localStorage.removeItem("clearcare_session_id")
    setInsuranceInput("")
    setZipCode("")
    setResult(null)
    setIsReturning(false)
    setGreeting("")
    // Generate new session
    const newId = crypto.randomUUID()
    localStorage.setItem("clearcare_session_id", newId)
    setSessionId(newId)
  }, [sessionId])


  // ── Render ────────────────────────────────────
  return (
    <div className="page-wrapper">

      <Header
        greeting={greeting}
        isReturning={isReturning}
        onClearData={handleClearData}
      />

      <main className="main-content">
        <div className="main-grid">

          {/* Left column — input panel */}
          <div className="left-column">
            <InputPanel
              inputMode={inputMode}
              setInputMode={setInputMode}
              insuranceInput={insuranceInput}
              setInsuranceInput={setInsuranceInput}
              careNeeded={careNeeded}
              setCareNeeded={setCareNeeded}
              zipCode={zipCode}
              setZipCode={setZipCode}
              isLoading={isLoading}
              onSubmit={handleSubmit}
              onVoiceResult={handleVoiceResult}
              onUploadResult={handleUploadResult}
              error={error}
            />

            {/* AI Analysis shows below input after result arrives */}
            {result && (
              <AIAnalysis
                spokenSummary={result.spoken_summary}
                nextStep={result.next_step}
                usedDefaults={result.used_defaults}
              />
            )}
          </div>

          {/* Right column — results */}
          <div className="right-column">
            <ResultsPanel
              result={result}
              isLoading={isLoading}
              currentStep={currentStep}
              stepIndex={stepIndex}
              agentSteps={AGENT_STEPS}
            />

            {result && (
              <ScoreLoop
                scoreHistory={result.score_history}
                finalScore={result.final_score}
              />
            )}
          </div>

        </div>

        {/* Map + cards — full width below the grid */}
        {result && result.hospitals.length > 0 && (
          <div className="full-width-section fade-in-up">
            <HospitalMap hospitals={result.hospitals} />
            <HospitalCards hospitals={result.hospitals} />
          </div>
        )}

      </main>

      <Footer />

    </div>
  )
}