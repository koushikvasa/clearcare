// components/HospitalMap.tsx
// Google Maps component showing hospital pins.
// Green = in-network, Red = out-of-network, Grey = unknown.
// Loads Maps via script tag injection.

"use client"

import { useEffect, useRef, useState } from "react"
import { Hospital } from "../page"

interface HospitalMapProps {
  hospitals: Hospital[]
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

export default function HospitalMap({ hospitals }: HospitalMapProps) {

  const mapRef        = useRef<HTMLDivElement>(null)
  const mapInstance   = useRef<any>(null)
  const markersRef    = useRef<any[]>([])
  const infoWindowRef = useRef<any>(null)

  const [isReady, setIsReady] = useState(false)
  const [mapError, setMapError] = useState("")

  // Load Google Maps script once
  useEffect(() => {
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || ""
    if (!apiKey) {
      setMapError("Google Maps API key not configured")
      return
    }

    // If already loaded
    if (window.google && window.google.maps) {
      setIsReady(true)
      return
    }

    // If script already injected but not ready yet
    if (document.getElementById("google-maps-script")) {
      window.initClearCareMap = () => setIsReady(true)
      return
    }

    // Inject the script tag
    window.initClearCareMap = () => setIsReady(true)

    const script = document.createElement("script")
    script.id    = "google-maps-script"
    script.src   = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&callback=initClearCareMap`
    script.async = true
    script.defer = true
    script.onerror = () => setMapError("Failed to load Google Maps")

    document.head.appendChild(script)

    return () => {
      // Do not remove script on unmount — keep it cached
    }
  }, [])

  // Initialize map once script is ready
  useEffect(() => {
    if (!isReady || !mapRef.current || mapInstance.current) return

    mapInstance.current = new window.google.maps.Map(mapRef.current, {
      center:            { lat: 40.6892, lng: -74.0445 },
      zoom:              13,
      mapTypeControl:    false,
      fullscreenControl: false,
      streetViewControl: false,
      styles: [
        {
          featureType: "poi",
          elementType: "labels",
          stylers:     [{ visibility: "off" }]
        },
        {
          featureType: "transit",
          elementType: "labels",
          stylers:     [{ visibility: "off" }]
        },
      ]
    })

    infoWindowRef.current = new window.google.maps.InfoWindow()

  }, [isReady])

  // Add markers when hospitals change
  useEffect(() => {
    if (!isReady || !mapInstance.current || !hospitals.length) return

    // Clear old markers
    markersRef.current.forEach(m => m.setMap(null))
    markersRef.current = []

    const geocoder = new window.google.maps.Geocoder()
    const bounds   = new window.google.maps.LatLngBounds()

    hospitals.forEach(hospital => {
      geocoder.geocode(
        { address: hospital.address },
        (results: any, status: string) => {
          if (status !== "OK" || !results?.[0]) return

          const position = results[0].geometry.location
          bounds.extend(position)

          const color = PIN_COLORS[hospital.network_status] || PIN_COLORS.unknown

          const pinSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="40" viewBox="0 0 32 40"><path d="M16 0C7.163 0 0 7.163 0 16c0 10 16 24 16 24s16-14 16-24C32 7.163 24.837 0 16 0z" fill="${color}"/><circle cx="16" cy="16" r="6" fill="white"/></svg>`

          const marker = new window.google.maps.Marker({
            position,
            map:   mapInstance.current,
            title: hospital.hospital,
            icon: {
              url:        "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(pinSvg),
              scaledSize: new window.google.maps.Size(32, 40),
              anchor:     new window.google.maps.Point(16, 40),
            }
          })

          const networkLabel =
            hospital.network_status === "in-network"       ? "In Network" :
            hospital.network_status === "accepts-medicare" ? "Accepts Medicare" :
            hospital.network_status === "out-of-network"   ? "Out of Network" :
            "Network Unknown"

          const infoContent = `
            <div class="map-popup">
              <p class="popup-name">${hospital.hospital}</p>
              <p class="popup-address">${hospital.address}</p>
              <div class="popup-bottom">
                <span class="popup-badge popup-badge--${hospital.network_status === "in-network" || hospital.network_status === "accepts-medicare" ? "green" : "red"}">${networkLabel}</span>
                <span class="popup-cost">$${hospital.estimated_cost?.toLocaleString()}</span>
              </div>
              ${hospital.phone !== "N/A" ? `<a href="tel:${hospital.phone}" class="popup-phone">${hospital.phone}</a>` : ""}
            </div>
          `

          marker.addListener("click", () => {
            infoWindowRef.current?.setContent(infoContent)
            infoWindowRef.current?.open(mapInstance.current, marker)
          })

          markersRef.current.push(marker)

          if (markersRef.current.length === hospitals.length) {
            mapInstance.current?.fitBounds(bounds)
          }
        }
      )
    })

  }, [isReady, hospitals])


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