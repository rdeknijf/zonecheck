from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ndw_zones.datex import ZoneFeed, parse_zone_feed
from ndw_zones.main import ZoneStore, create_app
from ndw_zones.ndw_feed import FeedSnapshot
from ndw_zones.rdw import RdwClient, Vehicle, vehicle_from_rows

FIXTURES = Path(__file__).parent / "fixtures"
ZONES_XML = FIXTURES / "emissiezones-trimmed.xml"
RDW_DIR = FIXTURES / "rdw"
# Fixed evaluation time: before the Euro 5 van exemption ends (2026-12-31).
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

# Recorded with live RDW calls on 2026-11-01.
PLATES = {
    "euro6_diesel_car": "G313XB",  # Mercedes C 200 D, M1, EURO 6 AP, 2020
    "old_diesel_car": "27FNLD",  # VW Golf, M1, EURO 3, 2000
    "electric_car": "GZS88K",  # Tesla Model 3, M1, Elektriciteit
    "euro6_diesel_van": "V68GJD",  # Mercedes V-Klasse, N1, EURO 6 DG, 2020
    "euro5_diesel_van": "1VZX50",  # N1, EURO 5 L, 2013
    "petrol_car": "2XNN77",  # Suzuki SX4, M1, Benzine EURO 6 W, 2014
    "diesel_camper": "27BHRX",  # Dethleffs, N1 kampeerwagen, Diesel code 3, 2002
    "phev_car": "GZR60P",  # M1, Benzine + Elektriciteit, EURO 6 AP
    "electric_van": "V53DKN",  # Peugeot e-Partner, N1, Elektriciteit
    "tractor_no_emission": "0003GV",  # Fendt, category T, Diesel, no code
    "missing": "ZZ999Z",  # RDW returns []
}


def rdw_rows(kenteken: str, kind: str) -> list[dict]:
    path = RDW_DIR / f"{kenteken}.{kind}.json"
    return json.loads(path.read_text()) if path.exists() else []


def load_vehicle(kenteken: str) -> Vehicle | None:
    return vehicle_from_rows(
        kenteken, rdw_rows(kenteken, "vehicle"), rdw_rows(kenteken, "fuel")
    )


@pytest.fixture(scope="session")
def zones_xml() -> bytes:
    return ZONES_XML.read_bytes()


@pytest.fixture(scope="session")
def feed(zones_xml: bytes) -> ZoneFeed:
    return parse_zone_feed(zones_xml)


@pytest.fixture
def zone_by_name(feed: ZoneFeed):
    def find(name: str):
        return next(z for z in feed.zones if z.name == name)

    return find


def rdw_transport(calls: list[str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        kenteken = request.url.params["kenteken"]
        if calls is not None:
            calls.append(f"{request.url.path}?{kenteken}")
        kind = "vehicle" if "m9d7-ebf2" in request.url.path else "fuel"
        return httpx.Response(200, json=rdw_rows(kenteken, kind))

    return httpx.MockTransport(handler)


def snapshot_of(content: bytes) -> FeedSnapshot:
    raw = gzip.compress(content)
    return FeedSnapshot(
        url="https://opendata.ndw.nu/emissiezones.xml.gz",
        content=content,
        sha256=hashlib.sha256(raw).hexdigest(),
        fetched_at=NOW,
        checked_at=NOW,
        last_modified="Sun, 01 Nov 2026 05:10:10 GMT",
        etag='"fixture"',
    )


@pytest.fixture
def client(zones_xml: bytes) -> TestClient:
    store = ZoneStore(lambda: snapshot_of(zones_xml), clock=lambda: NOW)
    rdw = RdwClient(httpx.Client(transport=rdw_transport()))
    return TestClient(create_app(store=store, rdw=rdw, clock=lambda: NOW))


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def vehicle():
    """Return the recorded RDW vehicle for a profile name from PLATES."""

    def get(profile: str) -> Vehicle | None:
        return load_vehicle(PLATES[profile])

    return get


@pytest.fixture
def plates() -> dict[str, str]:
    return PLATES
