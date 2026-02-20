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

  const [inputMode,      setInputMode]      = useState<InputMode>("text")
  const [insuranceInput, setInsuranceInput] = useState("")
  const [careNeeded,     setCareNeeded]     = useState("")
  const [zipCode,        setZipCode]        = useState("")
  const [medicalHistory, setMedicalHistory] = useState("")

  const [sessionId,    setSessionId]    = useState("")
  const [isReturning,  setIsReturning]  = useState(false)
  const [greeting,     setGreeting]     = useState("")

  const [isLoading,    setIsLoading]    = useState(false)
  const [currentStep,  setCurrentStep]  = useState("")
  const [stepIndex,    setStepIndex]    = useState(0)

  const [result,       setResult]       = useState<EstimateResult | null>(null)
  const [error,        setError]        = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem("clearcare_session_id")
    const id     = stored || crypto.randomUUID()
    if (!stored) localStorage.setItem("clearcare_session_id", id)
    setSessionId(id)

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
      .catch(() => {})
  }, [])

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
        return prev
      })
    }, 2200)
    return () => clearInterval(interval)
  }, [isLoading])

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
          care_needed:     careNeeded.trim(),
          zip_code:        zipCode.trim(),
          insurance_input: insuranceInput.trim(),
          input_type:      "text",
          medical_history: medicalHistory.trim(),
          session_id:      sessionId,
        }),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || "Something went wrong")
      }

      const data: EstimateResult = await response.json()
      setResult(data)
      if (data.greeting) setGreeting(data.greeting)

    } catch (err: any) {
      setError(err.message || "Failed to get estimate. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }, [careNeeded, zipCode, insuranceInput, medicalHistory, sessionId])

  const handleVoiceResult = useCallback(async (text: string) => {
    if (!text.trim()) return
  
    // Use GPT-4o to classify what the user said
    // into insurance input, care needed, or both
    try {
      const response = await fetch(`${API_URL}/api/voice/classify`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ text }),
      })
  
      if (response.ok) {
        const data = await response.json()
        if (data.insurance_input) setInsuranceInput(data.insurance_input)
        if (data.care_needed)     setCareNeeded(data.care_needed)
        if (data.zip_code)        setZipCode(data.zip_code)
        return
      }
    } catch {
      // Fall back to putting everything in care_needed
    }
  
    // Fallback if classify endpoint fails
    setCareNeeded(text)
  }, [API_URL])

  const handleUploadResult = useCallback((extractedText: string) => {
    setInsuranceInput(extractedText)
  }, [])

  const handleClearData = useCallback(async () => {
    if (!sessionId) return
    await fetch(`${API_URL}/api/estimate/session/${sessionId}`, { method: "DELETE" })
    localStorage.removeItem("clearcare_session_id")
    setInsuranceInput("")
    setZipCode("")
    setResult(null)
    setIsReturning(false)
    setGreeting("")
    const newId = crypto.randomUUID()
    localStorage.setItem("clearcare_session_id", newId)
    setSessionId(newId)
  }, [sessionId])

  return (
    <div className="page-wrapper">

      <Header
        greeting={greeting}
        isReturning={isReturning}
        onClearData={handleClearData}
      />

      <main className="main-content">
        <div className="main-grid">

          {/* Left column */}
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

            {result && (
              <AIAnalysis
                spokenSummary={result.spoken_summary}
                nextStep={result.next_step}
                usedDefaults={result.used_defaults}
              />
            )}

            {result &&  (
              <div className="fade-in-up">
                <HospitalCards hospitals={result.hospitals} />
              </div>
            )}
          </div>

          {/* Right column */}
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

            {result && (
              <div className="fade-in-up">
                <HospitalMap hospitals={result.hospitals} />
              </div>
            )}
          </div>

        </div>
      </main>

      <Footer />

    </div>
  )
}