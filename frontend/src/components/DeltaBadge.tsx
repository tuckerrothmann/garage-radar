import clsx from "clsx";

interface Props {
  delta: number | null;
}

/**
 * Shows asking price vs cluster median as a coloured pill.
 * Green  = priced below median (potential deal)
 * Red    = priced above median
 * Grey   = no cluster data
 */
export default function DeltaBadge({ delta }: Props) {
  if (delta === null) {
    return <span className="text-xs text-radar-muted">no data</span>;
  }

  const sign = delta > 0 ? "+" : "";
  const label = `${sign}${delta.toFixed(1)}%`;

  return (
    <span
      className={clsx(
        "inline-block px-2 py-0.5 rounded text-xs font-semibold tabular-nums",
        delta <= -15 ? "bg-green-900 text-green-300" :
        delta < 0   ? "bg-green-950 text-green-400" :
        delta > 15  ? "bg-red-900 text-red-300" :
                      "bg-red-950 text-red-400",
      )}
    >
      {label} vs median
    </span>
  );
}
