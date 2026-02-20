// components/InsuranceUpload.tsx
// Upload tab — drag and drop insurance card or PDF.
// Extracts plan details via GPT-4o Vision.
// Also collects care needed and zip code.

"use client"

import { useState, useRef, useCallback } from "react"

interface InsuranceUploadProps {
  onResult:       (text: string) => void
  isLoading:      boolean
  onSubmit:       () => void
  careNeeded:     string
  setCareNeeded:  (val: string) => void
  zipCode:        string
  setZipCode:     (val: string) => void
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"]
const MAX_SIZE_MB   = 10

export default function InsuranceUpload({
  onResult,
  isLoading,
  onSubmit,
  careNeeded,
  setCareNeeded,
  zipCode,
  setZipCode,
}: InsuranceUploadProps) {

  const [isDragging,   setIsDragging]   = useState(false)
  const [isUploading,  setIsUploading]  = useState(false)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [extracted,    setExtracted]    = useState("")
  const [error,        setError]        = useState("")

  const fileInputRef = useRef<HTMLInputElement>(null)

  const processFile = useCallback(async (file: File) => {
    setError("")

    // Validate type
    if (!ALLOWED_TYPES.includes(file.type)) {
      setError("Please upload a JPG, PNG, WEBP, or PDF file")
      return
    }

    // Validate size
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`File too large. Maximum size is ${MAX_SIZE_MB}MB`)
      return
    }

    setUploadedFile(file)
    setIsUploading(true)

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await fetch(`${API_URL}/api/image/parse-card`, {
        method: "POST",
        body:   formData,
      })

      if (!response.ok) throw new Error("Upload failed")

      const data = await response.json()

      if (data.extracted_text) {
        setExtracted(data.extracted_text)
        onResult(data.extracted_text)
      } else {
        throw new Error("Could not extract plan details")
      }

    } catch {
      setError("Could not read the insurance card. Please try a clearer photo or enter your plan manually.")
      setUploadedFile(null)
    } finally {
      setIsUploading(false)
    }
  }, [onResult])

  // Drag and drop handlers
  const handleDragOver  = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true) }
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false) }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) processFile(file)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) processFile(file)
    // Reset input so same file can be re-uploaded
    e.target.value = ""
  }

  const handleClear = () => {
    setUploadedFile(null)
    setExtracted("")
    setError("")
    onResult("")
  }

  const canSubmit = extracted && careNeeded.trim() && zipCode.trim() && !isLoading

  return (
    <div className="upload-tab">

      {/* Drop zone */}
      {!uploadedFile && (
        <div
          className={`drop-zone ${isDragging ? "drop-zone--active" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.pdf"
            onChange={handleFileChange}
            className="upload-file-input"
          />

          {isUploading ? (
            <div className="drop-zone-uploading">
              <div className="loading-spinner" />
              <p className="drop-zone-text">Reading your insurance card...</p>
            </div>
          ) : (
            <>
              <div className="drop-zone-icon">
                <span className="upload-arrow" />
              </div>
              <p className="drop-zone-title">Upload Insurance Card</p>
              <p className="drop-zone-text">
                Drag and drop or tap to browse
              </p>
              <p className="drop-zone-hint">
                JPG, PNG, WEBP or PDF — max {MAX_SIZE_MB}MB
              </p>
            </>
          )}
        </div>
      )}

      {/* Uploaded file confirmation */}
      {uploadedFile && !isUploading && (
        <div className="uploaded-file">
          <div className="uploaded-file-info">
            <div className="uploaded-file-icon">
              {uploadedFile.type === "application/pdf" ? "PDF" : "IMG"}
            </div>
            <div>
              <p className="uploaded-file-name">{uploadedFile.name}</p>
              <p className="uploaded-file-size">
                {(uploadedFile.size / 1024).toFixed(0)} KB
              </p>
            </div>
          </div>
          <button className="uploaded-file-clear" onClick={handleClear}>
            Remove
          </button>
        </div>
      )}

      {/* Extracted plan details */}
      {extracted && (
        <div className="extracted-box">
          <p className="extracted-label">Plan Detected</p>
          <p className="extracted-text">
            {extracted.length > 200
              ? extracted.slice(0, 200) + "..."
              : extracted}
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="input-error">{error}</div>
      )}

      {/* Care needed */}
      <div className="field-group">
        <label className="input-label">Care Needed</label>
        <input
          type="text"
          className="input-field"
          placeholder="e.g. knee MRI, colonoscopy, annual physical"
          value={careNeeded}
          onChange={e => setCareNeeded(e.target.value)}
          disabled={isLoading}
        />
      </div>

      {/* Zip code */}
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
      <button
        className="btn-primary"
        onClick={onSubmit}
        disabled={!canSubmit}
      >
        {isLoading      ? "Finding your cost..." :
         !extracted     ? "Upload your insurance card first" :
         !careNeeded    ? "Enter care needed above" :
         !zipCode       ? "Enter zip code above" :
                          "Find My Cost"}
      </button>

    </div>
  )
}