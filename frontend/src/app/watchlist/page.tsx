/**
 * Watchlist management page — shows watched vehicles and allows add/remove.
 */
import { getWatchlist } from "@/lib/api";
import WatchlistClient from "./WatchlistClient";

export default async function WatchlistPage() {
  let vehicles: import("@/lib/api").WatchedVehicle[] = [];
  let error: string | null = null;
  try {
    vehicles = await getWatchlist();
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load watchlist";
    vehicles = [];
  }

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">Watchlist</h1>
        <p className="text-radar-muted text-sm mt-1">
          Vehicles the crawlers search for on every nightly run.
          Changes take effect on the next scheduled crawl.
        </p>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4 text-red-300">
          {error}
        </div>
      )}

      <WatchlistClient initialVehicles={vehicles} />
    </div>
  );
}
