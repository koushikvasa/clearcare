// components/InsuranceSavings.tsx
// Shows the financial impact of the patient's insurance plan.
// Uses the same section pattern as ResultsPanel so the card looks native.

"use client"

import { Hospital } from "../page"

interface InsuranceSavingsProps {
  hospitals:    Hospital[]
  yourCost:     number | null
  planName:     string
  usedDefaults: boolean
}

export default function InsuranceSavings({
  hospitals,
  yourCost,
  planName,
  usedDefaults,
}: InsuranceSavingsProps) {

  const topHospital   = hospitals?.[0]
  const procedureCost = topHospital?.procedure_cost ?? 0
  const patientCost   = yourCost ?? topHospital?.estimated_cost ?? 0
  const savings       = procedureCost > patientCost ? procedureCost - patientCost : 0
  const savingsPct    = procedureCost > 0 ? Math.round((savings / procedureCost) * 100) : 0
  const hasSavings    = procedureCost > 0 && savings > 0

  // Need at least a patient cost to render anything
  if (!patientCost) return null

  const planLabel = usedDefaults
    ? "Standard Medicare estimate"
    : (planName || "Your plan")

  return (
    <div className="card fade-in-up">

      {/* Savings headline */}
      <div className="cost-section">
        <div className="cost-top">
          <div>
            <p className="cost-label">
              {hasSavings ? "Your Insurance Saves You" : "Your Out-of-Pocket Cost"}
            </p>
            <div className="cost-amount">
              {hasSavings ? `$${savings.toLocaleString()}` : `$${patientCost.toLocaleString()}`}
            </div>
            <p className="cost-explanation">{planLabel}</p>
          </div>
          {hasSavings && (
            <div className="network-badge-wrap">
              <span className="badge-in-network">-{savingsPct}%</span>
            </div>
          )}
        </div>
      </div>

      {/* Before / after breakdown */}
      <div className="confidence-section">
        {hasSavings && (
          <div className="alternative-row">
            <span className="alt-label">Full procedure cost</span>
            <span className="alt-cost">${procedureCost.toLocaleString()}</span>
          </div>
        )}

        <div className="alternative-row savings-yours-row">
          <span className="alt-label">Your out-of-pocket</span>
          <span className="alt-cost savings-yours-cost">${patientCost.toLocaleString()}</span>
        </div>

        {usedDefaults && (
          <p className="savings-defaults-note">
            Add your insurance plan above for a more accurate calculation.
          </p>
        )}
      </div>

    </div>
  )
}
