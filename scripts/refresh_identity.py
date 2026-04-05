#!/usr/bin/env python3
"""Refresh normalized make/model identity for existing listings and comps."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select

from garage_radar.db import get_session_factory
from garage_radar.db.models import Comp, Listing, SourceEnum
from garage_radar.normalize.vehicle_identity import extract_vehicle_identity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=[member.value for member in SourceEnum])
    parser.add_argument("--make")
    parser.add_argument("--model")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-comps", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _title_for_row(row) -> str:
    title_raw = getattr(row, "title_raw", None)
    if title_raw:
        return title_raw

    parts = [row.year, row.make, row.model]
    for attr in ("trim", "engine_variant"):
        value = getattr(row, attr, None)
        if value:
            parts.append(value)
    return " ".join(str(part) for part in parts if part)


def _source_value(value) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


async def _refresh_table(session, model_cls, args: argparse.Namespace) -> int:
    stmt = select(model_cls)
    if args.source:
        stmt = stmt.where(model_cls.source == SourceEnum(args.source))
    if args.make:
        stmt = stmt.where(func.lower(model_cls.make) == args.make.strip().lower())
    if args.model:
        stmt = stmt.where(func.lower(model_cls.model) == args.model.strip().lower())

    order_column = getattr(model_cls, "updated_at", None) or model_cls.created_at
    stmt = stmt.order_by(order_column.desc())
    if args.limit:
        stmt = stmt.limit(args.limit)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    changed = 0
    for row in rows:
        title = _title_for_row(row)
        new_make, new_model = extract_vehicle_identity(
            title,
            make_raw=row.make,
            model_raw=row.model,
        )
        if new_make == row.make and new_model == row.model:
            continue

        print(
            f"{model_cls.__name__} {row.id}: "
            f"{row.make!r}/{row.model!r} -> {new_make!r}/{new_model!r} | {title}"
        )
        changed += 1

        if args.dry_run:
            continue

        row.make = new_make
        row.model = new_model
        if hasattr(row, "updated_at"):
            row.updated_at = datetime.now(UTC)
        session.add(row)

    return changed


async def main_async(args: argparse.Namespace) -> None:
    async with get_session_factory()() as session:
        listing_changes = await _refresh_table(session, Listing, args)
        comp_changes = 0
        if args.include_comps:
            comp_changes = await _refresh_table(session, Comp, args)

        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()

    print(
        "Identity refresh complete: "
        f"{listing_changes} listing(s) changed, {comp_changes} comp(s) changed."
    )


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
