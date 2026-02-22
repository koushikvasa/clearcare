// components/InsuranceSavings.tsx
// Shows the financial impact of the patient's insurance plan.
// Before/after comparison: full procedure cost vs what they actually pay.
// The "aha" moment that proves ClearCare's value.

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

  // Don't render if we don't have enough data to show a meaningful comparison
  if (!procedureCost || !patientCost || procedureCost <= patientCost) return null

  const savingsPct = Math.round((savings / procedureCost) * 100)

  return (
    <div className="card insurance-savings fade-in-up">

      <div className="savings-header">
        <div>
          <h3 className="savings-title">Your Insurance Saves You</h3>
          <p className="savings-subtitle">
            {usedDefaults ? "Standard Medicare estimate" : planName}
          </p>
        </div>
        <div className="savings-badge">
          -{savingsPct}%
        </div>
      </div>

      <div className="savings-rows">

        <div className="savings-row">
          <span className="savings-label">Full procedure cost</span>
          <span className="savings-amount savings-amount--base">
            ${procedureCost.toLocaleString()}
          </span>
        </div>

        <div className="savings-row">
          <span className="savings-label">Your out-of-pocket</span>
          <span className="savings-amount savings-amount--yours">
            ${patientCost.toLocaleString()}
          </span>
        </div>

        <div className="savings-divider" />

        <div className="savings-row savings-row--total">
          <span className="savings-label savings-label--total">You save</span>
          <span className="savings-amount savings-amount--total">
            ${savings.toLocaleString()}
          </span>
        </div>

      </div>

      {usedDefaults && (
        <p className="savings-note">
          Add your insurance plan above for a more accurate calculation.
        </p>
      )}

    </div>
  )
}
