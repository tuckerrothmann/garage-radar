import { NextResponse } from "next/server";

const BASE =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

export async function POST(request: Request) {
  const fallbackUrl = new URL("/alerts?status=open", request.url);

  const response = await fetch(`${BASE}/alerts/dismiss-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await response.text().catch(() => "");
    return NextResponse.json(
      {
        error: "Failed to dismiss alerts",
        detail: message || response.statusText,
      },
      { status: response.status },
    );
  }

  const referer = request.headers.get("referer");
  const redirectTarget = referer ? new URL(referer) : fallbackUrl;
  return NextResponse.redirect(redirectTarget, { status: 303 });
}
