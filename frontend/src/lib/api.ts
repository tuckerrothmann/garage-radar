/**
 * Garage Radar API client.
 * All functions are async and throw on non-2xx responses.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface Listing {
  id: string;
  source: string;
  source_url: string;
  listing_status: string;
  make: string | null;
  model: string | null;
  year: number;
  generation: string | null;
  body_style: string | null;
  transmission: string | null;
  exterior_color_canonical: string | null;
  exterior_color_raw: string | null;
  mileage: number | null;
  asking_price: number | null;
  currency: string;
  title_raw: string | null;
  location: string | null;
  matching_numbers: boolean | null;
  original_paint: boolean | null;
  service_history: boolean | null;
  modification_flags: string[] | null;
  normalization_confidence: number | null;
  created_at: string;
  updated_at: string;
  cluster_median: number | null;
  delta_pct: number | null;
}

export interface PriceHistoryEntry {
  price: number;
  ts: string;
}

export interface ListingDetail extends Listing {
  drivetrain: string;
  trim: string | null;
  engine_variant: string | null;
  interior_color_raw: string | null;
  vin: string | null;
  title_status: string;
  final_price: number | null;
  listing_date: string | null;
  seller_type: string | null;
  seller_name: string | null;
  bidder_count: number | null;
  price_history: PriceHistoryEntry[] | null;
  alerts: Alert[];
}

export interface ListingPage {
  total: number;
  limit: number;
  offset: number;
  items: Listing[];
}

export interface Alert {
  id: string;
  alert_type: string;
  triggered_at: string;
  listing_id: string | null;
  reason: string;
  delta_pct: number | null;
  severity: string;
  status: string;
}

export interface AlertPage {
  total: number;
  limit: number;
  offset: number;
  items: Alert[];
}

export interface CompCluster {
  id: number;
  cluster_key: string;
  make: string;
  model: string;
  body_style: string;
  transmission: string;
  window_days: number;
  comp_count: number;
  median_price: number | null;
  p25_price: number | null;
  p75_price: number | null;
  min_price: number | null;
  max_price: number | null;
  insufficient_data: boolean;
  last_computed_at: string;
}

// ── Listings ─────────────────────────────────────────────────────────────────

export interface ListingFilters {
  make?: string;
  model?: string;
  generation?: string;
  body_style?: string;
  transmission?: string;
  status?: string;
  source?: string;
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  confidence_min?: number;
  limit?: number;
  offset?: number;
}

export async function getListings(filters: ListingFilters = {}): Promise<ListingPage> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== "") params.set(k, String(v));
  }
  return apiFetch<ListingPage>(`/listings?${params}`);
}

export async function getListing(id: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/listings/${id}`);
}

// ── Alerts ───────────────────────────────────────────────────────────────────

export async function getAlerts(
  status = "open",
  limit = 50,
  offset = 0,
): Promise<AlertPage> {
  return apiFetch<AlertPage>(
    `/alerts?status=${status}&limit=${limit}&offset=${offset}`,
  );
}

export async function patchAlertStatus(
  id: string,
  newStatus: "read" | "dismissed",
): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status: newStatus }),
  });
}

export async function dismissAllAlerts(): Promise<{ dismissed: number }> {
  return apiFetch<{ dismissed: number }>("/alerts/dismiss-all", {
    method: "POST",
  });
}

// ── Comp clusters ────────────────────────────────────────────────────────────

export async function getCompClusters(filters: {
  make?: string;
  model?: string;
  body_style?: string;
  transmission?: string;
} = {}): Promise<CompCluster[]> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v) params.set(k, v);
  }
  return apiFetch<CompCluster[]>(`/comps/clusters?${params}`);
}
