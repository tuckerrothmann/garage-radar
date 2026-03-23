"use client";

import { useState } from "react";
import type { WatchedVehicle } from "@/lib/api";
import { addToWatchlist, removeFromWatchlist } from "@/lib/api";

export default function WatchlistClient({
  initialVehicles,
}: {
  initialVehicles: WatchedVehicle[];
}) {
  const [vehicles, setVehicles] = useState(initialVehicles);
  const [form, setForm] = useState({ make: "", model: "", year_min: "", year_max: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const year_min = parseInt(form.year_min);
    const year_max = parseInt(form.year_max);
    if (!form.make || !form.model || isNaN(year_min) || isNaN(year_max)) {
      setError("All fields are required.");
      return;
    }
    if (year_max < year_min) {
      setError("Year Max must be ≥ Year Min.");
      return;
    }
    setSaving(true);
    try {
      const added = await addToWatchlist({ make: form.make, model: form.model, year_min, year_max });
      setVehicles(v => [...v, added]);
      setForm({ make: "", model: "", year_min: "", year_max: "" });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add vehicle");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove(index: number) {
    setError(null);
    try {
      await removeFromWatchlist(index);
      // Re-index after removal
      setVehicles(v => v.filter((_, i) => i !== index).map((v, i) => ({ ...v, index: i })));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to remove vehicle");
    }
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Current watchlist */}
      {vehicles.length === 0 ? (
        <div className="text-center py-10 text-radar-muted border border-radar-border rounded-lg">
          No vehicles in watchlist. Add one below.
        </div>
      ) : (
        <div className="rounded-lg border border-radar-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-radar-card text-radar-muted uppercase text-xs tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left">Make</th>
                <th className="px-4 py-3 text-left">Model</th>
                <th className="px-4 py-3 text-right">Year Min</th>
                <th className="px-4 py-3 text-right">Year Max</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-radar-border">
              {vehicles.map((v) => (
                <tr key={v.index} className="hover:bg-radar-card/50 transition-colors">
                  <td className="px-4 py-3 font-medium">{v.make}</td>
                  <td className="px-4 py-3">{v.model}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{v.year_min}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{v.year_max}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleRemove(v.index)}
                      className="text-xs text-red-400 hover:text-red-300 hover:underline"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add form */}
      <div className="border border-radar-border rounded-lg p-5 bg-radar-card/30">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-300 mb-4">
          Add Vehicle
        </h2>
        <form onSubmit={handleAdd} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs text-radar-muted mb-1">Make</label>
            <input
              value={form.make}
              onChange={e => setForm(f => ({ ...f, make: e.target.value }))}
              placeholder="Porsche"
              className="w-full bg-radar-card border border-radar-border rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs text-radar-muted mb-1">Model</label>
            <input
              value={form.model}
              onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
              placeholder="911"
              className="w-full bg-radar-card border border-radar-border rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs text-radar-muted mb-1">Year Min</label>
            <input
              type="number"
              value={form.year_min}
              onChange={e => setForm(f => ({ ...f, year_min: e.target.value }))}
              placeholder="1965"
              min={1900}
              max={2030}
              className="w-full bg-radar-card border border-radar-border rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs text-radar-muted mb-1">Year Max</label>
            <input
              type="number"
              value={form.year_max}
              onChange={e => setForm(f => ({ ...f, year_max: e.target.value }))}
              placeholder="1998"
              min={1900}
              max={2030}
              className="w-full bg-radar-card border border-radar-border rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="col-span-2 sm:col-span-4 flex justify-end pt-1">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded bg-blue-700 hover:bg-blue-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "Adding…" : "Add to Watchlist"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
