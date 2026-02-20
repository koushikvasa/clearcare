// components/Footer.tsx

export default function Footer() {
    return (
      <footer className="footer">
        <div className="footer-inner">
  
          {/* Left — brand */}
          <div className="footer-brand">
            <div className="footer-logo">
              <div className="logo-icon">C</div>
              <span className="logo-text">ClearCare</span>
            </div>
            <p className="footer-tagline">
              Know what you'll pay. Before you go.
            </p>
            <p className="footer-built">
              Built for Self-Improving Agents Hackathon — Creators Corner NYC
            </p>
          </div>
  
          {/* Right — links */}
          <div className="footer-links">
            <a
              href="https://github.com/koushikvasa"
              target="_blank"
              rel="noopener noreferrer"
              className="footer-link"
            >
              GitHub
            </a>
            <a
              href="https://koushikvasa.github.io"
              target="_blank"
              rel="noopener noreferrer"
              className="footer-link"
            >
              Portfolio
            </a>
            <a
              href="https://linkedin.com/in/koushik-vasa"
              target="_blank"
              rel="noopener noreferrer"
              className="footer-link"
            >
              LinkedIn
            </a>
          </div>
  
        </div>
  
        {/* Disclaimer */}
        <div className="footer-disclaimer">
          <b>
            ClearCare provides cost estimates only. Not a substitute for
            professional medical or financial advice. Always verify costs
            with your provider and insurer before scheduling care.
          </b>
          <p className="footer-copy">
            © 2026 ClearCare — Koushik Vasa
          </p>
        </div>
  
      </footer>
    )
  }