// components/ScoreLoop.tsx
// Self-critique score display.
// Animates the composite score and 4 dimension bars
// after the result arrives.
// This is the "self-improving agent" demo moment.

"use client"

import { useEffect, useState } from "react"
import { ScoreIteration } from "../page"

interface ScoreLoopProps {
  scoreHistory: ScoreIteration[]
  finalScore:   number
}

const DIMENSIONS = [
  { key: "completeness", label: "Completeness" },
  { key: "accuracy",     label: "Accuracy"     },
  { key: "clarity",      label: "Clarity"      },
  { key: "safety",       label: "Safety"       },
] as const

export default function ScoreLoop({ scoreHistory, finalScore }: ScoreLoopProps) {

  // displayScore animates from 0 up to the final score
  const [displayScore,  setDisplayScore]  = useState(0)
  const [displayBars,   setDisplayBars]   = useState<Record<string, number>>({
    completeness: 0,
    accuracy:     0,
    clarity:      0,
    safety:       0,
  })
  const [currentIteration, setCurrentIteration] = useState(0)

  useEffect(() => {
    if (!scoreHistory || scoreHistory.length === 0) return

    // Reset on new result
    setDisplayScore(0)
    setDisplayBars({ completeness: 0, accuracy: 0, clarity: 0, safety: 0 })
    setCurrentIteration(0)

    // Animate through each iteration with a delay between them
    // This makes the score climbing visible even with 1 iteration
    scoreHistory.forEach((iteration, index) => {
      setTimeout(() => {
        setCurrentIteration(index + 1)

        // Animate score number counting up
        const target    = iteration.composite
        const start     = index === 0 ? 0 : scoreHistory[index - 1].composite
        const duration  = 800
        const steps     = 40
        const increment = (target - start) / steps

        let current = start
        const counter = setInterval(() => {
          current += increment
          if (current >= target) {
            current = target
            clearInterval(counter)
          }
          setDisplayScore(Math.round(current))
        }, duration / steps)

        // Update bars for this iteration
        setDisplayBars({
          completeness: iteration.completeness,
          accuracy:     iteration.accuracy,
          clarity:      iteration.clarity,
          safety:       iteration.safety,
        })

      }, index * 1500)
    })

  }, [scoreHistory])

  if (!scoreHistory || scoreHistory.length === 0) return null

  // Color the composite score based on value
  const scoreColor =
    displayScore >= 80 ? "var(--teal)" :
    displayScore >= 60 ? "var(--orange)" :
    "var(--red)"

  return (
    <div className="card score-loop fade-in-up">

      {/* Header */}
      <div className="score-header">
        <div>
          <h3 className="score-title">Answer Quality</h3>
          <p className="score-subtitle">Self-verified by AI</p>
        </div>

        {/* Big score number */}
        <div className="score-circle" style={{ borderColor: scoreColor }}>
          <span className="score-number" style={{ color: scoreColor }}>
            {displayScore}
          </span>
          <span className="score-max">/100</span>
        </div>
      </div>

      {/* Iteration indicator */}
      {scoreHistory.length > 0 && (
        <div className="iteration-row">
          <span className="iteration-label">
            {currentIteration < scoreHistory.length
              ? `Reviewing... iteration ${currentIteration}`
              : finalScore >= 80
                ? "Quality check passed"
                : `Completed ${scoreHistory.length} iteration${scoreHistory.length > 1 ? "s" : ""}`
            }
          </span>
          <div className="iteration-dots">
            {scoreHistory.map((_, i) => (
              <div
                key={i}
                className={`iteration-dot ${i < currentIteration ? "filled" : ""}`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Dimension bars */}
      <div className="dimension-bars">
        {DIMENSIONS.map(dim => (
          <div key={dim.key} className="dimension-row">
            <span className="dimension-label">{dim.label}</span>
            <div className="dimension-bar-wrap">
              <div className="score-bar-track">
                <div
                  className="score-bar-fill"
                  style={{ width: `${displayBars[dim.key]}%` }}
                />
              </div>
              <span className="dimension-value">
                {displayBars[dim.key]}
              </span>
            </div>
          </div>
        ))}
      </div>

    </div>
  )
}