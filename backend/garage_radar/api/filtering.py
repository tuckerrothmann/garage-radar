"""
Helpers for multi-value query parameters.

The frontend sends repeated query params for multi-select filters, but we also
accept comma-separated values so URLs remain easy to edit by hand.
"""
from __future__ import annotations

from enum import Enum
from typing import TypeVar

from fastapi import HTTPException

TEnum = TypeVar("TEnum", bound=Enum)


def split_multi_values(values: list[str] | None) -> list[str]:
    """Flatten repeated/comma-separated query values into a clean list."""
    if not values:
        return []

    flattened: list[str] = []
    seen: set[str] = set()

    for value in values:
        for piece in value.split(","):
            cleaned = " ".join(piece.strip().split())
            if not cleaned:
                continue
            dedupe_key = cleaned.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            flattened.append(cleaned)

    return flattened


def parse_int_values(values: list[str] | None, field_name: str) -> list[int]:
    parsed: list[int] = []
    for value in split_multi_values(values):
        try:
            parsed.append(int(value))
        except ValueError as exc:
            raise HTTPException(400, f"Invalid {field_name} '{value}'") from exc
    return parsed


def parse_enum_values(
    enum_cls: type[TEnum],
    values: list[str] | None,
    field_name: str,
) -> list[TEnum]:
    parsed: list[TEnum] = []
    for value in split_multi_values(values):
        last_error: ValueError | None = None
        for candidate in (value, value.lower(), value.upper()):
            try:
                parsed.append(enum_cls(candidate))
                break
            except ValueError as exc:
                last_error = exc
        else:
            raise HTTPException(400, f"Invalid {field_name} '{value}'") from last_error
    return parsed
