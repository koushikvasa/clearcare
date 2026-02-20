// components/HospitalMap.tsx
"use client"

import { useEffect, useRef, useState } from "react"
import { Hospital } from "../page"

interface HospitalMapProps {
  hospitals: Hospital[]
  zipCode:   string
}

const PIN_COLORS: Record<string, string> = {
  "in-network":       "#00A693",
  "out-of-network":   "#E53E3E",
  "accepts-medicare": "#00A693",
  "unknown":          "#9AAAB8",
}

declare global {
  interface Window {
    google: any
    initClearCareMap: () => void
  }
}

export default function HospitalMap({ hospitals, zipCode }: HospitalMapProps) {

  const mapRef        = useRef<HTMLDivElement>(null)
  const mapInstance   = useRef<any>(null)
  const markersRef    = useRef<any[]>([])
  const infoWindowRef = useRef<any>(null)

  const [isReady,  setIsReady]  = useState(false)
  const [mapError, setMapError] = useState("")

  // ── Step 1: Load Google Maps script ──────────────────
  useEffect(() => {
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || ""

    if (!apiKey) {
      setMapError("Google Maps API key not configured")
      return
    }

    // Already loaded
    if (window.google?.maps) {
      setIsReady(true)
      return
    }

    // Script injected but callback not yet fired
    if (document.getElementById("google-maps-script")) {
      window.initClearCareMap = () => setIsReady(true)
      return
    }

    // First load — inject script
    window.initClearCareMap = () => setIsReady(true)

    const script    = document.createElement("script")
    script.id       = "google-maps-script"
    script.src      = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&callback=initClearCareMap`
    script.async    = true
    script.defer    = true
    script.onerror  = () => setMapError("Failed to load Google Maps")
    document.head.appendChild(script)
  }, [])

  // ── Step 2: Init map instance once script ready ───────
  useEffect(() => {
    if (!isReady || !mapRef.current || mapInstance.current) return
    if (!window.google?.maps) return

    mapInstance.current = new window.google.maps.Map(mapRef.current, {
      center:            { lat: 40.7128, lng: -74.0060 },
      zoom:              12,
      mapTypeControl:    false,
      fullscreenControl: false,
      streetViewControl: false,
      styles: [
        {
          featureType: "poi",
          elementType: "labels",
          stylers:     [{ visibility: "off" }],
        },
        {
          featureType: "transit",
          elementType: "labels",
          stylers:     [{ visibility: "off" }],
        },
      ],
    })

    infoWindowRef.current = new window.google.maps.InfoWindow()
  }, [isReady])

  // ── Step 3: Place markers when hospitals change ───────
  useEffect(() => {
    if (!isReady || !mapInstance.current || !window.google?.maps) return

    // Clear existing markers
    markersRef.current.forEach(m => m.setMap(null))
    markersRef.current = []

    const geocoder = new window.google.maps.Geocoder()

    // No hospitals — just center on zip code
    if (!hospitals || hospitals.length === 0) {
      geocoder.geocode(
        { address: zipCode },
        (results: any, status: string) => {
          if (status === "OK" && results?.[0]) {
            mapInstance.current.setCenter(results[0].geometry.location)
            mapInstance.current.setZoom(13)
          }
        }
      )
      return
    }

    // Place a marker for each hospital
    const bounds = new window.google.maps.LatLngBounds()
    let resolved = 0

    hospitals.forEach(hospital => {
      // Use address for geocoding — fall back to zip if address is bad
      const query = hospital.address && hospital.address.length > 5
        ? hospital.address
        : zipCode

      geocoder.geocode(
        { address: query },
        (results: any, status: string) => {
          resolved++

          if (status === "OK" && results?.[0]) {
            const position = results[0].geometry.location
            bounds.extend(position)

            const color  = PIN_COLORS[hospital.network_status] || PIN_COLORS["unknown"]
            const pinSvg = `
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="40" viewBox="0 0 32 40">
                <path d="M16 0C7.163 0 0 7.163 0 16c0 10 16 24 16 24s16-14 16-24C32 7.163 24.837 0 16 0z" fill="${color}"/>
                <circle cx="16" cy="16" r="6" fill="white"/>
              </svg>
            `.trim()

            const marker = new window.google.maps.Marker({
              position,
              map:   mapInstance.current,
              title: hospital.hospital,
              icon: {
                url:        "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(pinSvg),
                scaledSize: new window.google.maps.Size(32, 40),
                anchor:     new window.google.maps.Point(16, 40),
              },
            })

            const networkLabel =
              hospital.network_status === "in-network"       ? "In Network" :
              hospital.network_status === "accepts-medicare" ? "Accepts Medicare" :
              hospital.network_status === "out-of-network"   ? "Out of Network" :
              "Network Unknown"

            const badgeClass =
              hospital.network_status === "in-network" ||
              hospital.network_status === "accepts-medicare"
                ? "green" : "red"

            const costText = hospital.estimated_cost && hospital.estimated_cost > 0
              ? "$" + hospital.estimated_cost.toLocaleString()
              : "Est. TBD"

            const phoneLink = hospital.phone && hospital.phone !== "N/A"
              ? `<a href="tel:${hospital.phone}" class="popup-phone">${hospital.phone}</a>`
              : ""

            const infoContent = `
              <div class="map-popup">
                <p class="popup-name">${hospital.hospital}</p>
                <p class="popup-address">${hospital.address}</p>
                <div class="popup-bottom">
                  <span class="popup-badge popup-badge--${badgeClass}">${networkLabel}</span>
                  <span class="popup-cost">${costText}</span>
                </div>
                ${phoneLink}
              </div>
            `

            marker.addListener("click", () => {
              infoWindowRef.current?.setContent(infoContent)
              infoWindowRef.current?.open(mapInstance.current, marker)
            })

            markersRef.current.push(marker)
          }

          // Fit bounds after all geocoding attempts complete
          if (resolved === hospitals.length) {
            if (markersRef.current.length > 1) {
              mapInstance.current.fitBounds(bounds)
            } else if (markersRef.current.length === 1) {
              mapInstance.current.setCenter(
                markersRef.current[0].getPosition()
              )
              mapInstance.current.setZoom(14)
            } else {
              // All geocoding failed — fall back to zip
              geocoder.geocode(
                { address: zipCode },
                (r: any, s: string) => {
                  if (s === "OK" && r?.[0]) {
                    mapInstance.current.setCenter(r[0].geometry.location)
                    mapInstance.current.setZoom(13)
                  }
                }
              )
            }
          }
        }
      )
    })
  }, [isReady, hospitals, zipCode])

  // ── Render ────────────────────────────────────────────
  if (mapError) {
    return <div className="map-error">{mapError}</div>
  }

  return (
    <div className="map-container">
      <div className="map-header">
        <h3 className="map-title">Nearby Providers</h3>
        <div className="map-legend">
          <div className="legend-item">
            <div className="legend-dot legend-dot--green" />
            <span>In Network</span>
          </div>
          <div className="legend-item">
            <div className="legend-dot legend-dot--red" />
            <span>Out of Network</span>
          </div>
          <div className="legend-item">
            <div className="legend-dot legend-dot--grey" />
            <span>Unknown</span>
          </div>
        </div>
      </div>
      <div ref={mapRef} className="map-canvas" />
    </div>
  )
}