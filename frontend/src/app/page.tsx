/**
 * Listings dashboard.
 */
import Link from "next/link";

import DeltaBadge from "@/components/DeltaBadge";
import ListingFiltersForm from "@/components/ListingFiltersForm";
import { getListings, type ListingFilters } from "@/lib/api";
import {
  allValues,
  buildSearchParams,
  parseNumberValue,
  parseNumberValues,
  type SearchParams,
} from "@/lib/search-params";

const GENERATIONS = ["G1", "G2", "G3", "G4", "G5", "G6"];
const BODY_STYLES = [
  "coupe",
  "sedan",
  "wagon",
  "hatchback",
  "suv",
  "truck",
  "van",
  "targa",
  "cabriolet",
  "speedster",
];
const TRANSMISSIONS = ["manual", "manual-6sp", "auto"];
const SOURCES = ["bat", "carsandbids", "ebay", "pcarmarket"];

interface PageProps {
  searchParams: SearchParams;
}

type DashboardListing = Awaited<ReturnType<typeof getListings>>["items"][number];

function fmt(n: number | null, currency = "USD") {
  if (n == null) return "-";
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

function primaryPrice(listing: DashboardListing) {
  if (listing.current_bid != null) {
    return {
      label: "Current bid",
      value: fmt(listing.current_bid, listing.currency),
    };
  }
  if (listing.asking_price != null) {
    return {
      label: "Asking",
      value: fmt(listing.asking_price, listing.currency),
    };
  }
  if (listing.final_price != null) {
    return {
      label: "Final",
      value: fmt(listing.final_price, listing.currency),
    };
  }
  return { label: "Price", value: "-" };
}

function formatAuctionState(listing: DashboardListing) {
  if (listing.time_remaining_text) return listing.time_remaining_text;
  if (!listing.auction_end_at) return "-";
  const end = parseAuctionDate(listing.auction_end_at);
  if (Number.isNaN(end.getTime())) return listing.auction_end_at;
  const hasTime = listing.auction_end_at.includes("T");
  return end.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: hasTime ? "numeric" : undefined,
    minute: hasTime ? "2-digit" : undefined,
  });
}

function auctionDetail(listing: DashboardListing) {
  if (!listing.auction_end_at) return null;
  const end = parseAuctionDate(listing.auction_end_at);
  if (Number.isNaN(end.getTime())) return `Ends ${listing.auction_end_at}`;
  const prefix = listing.time_remaining_text ? "Ends" : "Auction end";
  return `${prefix} ${end.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })}`;
}

function parseAuctionDate(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T00:00:00`);
  }
  return new Date(value);
}

function displayTitle(listing: DashboardListing) {
  if (listing.title_raw) return listing.title_raw;
  const pieces = [listing.year, listing.make, listing.model].filter(Boolean);
  return pieces.join(" ") || "Unknown vehicle";
}

export default async function ListingsPage({ searchParams }: PageProps) {
  const limit = 50;
  const offset = parseNumberValue(searchParams.offset) ?? 0;

  const filters: ListingFilters = {
    status: allValues(searchParams.status).length > 0 ? allValues(searchParams.status) : ["active"],
    make: allValues(searchParams.make),
    model: allValues(searchParams.model),
    generation: allValues(searchParams.generation),
    body_style: allValues(searchParams.body_style),
    transmission: allValues(searchParams.transmission),
    source: allValues(searchParams.source),
    year: parseNumberValues(searchParams.year),
    year_min: parseNumberValue(searchParams.year_min),
    year_max: parseNumberValue(searchParams.year_max),
    price_min: parseNumberValue(searchParams.price_min),
    price_max: parseNumberValue(searchParams.price_max),
    limit,
    offset,
  };

  let page: Awaited<ReturnType<typeof getListings>> | null = null;
  let error: string | null = null;
  try {
    page = await getListings(filters);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load listings";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Active Listings</h1>
        {page && (
          <span className="text-sm text-radar-muted">
            {page.total.toLocaleString()} listings
          </span>
        )}
      </div>

      <ListingFiltersForm
        current={searchParams}
        generations={GENERATIONS}
        bodyStyles={BODY_STYLES}
        transmissions={TRANSMISSIONS}
        sources={SOURCES}
      />

      {error && (
        <div className="rounded-lg border border-red-700 bg-red-950 p-4 text-red-300">
          {error}
        </div>
      )}

      {page && (
        <>
          <div className="overflow-x-auto rounded-lg border border-radar-border">
            <table className="w-full text-sm">
              <thead className="bg-radar-card text-xs uppercase tracking-wide text-radar-muted">
                <tr>
                  {["Year", "Details", "Source", "Mileage", "Price", "Auction", "vs Median", "Flags", ""].map((header) => (
                    <th key={header} className="whitespace-nowrap px-4 py-3 text-left">
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-radar-border">
                {page.items.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-radar-muted">
                      No listings found.
                    </td>
                  </tr>
                )}
                {page.items.map((listing) => (
                  <tr key={listing.id} className="transition-colors hover:bg-radar-card/50">
                    <td className="px-4 py-3 font-mono font-semibold">{listing.year}</td>
                    <td className="max-w-xs px-4 py-3">
                      <Link
                        href={`/listings/${listing.id}`}
                        className="block truncate font-medium hover:text-radar-red"
                        title={displayTitle(listing)}
                      >
                        {displayTitle(listing)}
                      </Link>
                      <div className="mt-0.5 text-xs text-radar-muted">
                        {[listing.make, listing.model, listing.generation, listing.body_style, listing.transmission]
                          .filter(Boolean)
                          .join(" | ")}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-radar-muted">
                      {sourceBadge(listing.source)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {listing.mileage != null ? listing.mileage.toLocaleString() : "-"}
                    </td>
                    <td className="px-4 py-3 text-right font-medium tabular-nums">
                      <div>{primaryPrice(listing).value}</div>
                      <div className="mt-0.5 text-xs text-radar-muted">{primaryPrice(listing).label}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div>{formatAuctionState(listing)}</div>
                      {auctionDetail(listing) && (
                        <div className="mt-0.5 text-xs text-radar-muted">{auctionDetail(listing)}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <DeltaBadge delta={listing.delta_pct} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {listing.matching_numbers && (
                          <span className="rounded bg-blue-900 px-1.5 py-0.5 text-xs text-blue-300">MN</span>
                        )}
                        {listing.original_paint && (
                          <span className="rounded bg-emerald-900 px-1.5 py-0.5 text-xs text-emerald-300">
                            OP
                          </span>
                        )}
                        {listing.service_history && (
                          <span className="rounded bg-teal-900 px-1.5 py-0.5 text-xs text-teal-300">SH</span>
                        )}
                        {listing.modification_flags && listing.modification_flags.length > 0 && (
                          <span className="rounded bg-orange-900 px-1.5 py-0.5 text-xs text-orange-300">
                            MOD
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap">
                      <div className="flex gap-3">
                        <Link href={`/listings/${listing.id}`} className="text-radar-red hover:underline">
                          More info
                        </Link>
                        <a
                          href={listing.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-radar-muted hover:text-white"
                        >
                          Source
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
  searchParams: SearchParams;
}) {
  if (total <= limit) return null;

  const prevOffset = Math.max(0, offset - limit);
  const nextOffset = offset + limit;
  const canPrev = offset > 0;
  const canNext = nextOffset < total;

  const makeHref = (next: number) => {
    const params = buildSearchParams(searchParams);
    params.set("offset", String(next));
    return `?${params.toString()}`;
  };

  return (
    <div className="flex items-center justify-between text-sm text-radar-muted">
      <span>
        {offset + 1}-{Math.min(offset + limit, total)} of {total.toLocaleString()}
      </span>
      <div className="flex gap-2">
        <a
          href={canPrev ? makeHref(prevOffset) : undefined}
          className={
            canPrev
              ? "rounded border border-radar-border px-3 py-1.5 text-white hover:bg-radar-card"
              : "cursor-not-allowed rounded border border-radar-border px-3 py-1.5 opacity-40"
          }
        >
          {"<-"} Prev
        </a>
        <a
          href={canNext ? makeHref(nextOffset) : undefined}
          className={
            canNext
              ? "rounded border border-radar-border px-3 py-1.5 text-white hover:bg-radar-card"
              : "cursor-not-allowed rounded border border-radar-border px-3 py-1.5 opacity-40"
          }
        >
          Next {"->"}
        </a>
      </div>
    </div>
  );
}
