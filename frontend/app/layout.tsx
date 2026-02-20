// app/layout.tsx
// Root layout — wraps every page in ClearCare.
// Sets fonts, metadata, and global HTML structure.
// This file runs on every single page automatically.

import type { Metadata } from "next"
import { Inter, Syne } from "next/font/google"
import "./globals.css"

// Inter — clean readable body font
// Used for all body text, labels, descriptions
// subsets: ["latin"] keeps the bundle small
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
})

// Syne — distinctive display font
// Used for the logo, cost numbers, and headlines
// Gives ClearCare a modern medical-tech feel
const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  display: "swap",
})



// Metadata appears in browser tab and search results
// og: fields are for social sharing previews
export const metadata: Metadata = {
  title: "ClearCare — Know What You'll Pay",
  description:
    "AI Medicare cost navigator. Find in-network hospitals, estimate your out-of-pocket costs, and discover cheaper alternatives before you schedule care.",
  icons: {
      icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%2300A693'/><text x='50%25' y='50%25' dominant-baseline='central' text-anchor='middle' font-family='system-ui' font-weight='700' font-size='18' fill='white'>C</text></svg>",
    },
  keywords: "Medicare cost estimator, insurance, hospital finder, out of pocket cost",
  authors: [{ name: "Koushik Vasa" }],
  openGraph: {
    title: "ClearCare — Know What You'll Pay Before You Go",
    description: "AI Medicare cost navigator",
    type: "website",
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${inter.variable} ${syne.variable}`}>
      {/*
        suppressHydrationWarning prevents a React warning caused by
        browser extensions that modify the DOM before React hydrates.
        Common with password managers and ad blockers.
      */}
      <body suppressHydrationWarning>
        {children}
      </body>
    </html>
  )
}