/**
 * Next.js Route Handler: POST /api/dismiss-all
 *
 * Proxies the dismiss-all request to the backend API, then redirects back to
 * the alerts page. Used by the native <form action="/api/dismiss-all"> on the
 * alerts page so no client-side JavaScript is required.
 */
import { NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  try {
    await fetch(`${API_BASE}/alerts/dismiss-all`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    // Best-effort — redirect regardless so the user isn't stuck
  }
  return NextResponse.redirect(new URL("/alerts", request.url));
}
