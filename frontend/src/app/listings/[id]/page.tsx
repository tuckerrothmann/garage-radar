import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import DeltaBadge from "@/components/DeltaBadge";
import { getListing, getVehicleProfile, type ListingDetail, type VehicleProfile } from "@/lib/api";

interface PageProps {
  params: { id: string };
}

function fmtCurrency(n: number | null, currency = "USD") {
  if (n == null) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

function sourceLabel(source: string) {
  return {
    bat: "Bring a Trailer",
    carsandbids: "Cars & Bids",
    ebay: "eBay",
    pcarmarket: "PCarMarket",
  }[source] ?? source;
}

function primaryPriceFact(listing: ListingDetail) {
  if (listing.current_bid != null) {
    return {
      label: "Current bid",
      value: fmtCurrency(listing.current_bid, listing.currency),
    };
  }
  return {
    label: "Asking",
    value: fmtCurrency(listing.asking_price, listing.currency),
  };
}

export default async function ListingDetailPage({ params }: PageProps) {
  let listing: Awaited<ReturnType<typeof getListing>>;
  try {
    listing = await getListing(params.id);
  } catch (error) {
    if (error instanceof Error && error.message.includes("API 404")) {
      notFound();
    }
    throw error;
  }

  let profile: VehicleProfile | null = null;
  if (listing.make && listing.model) {
    try {
      profile = await getVehicleProfile({
        make: listing.make,
        model: listing.model,
        year: listing.year,
        currency: listing.currency,
      });
    } catch {
      profile = null;
    }
  }
  const listingSignals = buildListingSignals(listing, profile);
  const primaryPrice = primaryPriceFact(listing);

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <Link href="/" className="text-sm text-radar-muted hover:text-white">
          {"<-"} Back to listings
        </Link>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-bold">
              {listing.title_raw ?? [listing.year, listing.make, listing.model].filter(Boolean).join(" ")}
            </h1>
            <p className="mt-2 text-sm text-radar-muted">
              {[listing.make, listing.model, listing.generation, listing.body_style, listing.transmission]
                .filter(Boolean)
                .join(" | ")}
            </p>
          </div>
          <div className="flex gap-3 text-sm">
            <a
              href={listing.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-radar-border px-3 py-2 hover:bg-radar-card"
            >
              View source
            </a>
            {profile && (
              <a href="#vehicle-profile" className="rounded border border-radar-border px-3 py-2 hover:bg-radar-card">
                More info
              </a>
            )}
          </div>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1.4fr,0.9fr]">
        <div className="rounded-2xl border border-radar-border bg-radar-card/40 p-5">
          <h2 className="text-lg font-semibold">Listing Snapshot</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Fact label={primaryPrice.label} value={primaryPrice.value} />
            <Fact label="Year" value={String(listing.year)} />
            <Fact label="Mileage" value={listing.mileage != null ? listing.mileage.toLocaleString() : "-"} />
            <Fact label="Source" value={sourceLabel(listing.source)} />
            <Fact label="Location" value={listing.location ?? "-"} />
            <Fact label="Seller" value={listing.seller_name ?? listing.seller_type ?? "-"} />
            <Fact label="VIN" value={listing.vin ?? "-"} />
            <Fact label="Title" value={listing.title_status} />
            <Fact label="Bidder count" value={listing.bidder_count != null ? String(listing.bidder_count) : "-"} />
            <Fact label="Time remaining" value={displayTimeRemaining(listing)} />
            <Fact label="Auction end" value={formatAuctionEnd(listing.auction_end_at)} />
            <Fact label="Listed" value={formatSimpleDate(listing.listing_date)} />
          </div>
        </div>

        <div className="rounded-2xl border border-radar-border bg-radar-card/40 p-5">
          <h2 className="text-lg font-semibold">Market Read</h2>
          <div className="mt-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-radar-muted">Price vs comps</span>
              <DeltaBadge delta={listing.delta_pct} />
            </div>
            <Fact label="Cluster median" value={fmtCurrency(listing.cluster_median, listing.currency)} />
            <Fact
              label="Comp depth"
              value={
                listing.cluster_comp_count != null && listing.cluster_window_days != null
                  ? `${listing.cluster_comp_count} comps / ${listing.cluster_window_days}d`
                  : "-"
              }
            />
            <Fact
              label="Core price band"
              value={priceBand(listing.cluster_p25, listing.cluster_p75, listing.currency)}
            />
            <Fact
              label="Observed range"
              value={priceBand(listing.cluster_min, listing.cluster_max, listing.currency)}
            />
            <Fact label="Final price" value={fmtCurrency(listing.final_price, listing.currency)} />
            <Fact
              label="Signals"
              value={
                [
                  listing.matching_numbers ? "matching numbers" : null,
                  listing.original_paint ? "original paint" : null,
                  listing.service_history ? "service history" : null,
                  listing.modification_flags?.length ? `${listing.modification_flags.length} mod flag(s)` : null,
                ]
                  .filter(Boolean)
                  .join(", ") || "-"
              }
            />
          </div>
        </div>
      </section>

      {listingSignals.length > 0 && (
        <section className="rounded-2xl border border-radar-border bg-radar-card/40 p-5">
          <h2 className="text-lg font-semibold">This Listing in Context</h2>
          <div className="mt-4">
            <BulletList items={listingSignals} />
          </div>
        </section>
      )}

      {profile && (
        <section
          id="vehicle-profile"
          className="space-y-6 rounded-[28px] border border-radar-border bg-gradient-to-br
                     from-slate-950 via-radar-card/80 to-zinc-950 p-6"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-radar-muted">Vehicle Profile</p>
              <h2 className="mt-2 text-2xl font-semibold">{profile.display_name}</h2>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-300">{profile.overview}</p>
              {(profile.canonical_url || profile.reference_links.length > 0) && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {profile.canonical_url && (
                    <a
                      href={profile.canonical_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-full border border-radar-border px-3 py-1 text-xs uppercase tracking-wide text-gray-200 hover:bg-black/20"
                    >
                      Wikipedia
                    </a>
                  )}
                  {profile.reference_links
                    .filter((reference) => reference.url !== profile.canonical_url)
                    .map((reference) => (
                      <a
                        key={reference.url}
                        href={reference.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded-full border border-radar-border px-3 py-1 text-xs uppercase tracking-wide text-gray-200 hover:bg-black/20"
                      >
                        {reference.name}
                      </a>
                    ))}
                </div>
              )}
            </div>
            <div className="rounded-full border border-radar-border px-3 py-1 text-xs uppercase tracking-wide text-radar-muted">
              {profile.profile_source}
            </div>
          </div>

          {profile.hero_image_url && (
            <div className="overflow-hidden rounded-3xl border border-radar-border bg-black/20">
              <Image
                src={profile.hero_image_url}
                alt={profile.display_name}
                width={1600}
                height={900}
                className="h-72 w-full object-cover"
              />
            </div>
          )}

          <div className="grid gap-4 xl:grid-cols-[1.05fr,0.95fr]">
            <div className="space-y-4">
              <ProfileCard title="Model DNA">
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Fact label="Production years" value={profile.production_years ?? "-"} />
                    <Fact label="Profile source" value={profile.profile_source} />
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Body Styles</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.body_styles.map((item) => ({
                          label: item,
                          value: item,
                        }))}
                        fallback="No body styles listed yet"
                      />
                    </div>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Transmissions</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.transmissions.map((item) => ({
                          label: item,
                          value: item,
                        }))}
                        fallback="No transmissions listed yet"
                      />
                    </div>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Notable Trims</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.notable_trims.map((item) => ({
                          label: item,
                          value: item,
                        }))}
                        fallback="No notable trims listed yet"
                      />
                    </div>
                  </div>
                </div>
              </ProfileCard>

              {Object.keys(profile.encyclopedia_facts).length > 0 && (
                <ProfileCard title="Encyclopedia Snapshot">
                  <div className="grid gap-3 sm:grid-cols-2">
                    {Object.entries(profile.encyclopedia_facts).map(([label, value]) => (
                      <Fact key={label} label={label} value={value} />
                    ))}
                  </div>
                </ProfileCard>
              )}

              <ProfileCard title="Garage Radar Snapshot">
                <div className="grid gap-3 sm:grid-cols-2">
                  {Object.entries(profile.market_facts).map(([label, value]) => (
                    <Fact key={label} label={label} value={value} />
                  ))}
                </div>
              </ProfileCard>

              <ProfileCard title="Market Context">
                <p className="text-sm leading-6 text-gray-300">{profile.market_summary}</p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <Fact label="Listings tracked" value={String(profile.stats.listing_count)} />
                  <Fact label="Comps tracked" value={String(profile.stats.comp_count)} />
                  <Fact
                    label="Observed asks"
                    value={fmtCurrency(profile.stats.avg_asking_price, profile.stats.primary_currency ?? listing.currency)}
                  />
                  <Fact
                    label="Observed sales"
                    value={fmtCurrency(profile.stats.avg_sale_price, profile.stats.primary_currency ?? listing.currency)}
                  />
                </div>
              </ProfileCard>

              {profile.market_signals.length > 0 && (
                <ProfileCard title="Pricing Signals">
                  <BulletList items={profile.market_signals} />
                </ProfileCard>
              )}

              {profile.local_observations.length > 0 && (
                <ProfileCard title="Local Observations">
                  <BulletList items={profile.local_observations} />
                </ProfileCard>
              )}

              {profile.external_sections.length > 0 && (
                <ProfileCard title="Reference Dossier">
                  <div className="space-y-4">
                    {profile.external_sections.map((section) => (
                      <div key={`${section.source_name}-${section.title}`} className="rounded-xl border border-radar-border p-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <h4 className="text-sm font-semibold text-gray-100">{section.title}</h4>
                            <p className="mt-2 text-sm leading-6 text-gray-300">{section.summary}</p>
                          </div>
                          {section.source_url && (
                            <a
                              href={section.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="shrink-0 text-xs uppercase tracking-wide text-radar-muted hover:text-white"
                            >
                              {section.source_name}
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </ProfileCard>
              )}
            </div>

            <div className="space-y-4">
              <ProfileCard title="Coverage Map">
                <div className="space-y-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Sources</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.source_breakdown.map((item) => ({
                          label: `${sourceLabel(item.label)} (${item.count})`,
                          value: item.label,
                        }))}
                        fallback="No source coverage yet"
                      />
                    </div>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Observed Years</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.year_breakdown.map((item) => ({
                          label: `${item.label} (${item.count})`,
                          value: item.label,
                        }))}
                        fallback="No year coverage yet"
                      />
                    </div>
                  </div>
                </div>
              </ProfileCard>
              <ProfileCard title="Spec Coverage">
                <div className="space-y-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Body Styles</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.body_style_breakdown.map((item) => ({
                          label: `${item.label} (${item.count})`,
                          value: item.label,
                        }))}
                        fallback="No body styles captured yet"
                      />
                    </div>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-radar-muted">Transmissions</p>
                    <div className="mt-2">
                      <CountChips
                        items={profile.transmission_breakdown.map((item) => ({
                          label: `${item.label} (${item.count})`,
                          value: item.label,
                        }))}
                        fallback="No transmissions captured yet"
                      />
                    </div>
                  </div>
                </div>
              </ProfileCard>
              <ProfileCard title="Recent Listings">
                {profile.recent_listings.length === 0 ? (
                  <p className="text-sm text-radar-muted">No related listings captured yet.</p>
                ) : (
                  <ul className="space-y-3">
                    {profile.recent_listings.map((example) => (
                      <li key={example.id} className="rounded-xl border border-radar-border p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <Link
                              href={`/listings/${example.id}`}
                              className="text-sm font-medium text-gray-100 hover:text-white"
                            >
                              {example.title}
                            </Link>
                            <p className="mt-1 text-xs uppercase tracking-wide text-radar-muted">
                              {sourceLabel(example.source)} | {example.listing_status}
                            </p>
                          </div>
                          <div className="text-right text-sm">
                            <div>{fmtCurrency(example.price, example.currency ?? "USD")}</div>
                            <div className="mt-1 text-xs text-radar-muted">
                              {example.location ?? String(example.year)}
                            </div>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </ProfileCard>
              <ProfileCard title="Recent Sales">
                {profile.recent_sales.length === 0 ? (
                  <p className="text-sm text-radar-muted">No recent sale examples captured yet.</p>
                ) : (
                  <div className="space-y-3">
                    {profile.recent_sales_scope && (
                      <p className="text-xs uppercase tracking-wide text-radar-muted">
                        Using {profile.recent_sales_scope} family sales for context
                      </p>
                    )}
                    <ul className="space-y-3">
                      {profile.recent_sales.map((sale) => (
                        <li key={sale.id} className="rounded-xl border border-radar-border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <a
                                href={sale.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sm font-medium text-gray-100 hover:text-white"
                              >
                                {sale.title}
                              </a>
                              <p className="mt-1 text-xs uppercase tracking-wide text-radar-muted">
                                {sourceLabel(sale.source)} | {sale.sale_date ?? "Unknown sale date"}
                              </p>
                            </div>
                            <div className="text-right text-sm">
                              <div>{fmtCurrency(sale.sale_price, sale.currency ?? "USD")}</div>
                              <div className="mt-1 text-xs text-radar-muted">{sale.year}</div>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </ProfileCard>
              <ProfileCard title="Variant Landscape">
                <CountChips
                  items={profile.related_model_breakdown.map((item) => ({
                    label: `${item.label} (${item.count})`,
                    value: item.label,
                  }))}
                  fallback="No closely related variants are tracked yet"
                />
              </ProfileCard>
              <ProfileCard title="Coverage Gaps">
                <BulletList items={profile.coverage_gaps} />
              </ProfileCard>
              <ProfileCard title="Trim Coverage">
                <CountChips
                  items={profile.trim_breakdown.map((item) => ({
                    label: `${item.label} (${item.count})`,
                    value: item.label,
                  }))}
                  fallback="No trims captured yet"
                />
              </ProfileCard>
              <ProfileCard title="Highlights">
                <BulletList items={profile.highlights} />
              </ProfileCard>
              <ProfileCard title="Buying Tips">
                <BulletList items={profile.buying_tips} />
              </ProfileCard>
              <ProfileCard title="Questions to Answer">
                <BulletList items={profile.common_questions} />
              </ProfileCard>
            </div>
          </div>
        </section>
      )}

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-radar-border bg-radar-card/40 p-5">
          <h2 className="text-lg font-semibold">Open Alerts</h2>
          {listing.alerts.length === 0 ? (
            <p className="mt-3 text-sm text-radar-muted">No active alerts for this listing.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {listing.alerts.map((alert) => (
                <li key={alert.id} className="rounded-xl border border-radar-border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{alert.alert_type}</span>
                    <span className="text-xs uppercase tracking-wide text-radar-muted">{alert.severity}</span>
                  </div>
                  <p className="mt-2 text-sm text-gray-300">{alert.reason}</p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-radar-border bg-radar-card/40 p-5">
          <h2 className="text-lg font-semibold">Price History</h2>
          {!listing.price_history || listing.price_history.length === 0 ? (
            <p className="mt-3 text-sm text-radar-muted">No recorded price changes yet.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {listing.price_history.map((entry, index) => (
                <li
                  key={`${listing.id}-${index}`}
                  className="flex items-center justify-between rounded-xl border border-radar-border p-3"
                >
                  <span className="text-radar-muted">{priceHistoryLabel(entry)}</span>
                  <span className="font-medium">
                    {fmtCurrency(priceHistoryPrice(entry), listing.currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-radar-border bg-black/20 p-3">
      <div className="text-[11px] uppercase tracking-wide text-radar-muted">{label}</div>
      <div className="mt-1 text-sm font-medium text-gray-100">{value}</div>
    </div>
  );
}

function ProfileCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-radar-border bg-black/20 p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-radar-muted">{title}</h3>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-radar-muted">No notes yet.</p>;
  }
  return (
    <ul className="space-y-2 text-sm leading-6 text-gray-300">
      {items.map((item) => (
        <li key={item}>- {item}</li>
      ))}
    </ul>
  );
}

function CountChips({
  items,
  fallback,
}: {
  items: Array<{ label: string; value: string }>;
  fallback: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-radar-muted">{fallback}</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span key={`${item.value}-${item.label}`} className="rounded-full border border-radar-border px-3 py-1 text-sm text-gray-200">
          {item.label}
        </span>
      ))}
    </div>
  );
}

function priceHistoryLabel(entry: Record<string, unknown>) {
  return String(entry.ts ?? entry.date ?? "Unknown date");
}

function priceHistoryPrice(entry: Record<string, unknown>) {
  return typeof entry.price === "number" ? entry.price : null;
}

function priceBand(min: number | null, max: number | null, currency = "USD") {
  if (min == null && max == null) return "-";
  if (min != null && max != null) {
    return `${fmtCurrency(min, currency)} - ${fmtCurrency(max, currency)}`;
  }
  return fmtCurrency(min ?? max, currency);
}

function buildListingSignals(listing: ListingDetail, profile: VehicleProfile | null) {
  const signals: string[] = [];
  const livePrice = listing.current_bid ?? listing.asking_price;

  if (livePrice != null && listing.cluster_median != null && listing.delta_pct != null) {
    const relation = listing.delta_pct > 0 ? "above" : "below";
    if (Math.abs(listing.delta_pct) < 3) {
      signals.push("This live price is sitting roughly in line with the current comp median.");
    } else {
      signals.push(
        `This live price is running about ${Math.abs(listing.delta_pct).toFixed(1)}% ${relation} the current comp median.`
      );
    }
  }

  if (
    livePrice != null &&
    listing.cluster_p25 != null &&
    listing.cluster_p75 != null
  ) {
    if (livePrice < listing.cluster_p25) {
      signals.push("The live price is below the core interquartile comp band, which can signal a discount or a condition/story gap.");
    } else if (livePrice > listing.cluster_p75) {
      signals.push("The live price is above the core interquartile comp band, so provenance and spec need to justify the premium.");
    } else {
      signals.push("The live price falls inside the core interquartile comp band.");
    }
  }

  if (
    profile &&
    livePrice != null &&
    profile.stats.avg_sale_price != null &&
    profile.stats.avg_sale_price > 0
  ) {
    const delta = ((livePrice - profile.stats.avg_sale_price) / profile.stats.avg_sale_price) * 100;
    if (Math.abs(delta) >= 5) {
      const relation = delta > 0 ? "above" : "below";
        signals.push(
          `Versus the family-level average sale price, this live price is about ${Math.abs(delta).toFixed(1)}% ${relation}.`
        );
      }
    }

  if (profile?.related_model_breakdown.length) {
    const variants = profile.related_model_breakdown
      .slice(0, 3)
      .map((item) => item.label)
      .join(", ");
    signals.push(`The closest tracked sibling variants right now are ${variants}.`);
  }

  return signals.slice(0, 4);
}

function displayTimeRemaining(listing: ListingDetail) {
  if (listing.time_remaining_text) return listing.time_remaining_text;
  if (!listing.auction_end_at) return "-";
  const end = parseAuctionDate(listing.auction_end_at);
  if (!end) return listing.auction_end_at;
  const diffMs = end.getTime() - Date.now();
  if (diffMs <= 0) return "ended";
  const totalMinutes = Math.floor(diffMs / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatAuctionEnd(value: string | null) {
  if (!value) return "-";
  const end = parseAuctionDate(value);
  if (!end) return value;
  const hasTime = value.includes("T");
  return end.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: hasTime ? "numeric" : undefined,
    minute: hasTime ? "2-digit" : undefined,
  });
}

function formatSimpleDate(value: string | null) {
  if (!value) return "-";
  const parsed = parseAuctionDate(value);
  if (!parsed) return value;
  return parsed.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function parseAuctionDate(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T00:00:00`);
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}
