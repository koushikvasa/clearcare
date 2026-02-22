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

  const topHospital   = result.hospitals?.[0]
  const networkStatus = topHospital?.network_status || "unknown"
  const inNetwork     = networkStatus === "in-network"
  const acceptsMed    = networkStatus === "accepts-medicare"

  const displayCost = result.in_network_cost ?? result.out_of_network_cost
  const breakdown   = topHospital?.cost_breakdown || null

  return (
    <div className="card results-panel fade-in-up">

      {/* Cost headline */}
      <div className="cost-section">
        <div className="cost-top">
          <div>
            <p className="cost-label">Your Out-of-Pocket Cost</p>
            <div className="cost-amount">
              {displayCost != null && displayCost > 0
                ? "$" + displayCost.toLocaleString()
                : "See providers below"}
            </div>
            {breakdown && (
              <p className="cost-breakdown-line">{breakdown}</p>
            )}
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
            {!inNetwork && !acceptsMed && networkStatus !== "unknown" && (
              <span className="badge-out-network">Out of Network</span>
            )}
            {networkStatus === "unknown" && (
              <span className="badge-unknown">Network Unknown</span>
            )}
          </div>
        </div>

        {/* Out-of-network cost if different from display cost */}
        {result.out_of_network_cost && result.out_of_network_cost !== displayCost && (
          <div className="alternative-row">
            <span className="alt-label">Out-of-network cost</span>
            <span className="alt-cost">
              ${result.out_of_network_cost.toLocaleString()}
            </span>
          </div>
        )}

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

      {/* Signal-based confidence */}
      <div className="confidence-section">
        <div className="confidence-row">
          <span className="confidence-label">Data Confidence</span>
          <span className="confidence-value">
            {result.signal_confidence ?? Math.round(result.confidence * 100)}
            <span className="confidence-max">/100</span>
          </span>
        </div>
        <div className="score-bar-track">
          <div
            className="score-bar-fill"
            style={{ width: `${result.signal_confidence ?? Math.round(result.confidence * 100)}%` }}
          />
        </div>

        {/* Signal breakdown */}
        {result.confidence_signals && Object.keys(result.confidence_signals).length > 0 && (
          <div className="signal-breakdown">
            {SIGNAL_LABELS.map(({ key, label, max }) => {
              const earned = result.confidence_signals[key] ?? 0
              const passed = earned > 0
              return (
                <div key={key} className={`signal-row ${passed ? "signal-pass" : "signal-fail"}`}>
                  <span className="signal-icon">{passed ? "✓" : "✗"}</span>
                  <span className="signal-label">{label}</span>
                  <span className="signal-pts">{earned}/{max}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}

const SIGNAL_LABELS = [
  { key: "providers_found",      label: "Providers found near you",   max: 25 },
  { key: "insurance_recognized", label: "Insurance plan recognized",  max: 20 },
  { key: "procedure_mapped",     label: "Procedure identified",       max: 20 },
  { key: "network_checked",      label: "Network status confirmed",   max: 15 },
  { key: "costs_calculated",     label: "Cost estimate calculated",   max: 10 },
  { key: "urgency_set",          label: "Urgency level assessed",     max: 10 },
]