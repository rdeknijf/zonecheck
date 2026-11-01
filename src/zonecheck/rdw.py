"""Read vehicle facts from RDW open data (opendata.rdw.nl, Socrata).

Two datasets give the facts that the emission-zone rules test:

- ``m9d7-ebf2`` (Gekentekende voertuigen): voertuigsoort,
  europese_voertuigcategorie, datum_eerste_toelating, inrichting.
- ``8ys7-d773`` (brandstof): one row per fuel with brandstof_omschrijving,
  emissiecode_omschrijving and uitlaatemissieniveau.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import httpx

RDW_BASE = "https://opendata.rdw.nl/resource"
VEHICLE_DATASET = "m9d7-ebf2"
FUEL_DATASET = "8ys7-d773"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_KENTEKEN = re.compile(r"^[A-Z0-9]{1,8}$")


class InvalidKentekenError(ValueError):
    """The input is not a possible Dutch registration number."""


class RdwError(RuntimeError):
    """RDW did not answer, or answered with something unexpected."""


def normalise_kenteken(value: str) -> str:
    """Strip dashes, spaces and dots, then uppercase: ``ab-12 cd`` -> ``AB12CD``."""
    cleaned = re.sub(r"[\s\-.]", "", value).upper()
    if not _KENTEKEN.fullmatch(cleaned):
        raise InvalidKentekenError(f"not a registration number: {value!r}")
    return cleaned


@dataclass(frozen=True)
class Fuel:
    brandstof_omschrijving: str | None
    emissiecode_omschrijving: str | None
    uitlaatemissieniveau: str | None


@dataclass(frozen=True)
class Vehicle:
    kenteken: str
    voertuigsoort: str | None
    europese_voertuigcategorie: str | None
    datum_eerste_toelating: date | None
    inrichting: str | None
    merk: str | None
    handelsbenaming: str | None
    fuels: tuple[Fuel, ...]


def _parse_date(value: str | None) -> date | None:
    if not value or not re.fullmatch(r"\d{8}", value):
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def vehicle_from_rows(
    kenteken: str, vehicle_rows: list[dict], fuel_rows: list[dict]
) -> Vehicle | None:
    """Build a Vehicle from the two RDW answers. None when RDW has no vehicle."""
    if len(vehicle_rows) != 1:
        return None
    row = vehicle_rows[0]
    fuels = tuple(
        Fuel(
            brandstof_omschrijving=f.get("brandstof_omschrijving"),
            emissiecode_omschrijving=f.get("emissiecode_omschrijving"),
            uitlaatemissieniveau=f.get("uitlaatemissieniveau"),
        )
        for f in sorted(fuel_rows, key=lambda f: str(f.get("brandstof_volgnummer")))
    )
    return Vehicle(
        kenteken=kenteken,
        voertuigsoort=row.get("voertuigsoort"),
        europese_voertuigcategorie=row.get("europese_voertuigcategorie"),
        datum_eerste_toelating=_parse_date(row.get("datum_eerste_toelating")),
        inrichting=row.get("inrichting"),
        merk=row.get("merk"),
        handelsbenaming=row.get("handelsbenaming"),
        fuels=fuels,
    )


class RdwClient:
    def __init__(
        self, client: httpx.Client | None = None, base: str = RDW_BASE
    ) -> None:
        self._client = client or httpx.Client(timeout=_TIMEOUT)
        self._base = base

    def _rows(self, dataset: str, kenteken: str) -> list[dict]:
        try:
            response = self._client.get(
                f"{self._base}/{dataset}.json", params={"kenteken": kenteken}
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RdwError(f"RDW {dataset} lookup failed: {exc}") from exc
        if not isinstance(rows, list):
            raise RdwError(f"RDW {dataset} returned {type(rows).__name__}, not a list")
        return rows

    def lookup(self, kenteken: str) -> Vehicle | None:
        vehicle_rows = self._rows(VEHICLE_DATASET, kenteken)
        if not vehicle_rows:
            return None
        return vehicle_from_rows(
            kenteken, vehicle_rows, self._rows(FUEL_DATASET, kenteken)
        )

    def close(self) -> None:
        self._client.close()
