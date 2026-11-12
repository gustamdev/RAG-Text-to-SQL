from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    # O Mongo devolve datetimes ingênuos (já em UTC): reanexa o fuso para comparar/serializar.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def iso(value: datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")
