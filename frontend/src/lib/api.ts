/**
 * Garage Radar API client.
 */

const SERVER_BASE =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";
const CLIENT_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type QueryValue = string | number | Array<string | number> | undefined;

function apiBase(): string {
  return typeof window === "undefined" ? SERVER_BASE : CLIENT_BASE;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

function toQueryString<T extends object>(filters: T): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters as Record<string, QueryValue>)) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== "") params.append(key, String(item));
      }
      continue;
    }
    params.set(key, String(value));
  }
  return params.toString();
}

export interface Listing {
  id: string;
  source: string;
  source_url: string;
  listing_status: string;
  year: number;
  make: string | null;
  model: string | null;
  generation: string | null;
  body_style: string | null;
  trim: string | null;
  drivetrain: string;
  transmission: string | null;
  engine_variant: string | null;
  exterior_color_canonical: string | null;
  exterior_color_raw: string | null;
  interior_color_raw: string | null;
  mileage: number | null;
  vin: string | null;
  title_status: string;
  current_bid: number | null;
  asking_price: number | null;
  currency: string;
  final_price: number | null;
  matching_numbers: boolean | null;
  original_paint: boolean | null;
  service_history: boolean | null;
  modification_flags: string[] | null;
  normalization_confidence: number | null;
  listing_date: string | null;
  auction_end_at: string | null;
  time_remaining_text: string | null;
  seller_type: string | null;
  seller_name: string | null;
  location: string | null;
  bidder_count: number | null;
  title_raw: string | null;
  created_at: string;
  updated_at: string;
  cluster_median: number | null;
  cluster_comp_count: number | null;
  cluster_p25: number | null;
  cluster_p75: number | null;
  cluster_min: number | null;
  cluster_max: number | null;
  cluster_window_days: number | null;
  delta_pct: number | null;
}

export interface ListingDetail extends Listing {
  price_history: Array<Record<string, unknown>> | null;
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
  make: string | null;
  model: string | null;
  generation: string | null;
  year_bucket: number | null;
  body_style: string;
  transmission: string;
  currency: string;
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

export interface VehicleProfileStats {
  listing_count: number;
  comp_count: number;
  primary_currency: string | null;
  currencies: string[];
  year_min: number | null;
  year_max: number | null;
  avg_asking_price: number | null;
  min_asking_price: number | null;
  max_asking_price: number | null;
  avg_sale_price: number | null;
  min_sale_price: number | null;
  max_sale_price: number | null;
  latest_listing_at: string | null;
  latest_sale_date: string | null;
  sources: string[];
}

export interface VehicleProfileReference {
  name: string;
  url: string;
  license: string | null;
}

export interface VehicleProfileSection {
  title: string;
  summary: string;
  source_name: string;
  source_url: string | null;
}

export interface VehicleProfileCount {
  label: string;
  count: number;
}

export interface VehicleProfileRecentListing {
  id: string;
  title: string;
  source: string;
  source_url: string;
  year: number;
  price: number | null;
  currency: string | null;
  listing_status: string;
  location: string | null;
}

export interface VehicleProfileRecentSale {
  id: string;
  title: string;
  source: string;
  source_url: string;
  year: number;
  sale_price: number | null;
  currency: string | null;
  sale_date: string | null;
}

export interface VehicleProfile {
  make: string;
  model: string;
  year: number | null;
  slug: string;
  display_name: string;
  profile_source: string;
  overview: string;
  canonical_url: string | null;
  hero_image_url: string | null;
  production_years: string | null;
  body_styles: string[];
  transmissions: string[];
  notable_trims: string[];
  encyclopedia_facts: Record<string, string>;
  market_facts: Record<string, string>;
  quick_facts: Record<string, string>;
  highlights: string[];
  common_questions: string[];
  buying_tips: string[];
  market_summary: string;
  market_signals: string[];
  recent_sales_scope: string | null;
  reference_links: VehicleProfileReference[];
  external_sections: VehicleProfileSection[];
  local_observations: string[];
  source_breakdown: VehicleProfileCount[];
  related_model_breakdown: VehicleProfileCount[];
  year_breakdown: VehicleProfileCount[];
  body_style_breakdown: VehicleProfileCount[];
  transmission_breakdown: VehicleProfileCount[];
  trim_breakdown: VehicleProfileCount[];
  recent_listings: VehicleProfileRecentListing[];
  recent_sales: VehicleProfileRecentSale[];
  coverage_gaps: string[];
  stats: VehicleProfileStats;
}

export interface ListingFilters {
  make?: string[];
  model?: string[];
  generation?: string[];
  body_style?: string[];
  transmission?: string[];
  status?: string[];
  source?: string[];
  year?: number[];
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  limit?: number;
  offset?: number;
}

export async function getListings(filters: ListingFilters = {}): Promise<ListingPage> {
  return apiFetch<ListingPage>(`/listings?${toQueryString(filters)}`);
}

export async function getListing(id: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/listings/${id}`);
}

export async function getAlerts(
  status = "open",
  limit = 50,
  offset = 0,
): Promise<AlertPage> {
  return apiFetch<AlertPage>(`/alerts?status=${status}&limit=${limit}&offset=${offset}`);
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

export async function getCompClusters(filters: {
  make?: string[];
  model?: string[];
  generation?: string[];
  year_bucket?: number[];
  body_style?: string[];
  transmission?: string[];
} = {}): Promise<CompCluster[]> {
  return apiFetch<CompCluster[]>(`/comps/clusters?${toQueryString(filters)}`);
}

export async function getVehicleProfile(filters: {
  make: string;
  model: string;
  year?: number;
  currency?: string;
}): Promise<VehicleProfile> {
  return apiFetch<VehicleProfile>(`/vehicles/profile?${toQueryString(filters)}`);
}
