"use client";

import { useState } from "react";
import { patchAlertStatus, type Alert } from "@/lib/api";
import SeverityBadge from "@/components/SeverityBadge";

const TYPE_LABELS: Record<string, string> = {
  underpriced:             "Underpriced",
  price_drop:              "Price Drop",
  new_listing:             "New Listing",
  relist:                  "Relist",
  insufficient_data_warning: "Data Warning",
};

function relativeTime(iso: string) {
  const ms = Date.now() - new Date(iso).getTime();
  const h = Math.floor(ms / 3600000);
  if (h < 1)  return `${Math.floor(ms / 60000)}m ago`;
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function AlertList({
  alerts: initialAlerts,
  currentStatus,
}: {
  alerts: Alert[];
  currentStatus: string;
}) {
  const [alerts, setAlerts] = useState(initialAlerts);
  const [loading, setLoading] = useState<string | null>(null);

  async function handleAction(id: string, action: "read" | "dismissed") {
    setLoading(id);
    try {
      await patchAlertStatus(id, action);
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch {
      // silent — alert stays in list
    } finally {
      setLoading(null);
    }
  }

  if (alerts.length === 0) {
    return (
      <div className="text-center py-16 text-radar-muted">
        No {currentStatus} alerts.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map(alert => (
        <div
          key={alert.id}
          className="flex items-start gap-4 bg-radar-card border border-radar-border
                     rounded-lg px-4 py-3"
        >
          {/* Severity */}
          <div className="pt-0.5 shrink-0">
            <SeverityBadge severity={alert.severity} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-sm">
                {TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
              </span>
              {alert.delta_pct != null && (
                <span className="text-xs text-radar-muted tabular-nums">
                  {alert.delta_pct > 0 ? "+" : ""}{alert.delta_pct.toFixed(1)}%
                </span>
              )}
              <span className="text-xs text-radar-muted ml-auto shrink-0">
                {relativeTime(alert.triggered_at)}
              </span>
            </div>
            <p className="text-sm text-gray-300 mt-1 break-words">{alert.reason}</p>
          </div>

          {/* Actions */}
          {currentStatus !== "dismissed" && (
            <div className="flex gap-2 shrink-0">
              {currentStatus === "open" && (
                <button
                  onClick={() => handleAction(alert.id, "read")}
                  disabled={loading === alert.id}
                  className="text-xs px-2 py-1 rounded border border-radar-border
                             hover:bg-radar-border text-radar-muted hover:text-white
                             disabled:opacity-40 transition-colors"
                >
                  Mark read
                </button>
              )}
              <button
                onClick={() => handleAction(alert.id, "dismissed")}
                disabled={loading === alert.id}
                className="text-xs px-2 py-1 rounded border border-radar-border
                           hover:bg-radar-border text-radar-muted hover:text-white
                           disabled:opacity-40 transition-colors"
              >
                Dismiss
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
