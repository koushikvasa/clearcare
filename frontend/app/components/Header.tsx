// components/Header.tsx
// Top navigation bar for ClearCare.
// Shows logo, tagline, returning user greeting,
// and a clear data button.

"use client"

interface HeaderProps {
  greeting:    string
  isReturning: boolean
  onClearData: () => void
}

export default function Header({ greeting, isReturning, onClearData }: HeaderProps) {
  return (
    <header className="header">
      <div className="header-inner">

        {/* Left — logo and tagline */}
        <div className="header-brand">
        <div className="header-logo">
            <div className="logo-icon">C</div>
            <span className="logo-text">ClearCare</span>
        </div>
        <p className="header-tagline">
            Know what you'll pay. Before you go.
        </p>
        </div>

        {/* Center — returning user greeting */}
        {isReturning && greeting && (
          <div className="header-greeting">
            <div className="greeting-dot" />
            <span>{greeting}</span>
          </div>
        )}

        {/* Right — clear data button */}
        <div className="header-actions">
          {isReturning && (
            <button
              className="clear-data-btn"
              onClick={onClearData}
              title="Delete your saved plan details"
            >
              Clear my data
            </button>
          )}
        </div>

      </div>
    </header>
  )
}