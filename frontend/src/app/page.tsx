/**
 * Listings dashboard — server component, re-fetches on every request.
 * Filters are controlled via URL search params.
 */
import { getListings, type ListingFilters } from "@/lib/api";
import DeltaBadge from "@/components/DeltaBadge";
import ListingFiltersForm from "@/components/ListingFiltersForm";

const GENERATIONS = ["G1", "G2", "G3", "G4", "G5", "G6"];
const BODY_STYLES  = ["coupe", "targa", "cabriolet", "speedster"];
const TRANSMISSIONS = ["manual", "manual-6sp", "auto"];
const SOURCES = ["bat", "carsandbids", "ebay", "pcarmarket"];

interface PageProps {
  searchParams: Record<string, string | undefined>;
}

function fmt(n: number | null, currency = "USD") {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

function sourceBadge(source: string) {
  const labels: Record<string, string> = {
    bat: "BaT",
    carsandbids: "C&B",
    ebay: "eBay",
    pcarmarket: "PCA Mkt",
  };
  return labels[source] ?? source;
}

export default async function ListingsPage({ searchParams }: PageProps) {
  const limit = 50;
  const offset = Number(searchParams.offset ?? 0);

  const filters: ListingFilters = {
    status:       searchParams.status ?? "active",
    generation:   searchParams.generation,
    body_style:   searchParams.body_style,
    transmission: searchParams.transmission,
    source:       searchParams.source,
    year_min:     searchParams.year_min ? Number(searchParams.year_min) : undefined,
    year_max:     searchParams.year_max ? Number(searchParams.year_max) : undefined,
    price_min:    searchParams.price_min ? Number(searchParams.price_min) : undefined,
    price_max:    searchParams.price_max ? Number(searchParams.price_max) : undefined,
    limit,
    offset,
  };

  let page;
  let error: string | null = null;
  try {
    page = await getListings(filters);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load listings";
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Active Listings</h1>
        {page && (
          <span className="text-radar-muted text-sm">
            {page.total.toLocaleString()} listings
          </span>
        )}
      </div>

      {/* Filters */}
      <ListingFiltersForm
        current={searchParams}
        generations={GENERATIONS}
        bodyStyles={BODY_STYLES}
        transmissions={TRANSMISSIONS}
        sources={SOURCES}
      />

      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4 text-red-300">
          {error}
        </div>
      )}

      {/* Table */}
      {page && (
        <>
          <div className="overflow-x-auto rounded-lg border border-radar-border">
            <table className="w-full text-sm">
              <thead className="bg-radar-card text-radar-muted uppercase text-xs tracking-wide">
                <tr>
                  {["Year", "Details", "Source", "Mileage", "Asking", "vs Median", "Flags", ""].map(h => (
                    <th key={h} className="px-4 py-3 text-left whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-radar-border">
                {page.items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-radar-muted">
                      No listings found.
                    </td>
                  </tr>
                )}
                {page.items.map(listing => (
                  <tr
                    key={listing.id}
                    className="hover:bg-radar-card/50 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono font-semibold">
                      {listing.year}
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <div className="font-medium truncate" title={listing.title_raw ?? ""}>
                        {listing.title_raw ?? `${listing.year} Porsche 911`}
                      </div>
                      <div className="text-radar-muted text-xs mt-0.5">
                        {[listing.generation, listing.body_style, listing.transmission]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-radar-muted whitespace-nowrap">
                      {sourceBadge(listing.source)}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-right">
                      {listing.mileage != null
                        ? listing.mileage.toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums font-medium text-right">
                      {fmt(listing.asking_price, listing.currency)}
                    </td>
                    <td className="px-4 py-3">
                      <DeltaBadge delta={listing.delta_pct} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {listing.matching_numbers && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-blue-900 text-blue-300">MN</span>
                        )}
                        {listing.original_paint && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-purple-900 text-purple-300">OP</span>
                        )}
                        {listing.service_history && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-teal-900 text-teal-300">SH</span>
                        )}
                        {listing.modification_flags && listing.modification_flags.length > 0 && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-orange-900 text-orange-300">
                            MOD
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <a
                          href={`/listings/${listing.id}`}
                          className="text-xs text-blue-400 hover:underline whitespace-nowrap"
                        >
                          Detail
                        </a>
                        <a
                          href={listing.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-radar-red hover:underline whitespace-nowrap"
                        >
                          Source →
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <Pagination total={page.total} limit={limit} offset={offset} searchParams={searchParams} />
        </>
      )}
    </div>
  );
}

function Pagination({
  total,
  limit,
  offset,
  searchParams,
}: {
  total: number;
  limit: number;
  offset: number;
  searchParams: Record<string, string | undefined>;
}) {
  if (total <= limit) return null;

  const prevOffset = Math.max(0, offset - limit);
  const nextOffset = offset + limit;
  const canPrev = offset > 0;
  const canNext = nextOffset < total;

  const makeHref = (o: number) => {
    const p = new URLSearchParams(
      Object.fromEntries(
        Object.entries(searchParams).filter(([, v]) => v != null) as [string, string][]
      )
    );
    p.set("offset", String(o));
    return `?${p}`;
  };

  return (
    <div className="flex items-center justify-between text-sm text-radar-muted">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total.toLocaleString()}
      </span>
      <div className="flex gap-2">
        <a
          href={canPrev ? makeHref(prevOffset) : undefined}
          className={canPrev
            ? "px-3 py-1.5 rounded border border-radar-border hover:bg-radar-card text-white"
            : "px-3 py-1.5 rounded border border-radar-border opacity-40 cursor-not-allowed"}
        >
          ← Prev
        </a>
        <a
          href={canNext ? makeHref(nextOffset) : undefined}
          className={canNext
            ? "px-3 py-1.5 rounded border border-radar-border hover:bg-radar-card text-white"
            : "px-3 py-1.5 rounded border border-radar-border opacity-40 cursor-not-allowed"}
        >
          Next →
        </a>
      </div>
    </div>
  );
}
