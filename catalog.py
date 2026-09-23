"Load the hackathon catalog without altering the supplied profiles."

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


DATA_PATH = Path(__file__).parent / "data" / "contractors.csv"
CALENDAR_START = "2026-09-23"
CALENDAR_END = "2026-12-31"


def _items(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split("|") if part.strip())


@dataclass(frozen=True)
class Contractor:
    id: str
    name: str
    categories: frozenset[str]
    city: str
    price: int
    formats: frozenset[str]
    languages: frozenset[str]
    max_hours: int | None
    busy_dates: frozenset[str]
    description: str
    synthetic: bool
    city_imputed: bool
    price_imputed: bool


def load_catalog(path: Path = DATA_PATH) -> tuple[Contractor, ...]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        records = tuple(csv.DictReader(source))
    contractors = tuple(
        Contractor(
            id=row["id"],
            name=row["anon_name"],
            categories=_items(row["categories"]),
            city=row["city"].strip(),
            price=int(row["price_from_kzt"]),
            formats=_items(row["event_formats"]),
            languages=_items(row["languages"]),
            max_hours=int(row["max_hours"]) if row["max_hours"] else None,
            busy_dates=_items(row["busy_dates"]),
            description=row["description"].strip(),
            synthetic=row["synthetic"].lower() == "true",
            city_imputed=row["city_imputed"].lower() == "true",
            price_imputed=row["price_imputed"].lower() == "true",
        )
        for row in records
    )
    if len({item.id for item in contractors}) != len(contractors):
        raise ValueError("Duplicate contractor ID in catalog")
    return contractors


CATALOG = load_catalog()


def options() -> dict:
    return {
        "cities": sorted({item.city for item in CATALOG}),
        "categories": sorted({category for item in CATALOG for category in item.categories}),
        "formats": sorted({fmt for item in CATALOG for fmt in item.formats}),
        "languages": sorted({lang for item in CATALOG for lang in item.languages}),
        "calendar_start": CALENDAR_START,
        "calendar_end": CALENDAR_END,
        "profiles": len(CATALOG),
    }
