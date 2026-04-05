import clsx from "clsx";

const COLORS: Record<string, string> = {
  act:   "bg-red-900 text-red-300 border border-red-700",
  watch: "bg-yellow-900 text-yellow-300 border border-yellow-700",
  info:  "bg-gray-700 text-gray-300 border border-gray-600",
};

export default function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={clsx(
      "inline-block px-2 py-0.5 rounded text-xs font-bold uppercase",
      COLORS[severity] ?? COLORS.info,
    )}>
      {severity}
    </span>
  );
}
