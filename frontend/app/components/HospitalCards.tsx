// components/HospitalCards.tsx
// Hospital recommendation cards below the map.
// Sorted cheapest first.
// Shows name, address, network badge, cost, call button.

"use client"

import { Hospital } from "../page"

interface HospitalCardsProps {
  hospitals: Hospital[]
}

function NetworkBadge({ status }: { status: string }) {
  if (status === "in-network" || status === "accepts-medicare") {
    return <span className="badge-in-network">
      {status === "accepts-medicare" ? "Accepts Medicare" : "In Network"}
    </span>
  }
  if (status === "out-of-network") {
    return <span className="badge-out-network">Out of Network</span>
  }
  return <span className="badge-unknown">Network Unknown</span>
}

export default function HospitalCards({ hospitals }: HospitalCardsProps) {
    if (!hospitals || hospitals.length === 0) {
        return (
          <div className="card hospitals-empty">
            <p className="hospitals-empty-text">
              No providers found near this zip code. Try a nearby zip code or broaden your search.
            </p>
          </div>
        )
      }
    

  const top        = hospitals[0]
  const rest       = hospitals.slice(1)

  return (
    <div className="hospital-cards">

      <div className="cards-header">
        <h3 className="cards-title">Nearby Providers</h3>
        <span className="cards-count">{hospitals.length} found</span>
      </div>

      {/* Top recommendation */}
      <div className="hospital-card hospital-card--top">
        <div className="card-top-label">Top Recommendation</div>
        <div className="card-body">
          <div className="card-info">
            <p className="card-name">{top.hospital}</p>
            <p className="card-address">{top.address}</p>
            <NetworkBadge status={top.network_status} />
          </div>
          <div className="card-right">
            <p className="card-cost">
              ${top.estimated_cost?.toLocaleString()}
            </p>
            {top.phone && top.phone !== "N/A" && (
              <a
                href={"tel:" + top.phone}
                className="card-call-btn"
              >
                Call
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Remaining hospitals */}
      {rest.map((hospital, i) => (
        <div key={i} className="hospital-card">
          <div className="card-body">
            <div className="card-info">
              <p className="card-name">{hospital.hospital}</p>
              <p className="card-address">{hospital.address}</p>
              <NetworkBadge status={hospital.network_status} />
            </div>
            <div className="card-right">
              <p className="card-cost">
                ${hospital.estimated_cost?.toLocaleString()}
              </p>
              {hospital.phone && hospital.phone !== "N/A" && (
                <a
                  href={`tel:${hospital.phone}`}
                  className="card-call-btn card-call-btn--secondary"
                >
                  Call
                </a>
              )}
            </div>
          </div>
        </div>
      ))}

    </div>
  )
}