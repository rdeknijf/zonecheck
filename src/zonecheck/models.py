"""Response models for the HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class FeedInfo(BaseModel):
    url: str
    publication_time: datetime | None
    table_version_time: datetime | None
    fetched_at: datetime
    checked_at: datetime
    last_modified: str | None
    sha256: str
    stale_reason: str | None = None


class ZoneSummary(BaseModel):
    id: str
    name: str
    city: str | None
    type: str | None
    status: str | None
    valid_from: datetime | None
    valid_until: datetime | None
    regulation_id: str | None
    info_url: str | None
    record_version_time: datetime | None
    geojson_url: str | None


class ZoneList(BaseModel):
    feed: FeedInfo
    count: int
    zones: list[ZoneSummary]


class FuelFacts(BaseModel):
    brandstof_omschrijving: str | None
    emissiecode_omschrijving: str | None
    uitlaatemissieniveau: str | None


class VehicleFacts(BaseModel):
    kenteken: str
    found: bool
    voertuigsoort: str | None = None
    merk: str | None = None
    handelsbenaming: str | None = None
    europese_voertuigcategorie: str | None = None
    datum_eerste_toelating: date | None = None
    inrichting: str | None = None
    fuels: list[FuelFacts] = []
    euro_class: int | None = None
    euro_class_basis: str | None = None
    age_years: int | None = None


class DecidingCondition(BaseModel):
    condition_id: str | None
    readable: str
    value: bool | None
    vehicle_fact: str | None
    in_exemption: bool
    raw_xml: str


class ZoneAccess(BaseModel):
    zone: ZoneSummary
    result: Literal["allowed", "not_allowed", "unknown"]
    reason: str
    allowed_until: datetime | None
    deciding_conditions: list[DecidingCondition]
    rule_readable: list[str]


class AccessResponse(BaseModel):
    kenteken: str
    zone_query: str
    result: Literal["allowed", "not_allowed", "unknown"]
    evaluated_at: datetime
    zones: list[ZoneAccess]
    vehicle: VehicleFacts
    feed: FeedInfo
    sources: list[str]
    disclaimer: str


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    zones: int | None = None
    feed: FeedInfo | None = None
    detail: str | None = None
