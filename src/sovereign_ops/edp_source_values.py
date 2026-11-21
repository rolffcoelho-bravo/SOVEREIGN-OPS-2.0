"""Shared value rules for the pinned EDP source profile and telemetry reader."""

import math
from datetime import UTC, datetime


def scada_timestamp(value: object, *, require_offset: bool = True) -> datetime:
    """Parse a source timestamp without inventing a timezone for naive values."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("SCADA timestamp must be an ISO datetime or Excel datetime")
    if value.utcoffset() is None:
        if require_offset:
            raise ValueError("SCADA timestamp requires an explicit UTC offset")
        return value
    return value.astimezone(UTC)


def scada_value(value: object) -> float | None:
    """Allow blank measurements and finite numeric cells, rejecting coercion."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError("SCADA measurement must be a finite numeric cell or blank")
    return float(value)
