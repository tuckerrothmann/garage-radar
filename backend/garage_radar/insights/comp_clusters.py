"""
Comp cluster builder.

Computes median/P25/P75/min/max price bands per spec cluster
(generation × body_style × transmission) using completed sales (comps).

Design decisions:
  - Two-pass windowing: try comp_window_days (default 90). If a cluster is thin
    (< min_size comps) widen to comp_window_thin_days (default 180). If still
    thin, mark insufficient_data=True and record what we have — don't silently drop.
  - All percentile arithmetic is done server-side via PostgreSQL percentile_cont,
    so we never load raw comp rows into Python memory.
  - Clusters where any of generation/body_style/transmission is NULL are excluded;
    they can't be reliably priced.
  - Cluster key format: "{generation}:{body_style}:{transmission}" e.g. "G6:coupe:manual"
  - Upsert on cluster_key — rebuilding nightly is safe.
"""
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.config import get_settings
from garage_radar.db.models import Comp, CompCluster

logger = logging.getLogger(__name__)


# ── Cluster computation ───────────────────────────────────────────────────────

async def rebuild_comp_clusters(
    session: AsyncSession,
    window_days: Optional[int] = None,
    thin_window_days: Optional[int] = None,
    min_size: Optional[int] = None,
) -> dict:
    """
    Recompute all comp clusters and upsert into comp_clusters table.

    Returns a stats dict: {total, updated, insufficient_data}.
    """
    settings = get_settings()
    window_days = window_days or settings.comp_window_days
    thin_window_days = thin_window_days or settings.comp_window_thin_days
    min_size = min_size or settings.comp_cluster_min_size

    # Pass 1: primary window
    primary_rows = await _fetch_cluster_stats(session, window_days)

    # Pass 2: for thin clusters, widen the window
    thin_keys = {
        r["cluster_key"] for r in primary_rows
        if r["comp_count"] < min_size
    }

    # Fetch thin-window stats only for thin clusters (avoid duplicate network round-trip)
    thin_rows: dict[str, dict] = {}
    if thin_keys:
        wide_rows = await _fetch_cluster_stats(session, thin_window_days)
        thin_rows = {r["cluster_key"]: r for r in wide_rows if r["cluster_key"] in thin_keys}

    # Merge: prefer primary stats; fall back to thin-window for thin clusters
    merged: dict[str, dict] = {}
    for row in primary_rows:
        key = row["cluster_key"]
        if key in thin_rows:
            # Use wider window stats; tag the window_days used
            wide = thin_rows[key]
            wide["window_days"] = thin_window_days
            wide["insufficient_data"] = wide["comp_count"] < min_size
            merged[key] = wide
        else:
            row["window_days"] = window_days
            row["insufficient_data"] = row["comp_count"] < min_size
            merged[key] = row

    # Also include any clusters that only appear in the wide window
    for key, row in thin_rows.items():
        if key not in merged:
            row["window_days"] = thin_window_days
            row["insufficient_data"] = row["comp_count"] < min_size
            merged[key] = row

    if not merged:
        logger.info("comp_clusters: no comps found — nothing to compute.")
        return {"total": 0, "updated": 0, "insufficient_data": 0}

    # Upsert all clusters
    insufficient_count = 0
    for row in merged.values():
        await _upsert_cluster(session, row)
        if row["insufficient_data"]:
            insufficient_count += 1

    await session.commit()

    stats = {
        "total": len(merged),
        "updated": len(merged),
        "insufficient_data": insufficient_count,
    }
    logger.info(
        "comp_clusters: rebuilt %d clusters (%d insufficient data).",
        stats["total"],
        stats["insufficient_data"],
    )
    return stats


async def _fetch_cluster_stats(session: AsyncSession, window_days: int) -> list[dict]:
    """
    Query comps table for price band stats per (generation, body_style, transmission).

    Uses server-side percentile_cont — no Python-side sorting or statistics.
    Only comps with non-null sale_price, generation, body_style, and transmission
    are included; partial-spec comps can't anchor a cluster.
    """
    cutoff = date.today() - timedelta(days=window_days)

    stmt = (
        select(
            Comp.generation,
            Comp.body_style,
            Comp.transmission,
            func.count().label("comp_count"),
            func.percentile_cont(0.5)
                .within_group(Comp.sale_price)
                .label("median_price"),
            func.percentile_cont(0.25)
                .within_group(Comp.sale_price)
                .label("p25_price"),
            func.percentile_cont(0.75)
                .within_group(Comp.sale_price)
                .label("p75_price"),
            func.min(Comp.sale_price).label("min_price"),
            func.max(Comp.sale_price).label("max_price"),
            func.avg(Comp.confidence_score).label("avg_confidence"),
        )
        .where(
            Comp.sale_price.is_not(None),
            Comp.generation.is_not(None),
            Comp.body_style.is_not(None),
            Comp.transmission.is_not(None),
            Comp.sale_date >= cutoff,
        )
        .group_by(Comp.generation, Comp.body_style, Comp.transmission)
    )

    result = await session.execute(stmt)
    rows = []
    for row in result.mappings():
        gen = row["generation"]
        bs = row["body_style"]
        tx = row["transmission"]
        # Enum values may be enum instances or raw strings depending on driver
        gen_val = gen.value if hasattr(gen, "value") else str(gen)
        bs_val = bs.value if hasattr(bs, "value") else str(bs)
        tx_val = tx.value if hasattr(tx, "value") else str(tx)
        rows.append({
            "cluster_key": f"{gen_val}:{bs_val}:{tx_val}",
            "generation": gen,
            "body_style": bs,
            "transmission": tx,
            "comp_count": row["comp_count"],
            "median_price": _to_float(row["median_price"]),
            "p25_price": _to_float(row["p25_price"]),
            "p75_price": _to_float(row["p75_price"]),
            "min_price": _to_float(row["min_price"]),
            "max_price": _to_float(row["max_price"]),
            "avg_confidence": _to_float(row["avg_confidence"]),
        })
    return rows


async def _upsert_cluster(session: AsyncSession, row: dict) -> None:
    """INSERT ... ON CONFLICT (cluster_key) DO UPDATE for a single cluster row."""
    values = {
        "cluster_key": row["cluster_key"],
        "generation": row["generation"],
        "body_style": row["body_style"],
        "transmission": row["transmission"],
        "window_days": row["window_days"],
        "comp_count": row["comp_count"],
        "median_price": row.get("median_price"),
        "p25_price": row.get("p25_price"),
        "p75_price": row.get("p75_price"),
        "min_price": row.get("min_price"),
        "max_price": row.get("max_price"),
        "avg_confidence": row.get("avg_confidence"),
        "insufficient_data": row["insufficient_data"],
        "last_computed_at": text("now()"),
    }

    stmt = (
        pg_insert(CompCluster)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["cluster_key"],
            set_={
                k: values[k]
                for k in values
                if k != "cluster_key"
            },
        )
    )
    await session.execute(stmt)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_float(val) -> Optional[float]:
    """Coerce Decimal / None from SQLAlchemy result to Optional[float]."""
    if val is None:
        return None
    return float(val)


def cluster_key_for(generation: str, body_style: str, transmission: str) -> str:
    """Canonical cluster key — also used by alert engine and API."""
    return f"{generation}:{body_style}:{transmission}"
