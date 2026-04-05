"""
Alert engine — detects pricing and availability signals on active listings.

Alert types generated here:
  underpriced            — asking price is >= 15% below cluster median
  price_drop             — asking price dropped >= 5% since last recorded price
  new_listing            — listing appeared within the last 24 hours
  relist                 — a previously ended/sold listing is active again
  insufficient_data_warning — listing has an asking price but the comp cluster
                              has too few comps to validate it

Deduplication: we never create a second open alert of the same (alert_type,
listing_id) pair. If one already exists with status='open' or 'read', we skip.
Dismissed alerts do not block re-alerting (the user dismissed it deliberately).

All alert writes are batched into the caller's session — the caller is responsible
for commit().
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.config import get_settings
from garage_radar.db.models import Alert, AlertSeverityEnum, AlertStatusEnum, AlertTypeEnum

logger = logging.getLogger(__name__)

_NEW_LISTING_WINDOW_HOURS = 24


# ── Public entry point ────────────────────────────────────────────────────────

async def run_alert_engine(session: AsyncSession) -> dict:
    """
    Scan active listings and emit alerts.

    Returns stats dict: {checked, created, skipped_dedup}.
    """
    settings = get_settings()
    underpriced_threshold = settings.underpriced_alert_threshold    # e.g. -0.15
    price_drop_threshold = settings.price_drop_alert_threshold      # e.g. 0.05

    stats = {"checked": 0, "created": 0, "skipped_dedup": 0}

    # Query the view — it already joins comp_clusters and computes delta_pct
    rows = await _fetch_active_with_delta(session)

    for row in rows:
        stats["checked"] += 1
        listing_id = row["id"]

        # ── new_listing ───────────────────────────────────────────────────────
        if _is_new_listing(row):
            asking_label = _format_money(row.get("asking_price"), row.get("currency"))
            created = await _maybe_create_alert(
                session,
                listing_id=listing_id,
                alert_type=AlertTypeEnum.new_listing,
                severity=AlertSeverityEnum.info,
                reason=(
                    f"New listing: {row.get('source_url', '')} — asking {asking_label}"
                    if row.get("asking_price") else
                    f"New listing: {row.get('source_url', '')}"
                ),
                delta_pct=None,
            )
            stats["created" if created else "skipped_dedup"] += 1

        # ── relist ────────────────────────────────────────────────────────────
        if row.get("listing_status") == "relist":
            created = await _maybe_create_alert(
                session,
                listing_id=listing_id,
                alert_type=AlertTypeEnum.relist,
                severity=AlertSeverityEnum.info,
                reason=f"Relist detected: {row.get('source_url', '')}",
                delta_pct=None,
            )
            stats["created" if created else "skipped_dedup"] += 1

        # ── underpriced / insufficient_data_warning ───────────────────────────
        delta_pct = row.get("delta_pct")
        cluster_insufficient = row.get("cluster_insufficient_data")

        if row.get("asking_price") and cluster_insufficient:
            asking_label = _format_money(row.get("asking_price"), row.get("currency"))
            created = await _maybe_create_alert(
                session,
                listing_id=listing_id,
                alert_type=AlertTypeEnum.insufficient_data_warning,
                severity=AlertSeverityEnum.info,
                reason=(
                    f"Cluster has too few comps to validate price of "
                    f"{asking_label} — "
                    f"{row.get('source_url', '')}"
                ),
                delta_pct=None,
            )
            stats["created" if created else "skipped_dedup"] += 1

        elif delta_pct is not None and float(delta_pct) <= underpriced_threshold * 100:
            # delta_pct from the view is already a percentage (e.g. -22.5)
            pct_val = float(delta_pct)
            severity = _underpriced_severity(pct_val)
            asking_label = _format_money(row.get("asking_price", 0), row.get("currency"))
            median_label = _format_money(row.get("cluster_median", 0), row.get("currency"))
            created = await _maybe_create_alert(
                session,
                listing_id=listing_id,
                alert_type=AlertTypeEnum.underpriced,
                severity=severity,
                reason=(
                    f"Asking {asking_label} is "
                    f"{abs(pct_val):.1f}% below cluster median "
                    f"{median_label} — "
                    f"{row.get('source_url', '')}"
                ),
                delta_pct=pct_val,
            )
            stats["created" if created else "skipped_dedup"] += 1

        # ── price_drop ────────────────────────────────────────────────────────
        drop = _detect_price_drop(row, price_drop_threshold)
        if drop is not None:
            drop_pct, old_price, new_price = drop
            old_label = _format_money(old_price, row.get("currency"))
            new_label = _format_money(new_price, row.get("currency"))
            created = await _maybe_create_alert(
                session,
                listing_id=listing_id,
                alert_type=AlertTypeEnum.price_drop,
                severity=AlertSeverityEnum.watch,
                reason=(
                    f"Price dropped {drop_pct:.1f}% from "
                    f"{old_label} → {new_label} — "
                    f"{row.get('source_url', '')}"
                ),
                delta_pct=-drop_pct,
            )
            stats["created" if created else "skipped_dedup"] += 1

    logger.info(
        "alert_engine: checked %d listings, created %d alerts, skipped %d (dedup).",
        stats["checked"], stats["created"], stats["skipped_dedup"],
    )
    return stats


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_active_with_delta(session: AsyncSession) -> list[dict]:
    """Query the active_listings_with_delta view. Returns list of row dicts."""
    result = await session.execute(
        text("""
            SELECT
                id,
                source_url,
                listing_status,
                asking_price,
                currency,
                delta_pct,
                cluster_median,
                cluster_insufficient_data,
                price_history,
                created_at
            FROM active_listings_with_delta
        """)
    )
    return [dict(row._mapping) for row in result]


async def _maybe_create_alert(
    session: AsyncSession,
    listing_id: uuid.UUID,
    alert_type: AlertTypeEnum,
    severity: AlertSeverityEnum,
    reason: str,
    delta_pct: Optional[float],
) -> bool:
    """
    Create alert if no open/read alert of the same (type, listing_id) exists.
    Returns True if created, False if skipped due to dedup.
    """
    # Check for existing non-dismissed alert
    existing = await session.scalar(
        select(Alert).where(
            Alert.listing_id == listing_id,
            Alert.alert_type == alert_type,
            Alert.status.in_([AlertStatusEnum.open, AlertStatusEnum.read]),
        )
    )
    if existing:
        return False

    alert = Alert(
        id=uuid.uuid4(),
        alert_type=alert_type,
        listing_id=listing_id,
        reason=reason,
        delta_pct=delta_pct,
        severity=severity,
        status=AlertStatusEnum.open,
        triggered_at=datetime.now(timezone.utc),
    )
    session.add(alert)
    return True


# ── Signal detection helpers ──────────────────────────────────────────────────

def _is_new_listing(row: dict) -> bool:
    created_at = row.get("created_at")
    if created_at is None:
        return False
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            return False
    # Normalise to UTC-aware for comparison
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_NEW_LISTING_WINDOW_HOURS)
    return created_at >= cutoff


def _format_money(amount: Optional[float], currency: Optional[str]) -> str:
    if amount is None:
        return "unknown price"
    code = currency or "USD"
    return f"{code} {amount:,.0f}"


def _detect_price_drop(
    row: dict, threshold: float
) -> Optional[tuple[float, float, float]]:
    """
    Returns (drop_pct, old_price, new_price) if a significant drop is detected,
    else None.

    price_history is a JSONB list of {"price": float, "ts": str} entries.
    We compare current asking_price against the most recent history entry.
    A drop qualifies if (old - new) / old >= threshold.
    """
    asking_price = row.get("asking_price")
    price_history = row.get("price_history")

    if not asking_price or not price_history:
        return None

    # price_history may come back as a list (already parsed by asyncpg) or JSON string
    if isinstance(price_history, str):
        import json
        try:
            price_history = json.loads(price_history)
        except (ValueError, TypeError):
            return None

    if not isinstance(price_history, list) or not price_history:
        return None

    # Most recent historical price
    last_entry = price_history[-1]
    old_price = last_entry.get("price") if isinstance(last_entry, dict) else None
    if old_price is None or old_price <= 0:
        return None

    new_price = float(asking_price)
    old_price = float(old_price)
    if old_price <= new_price:
        return None

    drop_pct = (old_price - new_price) / old_price
    if drop_pct >= threshold:
        return drop_pct * 100, old_price, new_price

    return None


def _underpriced_severity(delta_pct: float) -> AlertSeverityEnum:
    """
    Map underpriced delta to severity tier.

    -15% to -25%: watch — interesting but could be condition/spec driven
    < -25%:       act   — material discount, high signal
    """
    if delta_pct <= -25.0:
        return AlertSeverityEnum.act
    return AlertSeverityEnum.watch
