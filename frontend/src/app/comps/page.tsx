/**
 * Comp clusters page.
 */
import { getCompClusters } from "@/lib/api";
import { allValues, parseNumberValues, type SearchParams } from "@/lib/search-params";

function fmt(n: number | null, currency = "USD") {
  if (n == null) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

function PriceBar({
  p25,
  median,
  p75,
  min,
  max,
}: {
  p25: number | null;
  median: number | null;
  p75: number | null;
  min: number | null;
  max: number | null;
}) {
  if (!p25 || !median || !p75 || !min || !max) return null;
  const range = max - min || 1;
  const pct = (v: number) => `${(((v - min) / range) * 100).toFixed(1)}%`;

  return (
    <div className="relative h-2 w-full min-w-[80px] rounded-full bg-radar-border">
      <div
        className="absolute h-2 rounded bg-blue-700/60"
        style={{ left: pct(p25), width: `${((p75 - p25) / range) * 100}%` }}
      />
      <div
        className="absolute -top-0.5 h-3 w-0.5 rounded bg-blue-400"
        style={{ left: pct(median) }}
      />
    </div>
  );
}

function specLabel(generation: string | null, yearBucket: number | null) {
  if (generation) return generation;
  if (yearBucket != null) return `Y${yearBucket}`;
  return "Unknown";
}

interface PageProps {
  searchParams: SearchParams;
}

type CompClusters = Awaited<ReturnType<typeof getCompClusters>>;

export default async function CompsPage({ searchParams }: PageProps) {
  let clusters: CompClusters | null = null;
  let error: string | null = null;
  try {
    clusters = await getCompClusters({
      make: allValues(searchParams.make),
      model: allValues(searchParams.model),
      generation: allValues(searchParams.generation),
      year_bucket: parseNumberValues(searchParams.year_bucket),
      body_style: allValues(searchParams.body_style),
      transmission: allValues(searchParams.transmission),
    });
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load comp clusters";
  }

  const insufficient = (clusters ?? []).filter((c) => c.insufficient_data);
  const sufficient = (clusters ?? []).filter((c) => !c.insufficient_data);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Comp Clusters</h1>
          <p className="mt-1 text-sm text-radar-muted">
            Price bands per make/model/spec cluster. Median = blue tick. Bar = P25-P75.
          </p>
        </div>
        {clusters && (
          <span className="text-sm text-radar-muted">
            {clusters.length} cluster{clusters.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-700 bg-red-950 p-4 text-red-300">
          {error}
        </div>
      )}

      {sufficient.length > 0 && <ClusterTable clusters={sufficient} title="Price bands" />}

      {insufficient.length > 0 && (
        <ClusterTable
          clusters={insufficient}
          title="Thin clusters (insufficient data)"
          muted
        />
      )}

      {clusters?.length === 0 && (
        <div className="py-16 text-center text-radar-muted">
          No comp clusters yet. Run the insight pipeline to compute them.
        </div>
      )}
    </div>
  );
}

function ClusterTable({
  clusters,
  title,
  muted = false,
}: {
  clusters: CompClusters;
  title: string;
  muted?: boolean;
}) {
  return (
    <section>
      <h2
        className={`mb-3 text-sm font-semibold uppercase tracking-wide ${
          muted ? "text-radar-muted" : "text-gray-300"
        }`}
      >
        {title}
      </h2>
      <div className="overflow-x-auto rounded-lg border border-radar-border">
        <table className="w-full text-sm">
          <thead className="bg-radar-card text-xs uppercase tracking-wide text-radar-muted">
            <tr>
              {[
                "Make",
                "Model",
                "Spec",
                "Body",
                "Trans",
                "Cur",
                "Comps",
                "Window",
                "P25",
                "Median",
                "P75",
                "Range",
                "",
              ].map((h) => (
                <th key={h} className="px-4 py-3 text-right first:text-left">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-radar-border">
            {clusters.map((c) => (
              <tr
                key={c.cluster_key}
                className={`transition-colors hover:bg-radar-card/50 ${
                  muted ? "opacity-60" : ""
                }`}
              >
                <td className="px-4 py-3 font-semibold">{c.make ?? "Unknown"}</td>
                <td className="px-4 py-3">{c.model ?? "Unknown"}</td>
                <td className="px-4 py-3 font-mono font-semibold">
                  {specLabel(c.generation, c.year_bucket)}
                </td>
                <td className="px-4 py-3 capitalize">{c.body_style}</td>
                <td className="px-4 py-3 text-radar-muted">{c.transmission}</td>
                <td className="px-4 py-3 text-radar-muted">{c.currency}</td>
                <td className="px-4 py-3 text-right tabular-nums">{c.comp_count}</td>
                <td className="px-4 py-3 text-right text-radar-muted">{c.window_days}d</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmt(c.p25_price, c.currency)}</td>
                <td className="px-4 py-3 text-right font-semibold tabular-nums">
                  {fmt(c.median_price, c.currency)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{fmt(c.p75_price, c.currency)}</td>
                <td className="w-40 px-4 py-3">
                  <PriceBar
                    p25={c.p25_price}
                    median={c.median_price}
                    p75={c.p75_price}
                    min={c.min_price}
                    max={c.max_price}
                  />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right text-xs text-radar-muted">
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
