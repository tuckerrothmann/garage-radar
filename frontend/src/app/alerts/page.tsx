/**
 * Alerts inbox — server component with client-side dismiss actions.
 */
import { getAlerts } from "@/lib/api";
import AlertList from "@/components/AlertList";

interface PageProps {
  searchParams: Record<string, string | undefined>;
}

const STATUS_TABS = [
  { value: "open",      label: "Open"      },
  { value: "read",      label: "Read"      },
  { value: "dismissed", label: "Dismissed" },
];

export default async function AlertsPage({ searchParams }: PageProps) {
  const status = searchParams.status ?? "open";
  const offset = Number(searchParams.offset ?? 0);
  const limit  = 50;

  let page;
  let error: string | null = null;
  try {
    page = await getAlerts(status, limit, offset);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load alerts";
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Alerts</h1>
        {page && page.total > 0 && status === "open" && (
          <form action="/api/dismiss-all" method="POST">
            <button
              type="submit"
              className="text-sm px-3 py-1.5 rounded border border-radar-border
                         hover:bg-radar-card text-radar-muted hover:text-white transition-colors"
            >
              Dismiss all
            </button>
          </form>
        )}
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 border-b border-radar-border pb-0">
        {STATUS_TABS.map(tab => (
          <a
            key={tab.value}
            href={`/alerts?status=${tab.value}`}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              status === tab.value
                ? "bg-radar-card text-white border-b-2 border-radar-red"
                : "text-radar-muted hover:text-white"
            }`}
          >
            {tab.label}
          </a>
        ))}
      </div>

      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4 text-red-300">
          {error}
        </div>
      )}

      {page && (
        <>
          <AlertList alerts={page.items} currentStatus={status} />

          {/* Pagination */}
          {page.total > limit && (
            <div className="flex justify-between text-sm text-radar-muted">
              <span>{offset + 1}–{Math.min(offset + limit, page.total)} of {page.total}</span>
              <div className="flex gap-2">
                {offset > 0 && (
                  <a
                    href={`/alerts?status=${status}&offset=${Math.max(0, offset - limit)}`}
                    className="px-3 py-1.5 rounded border border-radar-border hover:bg-radar-card text-white"
                  >
                    ← Prev
                  </a>
                )}
                {offset + limit < page.total && (
                  <a
                    href={`/alerts?status=${status}&offset=${offset + limit}`}
                    className="px-3 py-1.5 rounded border border-radar-border hover:bg-radar-card text-white"
                  >
                    Next →
                  </a>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
