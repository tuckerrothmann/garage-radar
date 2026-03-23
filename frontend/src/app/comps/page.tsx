/**
 * Comp clusters — price band table, server component.
 */
import { getCompClusters } from "@/lib/api";

function fmt(n: number | null) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
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
      {/* IQR band */}
      <div
        className="absolute h-2 bg-blue-700/60 rounded"
        style={{ left: pct(p25), width: `${((p75 - p25) / range) * 100}%` }}
      />
      {/* Median tick */}
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
  let clusters;
  let error: string | null = null;
  try {
    clusters = await getCompClusters({
      generation:   searchParams.generation,
      body_style:   searchParams.body_style,
      transmission: searchParams.transmission,
    });
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load comp clusters";
  }

  const insufficient = clusters?.filter(c => c.insufficient_data) ?? [];
  const sufficient   = clusters?.filter(c => !c.insufficient_data) ?? [];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Comp Clusters</h1>
          <p className="text-radar-muted text-sm mt-1">
            Price bands per generation × body style × transmission.
            Median = blue tick. Bar = P25–P75.
          </p>
        </div>
        {clusters && (
          <span className="text-radar-muted text-sm">
            {clusters.length} cluster{clusters.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4 text-red-300">
          {error}
        </div>
      )}

      {sufficient.length > 0 && (
        <ClusterTable clusters={sufficient} title="Price bands" />
      )}

      {insufficient.length > 0 && (
        <ClusterTable
          clusters={insufficient}
          title="Thin clusters (insufficient data)"
          muted
        />
      )}

      {clusters?.length === 0 && (
        <div className="text-center py-16 text-radar-muted">
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
              {["Generation", "Body", "Trans", "Comps", "Window", "P25", "Median", "P75", "Range", ""].map(h => (
                <th key={h} className="px-4 py-3 text-right first:text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-radar-border">
            {clusters.map(c => (
              <tr
                key={c.cluster_key}
                className={`hover:bg-radar-card/50 transition-colors ${
                  muted ? "opacity-60" : ""
                }`}
              >
                <td className="px-4 py-3 font-mono font-semibold">{c.generation}</td>
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
