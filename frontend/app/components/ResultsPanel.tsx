// components/ResultsPanel.tsx
// Right column — shows loading state and cost results.
// Loading: agent steps animate one by one.
// Result: cost headline, network badge, confidence score.

"use client"

import { EstimateResult } from "../page"

interface ResultsPanelProps {
  result:      EstimateResult | null
  isLoading:   boolean
  currentStep: string
  stepIndex:   number
  agentSteps:  string[]
}

export default function ResultsPanel({
  result,
  isLoading,
  currentStep,
  stepIndex,
  agentSteps,
}: ResultsPanelProps) {

  // Empty state — nothing submitted yet
  if (!isLoading && !result) {
    return (
      <div className="card results-empty">
        <div className="empty-icon">$</div>
        <h3 className="empty-title">Your cost estimate will appear here</h3>
        <p className="empty-desc">
          Enter your insurance plan and what care you need, then click Find My Cost.
        </p>
      </div>
    )
  }

  // Loading state — agent pipeline running
  if (isLoading) {
    return (
      <div className="card results-loading">
        <div className="loading-header">
          <div className="loading-spinner" />
          <span className="loading-title">ClearCare is working...</span>
        </div>

        <div className="agent-steps">
          {agentSteps.map((step, i) => {
            const isDone    = i < stepIndex
            const isCurrent = i === stepIndex
            const isPending = i > stepIndex

            return (
              <div
                key={step}
                className={`agent-step ${isDone ? "done" : ""} ${isCurrent ? "current" : ""} ${isPending ? "pending" : ""}`}
              >
                <div className="step-dot">
                  {isDone && <span className="step-check">✓</span>}
                  {isCurrent && <div className="step-pulse" />}
                </div>
                <span className="step-label">{step}</span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // Result state
  if (!result) return null

  const networkStatus = result.hospitals?.[0]?.network_status || "unknown"
  const inNetwork     = networkStatus === "in-network"
  const acceptsMed    = networkStatus === "accepts-medicare"

  return (
    <div className="card results-panel fade-in-up">

      {/* Cost headline */}
      <div className="cost-section">
        <div className="cost-top">
          <div>
            <p className="cost-label">Estimated Cost</p>
            <div className="cost-amount">
            {result.in_network_cost
                ? "$" + result.in_network_cost.toLocaleString()
                : result.alternative_cost
                ? "$" + result.alternative_cost.toLocaleString()
                : "See below"}
            </div>
            <p className="cost-explanation">{result.headline}</p>
          </div>

          {/* Network badge */}
          <div className="network-badge-wrap">
            {inNetwork && (
              <span className="badge-in-network">In Network</span>
            )}
            {acceptsMed && (
              <span className="badge-in-network">Accepts Medicare</span>
            )}
            {!inNetwork && !acceptsMed && (
              <span className="badge-unknown">Network Unknown</span>
            )}
          </div>
        </div>

        {/* Alternative cost if available */}
        {result.alternative_cost && (
          <div className="alternative-row">
            <span className="alt-label">Cheaper alternative</span>
            <span className="alt-cost">
              ${result.alternative_cost.toLocaleString()}
            </span>
          </div>
        )}
      </div>

      {/* Confidence bar */}
      <div className="confidence-section">
        <div className="confidence-row">
          <span className="confidence-label">Confidence</span>
          <span className="confidence-value">
            {Math.round(result.confidence * 100)}%
          </span>
        </div>
        <div className="score-bar-track">
          <div
            className="score-bar-fill"
            style={{ width: `${Math.round(result.confidence * 100)}%` }}
          />
        </div>
      </div>

    </div>
  )
}