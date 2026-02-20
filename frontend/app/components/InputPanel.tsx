// components/InputPanel.tsx
// Left column input panel.
// Contains the three input mode tabs and their content.
// Text tab is the default — voice and upload are alternatives.

"use client"

import { type InputMode } from "../page"
import VoiceInput from "./VoiceInput"
import InsuranceUpload from "./InsuranceUpload"

interface InputPanelProps {
  inputMode:        InputMode
  setInputMode:     (mode: InputMode) => void
  insuranceInput:   string
  setInsuranceInput:(val: string) => void
  careNeeded:       string
  setCareNeeded:    (val: string) => void
  zipCode:          string
  setZipCode:       (val: string) => void
  isLoading:        boolean
  onSubmit:         () => void
  onVoiceResult:    (text: string) => void
  onUploadResult:   (text: string) => void
  error:            string | null
}

const TABS: { id: InputMode; label: string }[] = [
  { id: "text",   label: "Type"   },
  { id: "voice",  label: "Voice"  },
  { id: "upload", label: "Upload" },
]

export default function InputPanel({
  inputMode,
  setInputMode,
  insuranceInput,
  setInsuranceInput,
  careNeeded,
  setCareNeeded,
  zipCode,
  setZipCode,
  isLoading,
  onSubmit,
  onVoiceResult,
  onUploadResult,
  error,
}: InputPanelProps) {

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !isLoading) onSubmit()
  }

  return (
    <div className="card input-panel">

      {/* Tab switcher */}
      <div className="tab-bar">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${inputMode === tab.id ? "active" : ""}`}
            onClick={() => setInputMode(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="tab-content">

        {/* Text tab */}
        {inputMode === "text" && (
          <div className="text-tab">

            <div className="field-group">
              <label className="input-label">Insurance Plan</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Humana Gold Plus HMO"
                value={insuranceInput}
                onChange={e => setInsuranceInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
              />
              <p className="field-hint">
                Leave blank to use standard Medicare rates
              </p>
            </div>

            <div className="field-group">
              <label className="input-label">Care Needed</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. knee MRI, colonoscopy, annual physical"
                value={careNeeded}
                onChange={e => setCareNeeded(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
              />
            </div>

            <div className="field-group">
              <label className="input-label">Zip Code</label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. 11201"
                value={zipCode}
                onChange={e => setZipCode(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
                maxLength={10}
              />
            </div>

            {/* Error message */}
            {error && (
              <div className="input-error">
                {error}
              </div>
            )}

            {/* Submit button */}
            <button
              className="btn-primary find-cost-btn"
              onClick={onSubmit}
              disabled={isLoading}
            >
              {isLoading ? "Finding your cost..." : "Find My Cost"}
            </button>

          </div>
        )}

        {/* Voice tab */}
        {inputMode === "voice" && (
          <VoiceInput
            onResult={onVoiceResult}
            isLoading={isLoading}
            onSubmit={onSubmit}
            insuranceInput={insuranceInput}
            careNeeded={careNeeded}
            zipCode={zipCode}
            setZipCode={setZipCode}
          />
        )}

        {/* Upload tab */}
        {inputMode === "upload" && (
          <InsuranceUpload
            onResult={onUploadResult}
            isLoading={isLoading}
            onSubmit={onSubmit}
            careNeeded={careNeeded}
            setCareNeeded={setCareNeeded}
            zipCode={zipCode}
            setZipCode={setZipCode}
          />
        )}

      </div>
    </div>
  )
}