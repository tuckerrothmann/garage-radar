/**
 * Pure SVG sparkline for listing price history.
 * No chart library dependencies — uses a viewBox-based SVG polyline.
 */

interface PricePoint {
  price: number;
  ts: string;
}

interface Props {
  priceHistory: PricePoint[];
  currentPrice: number | null;
  updatedAt: string;
}

function fmtK(n: number): string {
  return `$${(n / 1000).toFixed(0)}k`;
}

function fmtDate(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

export default function PriceHistoryChart({ priceHistory, currentPrice, updatedAt }: Props) {
  // Build combined series: history entries + current price as the latest point
  const series: PricePoint[] = [
    ...(priceHistory ?? []),
    ...(currentPrice != null ? [{ price: currentPrice, ts: updatedAt }] : []),
  ]
    .filter((p) => p.price != null)
    .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());

  if (series.length < 2) {
    return (
      <div className="flex items-center justify-center h-20 text-radar-muted text-sm">
        No price history yet
      </div>
    );
  }

  // SVG coordinate space
  const W = 400;
  const H = 120;
  const PAD_LEFT = 48;
  const PAD_RIGHT = 12;
  const PAD_TOP = 12;
  const PAD_BOTTOM = 24;

  const innerW = W - PAD_LEFT - PAD_RIGHT;
  const innerH = H - PAD_TOP - PAD_BOTTOM;

  const prices = series.map((p) => p.price);
  const times = series.map((p) => new Date(p.ts).getTime());

  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);

  const priceRange = maxP - minP || 1;
  const timeRange = maxT - minT || 1;

  const toX = (t: number) => PAD_LEFT + ((t - minT) / timeRange) * innerW;
  const toY = (p: number) => PAD_TOP + (1 - (p - minP) / priceRange) * innerH;

  const points = series.map((p) => ({
    x: toX(new Date(p.ts).getTime()),
    y: toY(p.price),
    isCurrent: p === series[series.length - 1],
  }));

  const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ height: 160 }}
      aria-label="Price history chart"
    >
      {/* Y-axis labels */}
      <text
        x={PAD_LEFT - 6}
        y={PAD_TOP + 4}
        textAnchor="end"
        fontSize={10}
        fill="#6B7280"
      >
        {fmtK(maxP)}
      </text>
      <text
        x={PAD_LEFT - 6}
        y={PAD_TOP + innerH + 4}
        textAnchor="end"
        fontSize={10}
        fill="#6B7280"
      >
        {fmtK(minP)}
      </text>

      {/* X-axis labels */}
      <text
        x={PAD_LEFT}
        y={H - 4}
        textAnchor="start"
        fontSize={10}
        fill="#6B7280"
      >
        {fmtDate(series[0].ts)}
      </text>
      <text
        x={W - PAD_RIGHT}
        y={H - 4}
        textAnchor="end"
        fontSize={10}
        fill="#6B7280"
      >
        {fmtDate(series[series.length - 1].ts)}
      </text>

      {/* Horizontal guide lines */}
      <line
        x1={PAD_LEFT}
        y1={PAD_TOP}
        x2={W - PAD_RIGHT}
        y2={PAD_TOP}
        stroke="#374151"
        strokeWidth={1}
        strokeDasharray="3 3"
      />
      <line
        x1={PAD_LEFT}
        y1={PAD_TOP + innerH}
        x2={W - PAD_RIGHT}
        y2={PAD_TOP + innerH}
        stroke="#374151"
        strokeWidth={1}
        strokeDasharray="3 3"
      />

      {/* Polyline */}
      <polyline
        points={polylinePoints}
        fill="none"
        stroke="#CC0000"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Dots */}
      {points.map((p, i) =>
        p.isCurrent ? (
          // Current price: larger, highlighted
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={6} fill="#1F2937" stroke="#3B82F6" strokeWidth={2} />
            <circle cx={p.x} cy={p.y} r={3} fill="white" />
          </g>
        ) : (
          <circle key={i} cx={p.x} cy={p.y} r={3} fill="#CC0000" />
        )
      )}
    </svg>
  );
}
