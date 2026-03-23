/**
 * Comps — price band clusters + recent sold listings, server component.
 */
import { getCompClusters, getComps } from "@/lib/api";

function fmt(n: number | null, currency = "USD") {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

function PriceBar({ p25, median, p75, min, max }: {
  p25: number | null;
  median: number | null;
  p75: number | null;
  min: number | null;
  max: number | null;
}) {
  if (!p25 || !median || !p75 || !min || !max) return null;
  const range = max - min || 1;
  const pct = (v: number) => `${((v - min) / range * 100).toFixed(1)}%`;

  return (
    <div className="relative h-2 bg-radar-border rounded-full w-full min-w-[80px]">
      <div
        className="absolute h-2 bg-blue-700/60 rounded"
        style={{ left: pct(p25), width: `${((p75 - p25) / range) * 100}%` }}
      />
      <div
        className="absolute h-3 w-0.5 bg-blue-400 rounded -top-0.5"
        style={{ left: pct(median) }}
      />
    </div>
  );
}

interface PageProps {
  searchParams: Record<string, string | undefined>;
}

export default async function CompsPage({ searchParams }: PageProps) {
  const make  = searchParams.make;
  const model = searchParams.model;

  let clusters;
  let compsPage;
  let error: string | null = null;

  try {
    [clusters, compsPage] = await Promise.all([
      getCompClusters({ make, model, body_style: searchParams.body_style, transmission: searchParams.transmission }),
      getComps({ make, model, body_style: searchParams.body_style, transmission: searchParams.transmission, limit: 50 }),
    ]);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load comps";
  }

  const insufficient = clusters?.filter(c => c.insufficient_data) ?? [];
  const sufficient   = clusters?.filter(c => !c.insufficient_data) ?? [];

  return (
    <div className="space-y-8">
      {/* Header + filters */}
      <div className="flex flex-wrap items-end gap-4 justify-between">
        <div>
          <h1 className="text-2xl font-bold">Comp Prices</h1>
          <p className="text-radar-muted text-sm mt-1">
            Price bands and recent sold listings.
          </p>
        </div>
        <form method="get" className="flex flex-wrap gap-2 items-end">
          <input
            name="make"
            defaultValue={make}
            placeholder="Make"
            className="bg-radar-card border border-radar-border rounded px-3 py-1.5 text-sm w-32 focus:outline-none focus:border-blue-500"
          />
          <input
            name="model"
            defaultValue={model}
            placeholder="Model"
            className="bg-radar-card border border-radar-border rounded px-3 py-1.5 text-sm w-32 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            className="px-3 py-1.5 rounded border border-radar-border bg-radar-card text-sm hover:bg-radar-card/80"
          >
            Filter
          </button>
          {(make || model) && (
            <a
              href="/comps"
              className="px-3 py-1.5 rounded border border-radar-border text-sm text-radar-muted hover:text-white"
            >
              Clear
            </a>
          )}
        </form>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4 text-red-300">
          {error}
        </div>
      )}

      {/* Price band clusters */}
      {sufficient.length > 0 && (
        <ClusterTable clusters={sufficient} title="Price bands" />
      )}
      {insufficient.length > 0 && (
        <ClusterTable clusters={insufficient} title="Thin clusters (insufficient data)" muted />
      )}
      {clusters?.length === 0 && (
        <div className="text-center py-8 text-radar-muted">
          No comp clusters yet. Run the insight pipeline to compute them.
        </div>
      )}

      {/* Recent sold listings */}
      {compsPage && compsPage.items.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide mb-3 text-gray-300">
            Recent Sales
            <span className="text-radar-muted font-normal ml-2">
              ({compsPage.total.toLocaleString()} total)
            </span>
          </h2>
          <div className="overflow-x-auto rounded-lg border border-radar-border">
            <table className="w-full text-sm">
              <thead className="bg-radar-card text-radar-muted uppercase text-xs tracking-wide">
                <tr>
                  {["Year", "Vehicle", "Body", "Trans", "Mileage", "Sale Price", "Date", "Source"].map(h => (
                    <th key={h} className="px-4 py-3 text-left whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-radar-border">
                {compsPage.items.map(comp => (
                  <tr key={comp.id} className="hover:bg-radar-card/50 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold">{comp.year}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium">
                        {[comp.make, comp.model].filter(Boolean).join(" ") || "—"}
                      </div>
                      {comp.generation && (
                        <div className="text-xs text-radar-muted">{comp.generation}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 capitalize text-radar-muted">{comp.body_style ?? "—"}</td>
                    <td className="px-4 py-3 text-radar-muted">{comp.transmission ?? "—"}</td>
                    <td className="px-4 py-3 tabular-nums text-right">
                      {comp.mileage != null ? comp.mileage.toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums font-semibold text-right">
                      {fmt(comp.sale_price)}
                    </td>
                    <td className="px-4 py-3 text-radar-muted whitespace-nowrap">
                      {comp.sale_date ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={comp.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-radar-red hover:underline uppercase"
                      >
                        {comp.source}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function ClusterTable({
  clusters,
  title,
  muted = false,
}: {
  clusters: NonNullable<Awaited<ReturnType<typeof getCompClusters>>>;
  title: string;
  muted?: boolean;
}) {
  return (
    <section>
      <h2 className={`text-sm font-semibold uppercase tracking-wide mb-3 ${
        muted ? "text-radar-muted" : "text-gray-300"
      }`}>
        {title}
      </h2>
      <div className="overflow-x-auto rounded-lg border border-radar-border">
        <table className="w-full text-sm">
          <thead className="bg-radar-card text-radar-muted uppercase text-xs tracking-wide">
            <tr>
              {["Make / Model", "Body", "Trans", "Comps", "Window", "P25", "Median", "P75", "Range", ""].map(h => (
                <th key={h} className="px-4 py-3 text-right first:text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-radar-border">
            {clusters.map(c => (
              <tr
                key={c.cluster_key}
                className={`hover:bg-radar-card/50 transition-colors ${muted ? "opacity-60" : ""}`}
              >
                <td className="px-4 py-3 font-medium">
                  {c.make} {c.model}
                </td>
                <td className="px-4 py-3 capitalize">{c.body_style}</td>
                <td className="px-4 py-3 text-radar-muted">{c.transmission}</td>
                <td className="px-4 py-3 text-right tabular-nums">{c.comp_count}</td>
                <td className="px-4 py-3 text-right text-radar-muted">{c.window_days}d</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmt(c.p25_price)}</td>
                <td className="px-4 py-3 text-right tabular-nums font-semibold">{fmt(c.median_price)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmt(c.p75_price)}</td>
                <td className="px-4 py-3 w-40">
                  <PriceBar
                    p25={c.p25_price}
                    median={c.median_price}
                    p75={c.p75_price}
                    min={c.min_price}
                    max={c.max_price}
                  />
                </td>
                <td className="px-4 py-3 text-right text-xs text-radar-muted whitespace-nowrap">
                  {new Date(c.last_computed_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
