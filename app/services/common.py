from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def hours_between(a: datetime, b: datetime) -> float:
    return round((a - b).total_seconds() / 3600.0, 2)
