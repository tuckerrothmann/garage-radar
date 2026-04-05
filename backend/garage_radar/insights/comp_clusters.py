"""
Comp cluster builder.

Computes median/P25/P75/min/max price bands per make/model/spec cluster
using completed sales (comps).

Cluster identity:
  - make/model + body_style + transmission are always required
  - use Porsche generation when available
  - otherwise fall back to exact model year to avoid mixing distant eras

Design decisions:
  - Two-pass windowing: try comp_window_days (default 90). If a cluster is thin
    (< min_size comps) widen to comp_window_thin_days (default 180). If still
    thin, mark insufficient_data=True and record what we have.
  - All percentile arithmetic is done server-side via PostgreSQL
    percentile_cont, so we never load raw comp rows into Python memory.
  - Partial-spec comps are excluded; they cannot anchor a trustworthy cluster.
  - Upsert on cluster_key so rebuilding nightly is safe.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.config import get_settings
from garage_radar.db.models import Comp, CompCluster

logger = logging.getLogger(__name__)


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

    primary_rows = await _fetch_cluster_stats(session, window_days)
    thin_keys = {r["cluster_key"] for r in primary_rows if r["comp_count"] < min_size}

    thin_rows: dict[str, dict] = {}
    if thin_keys:
        wide_rows = await _fetch_cluster_stats(session, thin_window_days)
        thin_rows = {r["cluster_key"]: r for r in wide_rows if r["cluster_key"] in thin_keys}

    merged: dict[str, dict] = {}
    for row in primary_rows:
        key = row["cluster_key"]
        if key in thin_rows:
            wide = thin_rows[key]
            wide["window_days"] = thin_window_days
            wide["insufficient_data"] = wide["comp_count"] < min_size
            merged[key] = wide
        else:
            row["window_days"] = window_days
            row["insufficient_data"] = row["comp_count"] < min_size
            merged[key] = row

    for key, row in thin_rows.items():
        if key not in merged:
            row["window_days"] = thin_window_days
            row["insufficient_data"] = row["comp_count"] < min_size
            merged[key] = row

    if not merged:
        logger.info("comp_clusters: no comps found; nothing to compute.")
        return {"total": 0, "updated": 0, "insufficient_data": 0}

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
    Query comps table for price band stats per make/model/spec cluster.

    Uses server-side percentile_cont and groups on either:
      - generation for Porsche-style clusters
      - exact year_bucket when generation is unavailable
    """
    cutoff = date.today() - timedelta(days=window_days)
    year_bucket = case((Comp.generation.is_(None), Comp.year), else_=None).label("year_bucket")

    stmt = (
        select(
            Comp.make,
            Comp.model,
            Comp.generation,
            year_bucket,
            Comp.body_style,
            Comp.transmission,
            Comp.currency,
            func.count().label("comp_count"),
            func.percentile_cont(0.5).within_group(Comp.sale_price).label("median_price"),
            func.percentile_cont(0.25).within_group(Comp.sale_price).label("p25_price"),
            func.percentile_cont(0.75).within_group(Comp.sale_price).label("p75_price"),
            func.min(Comp.sale_price).label("min_price"),
            func.max(Comp.sale_price).label("max_price"),
            func.avg(Comp.confidence_score).label("avg_confidence"),
        )
        .where(
            Comp.sale_price.is_not(None),
            Comp.make.is_not(None),
            Comp.model.is_not(None),
            Comp.body_style.is_not(None),
            Comp.transmission.is_not(None),
            Comp.sale_date >= cutoff,
        )
        .group_by(
            Comp.make,
            Comp.model,
            Comp.generation,
            year_bucket,
            Comp.body_style,
            Comp.transmission,
            Comp.currency,
        )
    )

    result = await session.execute(stmt)
    rows = []
    for row in result.mappings():
        make_val = str(row["make"]).strip()
        model_val = str(row["model"]).strip()
        generation = row["generation"]
        year_value = row["year_bucket"]
        body_style = row["body_style"]
        transmission = row["transmission"]
        currency = row["currency"]

        rows.append(
            {
                "cluster_key": cluster_key_for(
                    make_val,
                    model_val,
                    _enum_value(body_style) or "",
                    _enum_value(transmission) or "",
                    currency=_enum_value(currency) or "USD",
                    generation=_enum_value(generation),
                    year_bucket=year_value,
                ),
                "make": make_val,
                "model": model_val,
                "generation": generation,
                "year_bucket": year_value,
                "body_style": body_style,
                "transmission": transmission,
                "currency": currency,
                "comp_count": row["comp_count"],
                "median_price": _to_float(row["median_price"]),
                "p25_price": _to_float(row["p25_price"]),
                "p75_price": _to_float(row["p75_price"]),
                "min_price": _to_float(row["min_price"]),
                "max_price": _to_float(row["max_price"]),
                "avg_confidence": _to_float(row["avg_confidence"]),
            }
        )
    return rows


async def _upsert_cluster(session: AsyncSession, row: dict) -> None:
    """INSERT ... ON CONFLICT (cluster_key) DO UPDATE for a single cluster row."""
    values = {
        "cluster_key": row["cluster_key"],
        "make": row["make"],
        "model": row["model"],
        "generation": row["generation"],
        "year_bucket": row["year_bucket"],
        "body_style": row["body_style"],
        "transmission": row["transmission"],
        "currency": row["currency"],
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
            set_={k: values[k] for k in values if k != "cluster_key"},
        )
    )
    await session.execute(stmt)


def _to_float(val) -> Optional[float]:
    """Coerce Decimal / None from SQLAlchemy result to Optional[float]."""
    if val is None:
        return None
    return float(val)


def cluster_key_for(
    make: str,
    model: str,
    body_style: str,
    transmission: str,
    *,
    currency: str,
    generation: Optional[str] = None,
    year_bucket: Optional[int] = None,
) -> str:
    """Canonical cluster key used by the cluster builder, API, and alerts."""
    if generation is None and year_bucket is None:
        raise ValueError("cluster key requires either generation or year_bucket")

    spec_component = generation or f"y{year_bucket}"
    return ":".join(
        [
            _normalize_key_piece(make),
            _normalize_key_piece(model),
            _normalize_key_piece(spec_component),
            _normalize_key_piece(body_style),
            _normalize_key_piece(transmission),
            _normalize_key_piece(currency),
        ]
    )


def _enum_value(val) -> Optional[str]:
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


def _normalize_key_piece(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "unknown"
