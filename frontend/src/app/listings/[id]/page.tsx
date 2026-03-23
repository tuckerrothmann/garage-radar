/**
 * Listing detail page — server component.
 * Route: /listings/[id]
 */
import { getListing, type ListingDetail } from "@/lib/api";
import DeltaBadge from "@/components/DeltaBadge";
import SeverityBadge from "@/components/SeverityBadge";
import PriceHistoryChart from "@/components/PriceHistoryChart";

interface PageProps {
  params: { id: string };
}

function fmt(n: number | null, currency = "USD") {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

function sourceBadgeLabel(source: string) {
  const labels: Record<string, string> = {
    bat: "BaT",
    carsandbids: "Cars & Bids",
    ebay: "eBay",
    pcarmarket: "PCA Market",
  };
  return labels[source] ?? source;
}

function statusBadgeClass(status: string) {
  switch (status) {
    case "active":
      return "bg-green-900 text-green-300 border border-green-700";
    case "sold":
      return "bg-red-900 text-red-300 border border-red-700";
    case "ended":
      return "bg-gray-700 text-gray-300 border border-gray-600";
    default:
      return "bg-gray-700 text-gray-300 border border-gray-600";
  }
}

interface SpecRowProps {
  label: string;
  value: string | number | null | undefined;
}

function SpecRow({ label, value }: SpecRowProps) {
  if (value == null || value === "") return null;
  return (
    <div className="flex gap-4 py-2 border-b border-radar-border last:border-0">
      <dt className="text-radar-muted text-sm w-40 shrink-0">{label}</dt>
      <dd className="text-sm text-white">{value}</dd>
    </div>
  );
}

export default async function ListingDetailPage({ params }: PageProps) {
  let listing: ListingDetail | null = null;
  let error: string | null = null;

  try {
    listing = await getListing(params.id);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load listing";
  }

  if (error || !listing) {
    return (
      <div className="space-y-4">
        <a href="/" className="text-radar-muted hover:text-white text-sm">
          ← All listings
        </a>
        <div className="bg-radar-card border border-radar-border rounded-lg p-8 text-center space-y-2">
          <p className="text-xl font-semibold text-white">Listing not found</p>
          <p className="text-radar-muted text-sm">{error ?? "The listing you requested does not exist."}</p>
          <a href="/" className="inline-block mt-4 text-sm text-radar-red hover:underline">
            ← Back to all listings
          </a>
        </div>
      </div>
    );
  }

  const activeAlerts = listing.alerts.filter((a) => a.status !== "dismissed");

  return (
    <div className="space-y-6">
      {/* Back link */}
      <a href="/" className="text-radar-muted hover:text-white text-sm inline-flex items-center gap-1">
        ← All listings
      </a>

      {/* Header row */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-white leading-tight">
            {listing.year} {listing.title_raw ? listing.title_raw : "Porsche 911"}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase ${statusBadgeClass(listing.listing_status)}`}>
            {listing.listing_status}
          </span>
          <a
            href={listing.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-radar-card border border-radar-border text-radar-muted hover:text-white transition-colors"
          >
            {sourceBadgeLabel(listing.source)} ↗
          </a>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex flex-col lg:flex-row gap-6 items-start">

        {/* LEFT: Specs */}
        <div className="flex-1 min-w-0 space-y-6">
          <div className="bg-radar-card border border-radar-border rounded-lg p-4">
            <h2 className="text-sm font-semibold text-radar-muted uppercase tracking-wide mb-3">Specifications</h2>
            <dl>
              <SpecRow label="Generation" value={listing.generation} />
              <SpecRow label="Body Style" value={listing.body_style} />
              <SpecRow label="Trim" value={listing.trim} />
              <SpecRow label="Drivetrain" value={listing.drivetrain} />
              <SpecRow label="Transmission" value={listing.transmission} />
              <SpecRow label="Engine" value={listing.engine_variant} />
              <SpecRow label="Exterior Color" value={listing.exterior_color_raw} />
              <SpecRow label="Interior Color" value={listing.interior_color_raw} />
              <SpecRow
                label="Mileage"
                value={listing.mileage != null ? listing.mileage.toLocaleString() + " mi" : null}
              />
              <SpecRow label="VIN" value={listing.vin} />
              <SpecRow label="Seller Type" value={listing.seller_type} />
              <SpecRow label="Seller" value={listing.seller_name} />
              <SpecRow label="Location" value={listing.location} />
            </dl>
          </div>

          {/* Flags */}
          {(listing.matching_numbers || listing.original_paint || listing.service_history ||
            (listing.modification_flags && listing.modification_flags.length > 0)) && (
            <div className="bg-radar-card border border-radar-border rounded-lg p-4">
              <h2 className="text-sm font-semibold text-radar-muted uppercase tracking-wide mb-3">Flags</h2>
              <div className="flex flex-wrap gap-2">
                {listing.matching_numbers && (
                  <span className="text-xs px-2 py-1 rounded bg-blue-900 text-blue-300 border border-blue-700">
                    Matching Numbers
                  </span>
                )}
                {listing.original_paint && (
                  <span className="text-xs px-2 py-1 rounded bg-purple-900 text-purple-300 border border-purple-700">
                    Original Paint
                  </span>
                )}
                {listing.service_history && (
                  <span className="text-xs px-2 py-1 rounded bg-teal-900 text-teal-300 border border-teal-700">
                    Service History
                  </span>
                )}
                {listing.modification_flags?.map((flag) => (
                  <span key={flag} className="text-xs px-2 py-1 rounded bg-orange-900 text-orange-300 border border-orange-700">
                    {flag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Confidence */}
          {listing.normalization_confidence != null && (
            <p className="text-xs text-radar-muted">
              Confidence: {(listing.normalization_confidence * 100).toFixed(0)}%
            </p>
          )}
        </div>

        {/* RIGHT: Price card + chart + alerts */}
        <div className="lg:w-80 w-full shrink-0 space-y-4 lg:sticky lg:top-6">
          {/* Price card */}
          <div className="bg-radar-card border border-radar-border rounded-lg p-4 space-y-3">
            <h2 className="text-sm font-semibold text-radar-muted uppercase tracking-wide">Price</h2>
            <p className="text-3xl font-bold text-white tabular-nums">
              {fmt(listing.asking_price, listing.currency)}
            </p>
            <DeltaBadge delta={listing.delta_pct} />
            {listing.cluster_median != null && (
              <p className="text-xs text-radar-muted">
                Cluster median:{" "}
                <span className="text-white">{fmt(listing.cluster_median, listing.currency)}</span>
              </p>
            )}

            {/* Price history sparkline */}
            <div className="pt-2 border-t border-radar-border">
              <p className="text-xs text-radar-muted mb-2">Price history</p>
              <PriceHistoryChart
                priceHistory={listing.price_history ?? []}
                currentPrice={listing.asking_price}
                updatedAt={listing.updated_at}
              />
            </div>
          </div>

          {/* Alerts */}
          {activeAlerts.length > 0 && (
            <div className="bg-radar-card border border-radar-border rounded-lg p-4 space-y-3">
              <h2 className="text-sm font-semibold text-radar-muted uppercase tracking-wide">Alerts</h2>
              <ul className="space-y-2">
                {activeAlerts.map((alert) => (
                  <li key={alert.id} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={alert.severity} />
                      <span className="text-xs text-radar-muted uppercase tracking-wide">
                        {alert.alert_type.replace(/_/g, " ")}
                      </span>
                    </div>
                    <p className="text-xs text-white">{alert.reason}</p>
                    {alert.delta_pct != null && (
                      <p className="text-xs text-radar-muted">
                        Δ {alert.delta_pct > 0 ? "+" : ""}{alert.delta_pct.toFixed(1)}%
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
