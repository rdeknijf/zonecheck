from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from conftest import NOW, snapshot_of
from zonecheck.datex import parse_zone_feed
from zonecheck.main import ZoneStore, create_app, match_zones
from zonecheck.ndw_feed import FeedError
from zonecheck.rdw import RdwClient

AMSTERDAM_LEZ = "NDW11_acbf0f7f-56a6-4b36-9a66-4b6d0c69d474"


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["zones"] == 11
    assert body["feed"]["publication_time"].startswith("2026-10-31T06:00:00")


def test_zones(client):
    body = client.get("/zones").json()
    assert body["count"] == 11
    zone = next(z for z in body["zones"] if z["id"] == AMSTERDAM_LEZ)
    assert zone == {
        "id": AMSTERDAM_LEZ,
        "name": "Milieuzone Amsterdam",
        "city": "Amsterdam",
        "type": "lowEmissionZone",
        "status": "active",
        "valid_from": "2025-01-01T00:00:00Z",
        "valid_until": "2030-01-01T00:00:00Z",
        "regulation_id": zone["regulation_id"],
        "info_url": zone["info_url"],
        "record_version_time": zone["record_version_time"],
        "geojson_url": f"/zones/{AMSTERDAM_LEZ}.geojson",
    }


def test_geojson(client):
    response = client.get(f"/zones/{AMSTERDAM_LEZ}.geojson")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    body = response.json()
    assert body["type"] == "Feature"
    assert body["geometry"]["type"] == "MultiPolygon"
    assert len(body["geometry"]["coordinates"]) == 6
    lon, lat = body["geometry"]["coordinates"][0][0][0]
    assert 4.7 < lon < 5.1
    assert 52.2 < lat < 52.5
    assert body["properties"]["name"] == "Milieuzone Amsterdam"


def test_geojson_unknown_zone(client):
    assert client.get("/zones/nope.geojson").status_code == 404


def test_access_by_id_old_diesel(client):
    response = client.get(
        "/access", params={"kenteken": "27-fn-ld", "zone": AMSTERDAM_LEZ}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kenteken"] == "27FNLD"
    assert body["result"] == "not_allowed"
    [zone] = body["zones"]
    assert zone["result"] == "not_allowed"
    assert zone["zone"]["valid_from"] == "2025-01-01T00:00:00Z"
    assert zone["deciding_conditions"]
    assert all("raw_xml" in c for c in zone["deciding_conditions"])
    assert zone["rule_readable"][0] == "AccessRestriction noEntry when:"
    assert body["vehicle"]["euro_class"] == 3
    assert body["vehicle"]["age_years"] == 26
    assert body["vehicle"]["fuels"][0]["brandstof_omschrijving"] == "Diesel"
    assert body["feed"]["sha256"]
    assert "No liability" in body["disclaimer"]
    assert body["evaluated_at"] == "2026-11-01T12:00:00Z"


def test_access_by_city_returns_every_zone(client):
    body = client.get(
        "/access", params={"kenteken": "V68GJD", "zone": "amsterdam"}
    ).json()
    results = {z["zone"]["name"]: z["result"] for z in body["zones"]}
    assert results == {"Milieuzone Amsterdam": "allowed", "ZE Amsterdam": "allowed"}
    ze = next(z for z in body["zones"] if z["zone"]["name"] == "ZE Amsterdam")
    assert ze["allowed_until"] == "2027-12-31T23:00:00Z"
    assert body["result"] == "allowed"


def test_access_overall_is_the_worst_result(client):
    body = client.get(
        "/access", params={"kenteken": "27BHRX", "zone": "Utrecht"}
    ).json()
    results = {z["zone"]["name"]: z["result"] for z in body["zones"]}
    assert results == {"LEZ Utrecht": "unknown", "ZE Utrecht": "unknown"}
    assert body["result"] == "unknown"
    body = client.get(
        "/access", params={"kenteken": "27FNLD", "zone": "Utrecht"}
    ).json()
    results = {z["zone"]["name"]: z["result"] for z in body["zones"]}
    assert results == {"LEZ Utrecht": "not_allowed", "ZE Utrecht": "allowed"}
    assert body["result"] == "not_allowed"


def test_access_feed_caveat(client):
    body = client.get("/access", params={"kenteken": "G313XB", "zone": "Delft"}).json()
    [zone] = body["zones"]
    assert zone["zone"]["name"] == "LEZ Delft"
    assert zone["result"] == "not_allowed"
    assert zone["feed_caveat"].startswith(
        "The NDW feed applies this zone to every diesel vehicle"
    )
    assert "(N2, N3), not this vehicle's category M1" in zone["feed_caveat"]
    body = client.get(
        "/access", params={"kenteken": "G313XB", "zone": "Amsterdam"}
    ).json()
    assert [z["feed_caveat"] for z in body["zones"]] == [None, None]


def test_access_by_zone_name(client):
    body = client.get(
        "/access", params={"kenteken": "GZS88K", "zone": "ze rotterdam"}
    ).json()
    assert [z["zone"]["name"] for z in body["zones"]] == ["ZE Rotterdam"]
    assert body["result"] == "allowed"


def test_access_missing_vehicle_is_unknown(client):
    body = client.get(
        "/access", params={"kenteken": "ZZ-999-Z", "zone": "Amsterdam"}
    ).json()
    assert body["result"] == "unknown"
    assert body["vehicle"] == {
        "kenteken": "ZZ999Z",
        "found": False,
        "voertuigsoort": None,
        "merk": None,
        "handelsbenaming": None,
        "europese_voertuigcategorie": None,
        "datum_eerste_toelating": None,
        "inrichting": None,
        "fuels": [],
        "euro_class": None,
        "euro_class_basis": None,
        "age_years": None,
    }


def test_access_unknown_zone(client):
    response = client.get("/access", params={"kenteken": "G313XB", "zone": "Atlantis"})
    assert response.status_code == 404
    assert "Amsterdam" in response.json()["cities"]


def test_access_invalid_kenteken(client):
    response = client.get("/access", params={"kenteken": "!!", "zone": "Amsterdam"})
    assert response.status_code == 422


def test_access_rdw_down(zones_xml):
    store = ZoneStore(lambda: snapshot_of(zones_xml))
    rdw = RdwClient(
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    )
    client = TestClient(create_app(store=store, rdw=rdw, clock=lambda: NOW))
    response = client.get("/access", params={"kenteken": "G313XB", "zone": "Amsterdam"})
    assert response.status_code == 502


def test_feed_unavailable(zones_xml):
    def fail():
        raise FeedError("no feed")

    store = ZoneStore(fail)
    rdw = RdwClient(
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    )
    client = TestClient(create_app(store=store, rdw=rdw))
    assert client.get("/health").status_code == 503
    assert client.get("/health").json()["status"] == "unavailable"
    assert client.get("/zones").status_code == 503


def test_store_refreshes_after_ttl(zones_xml):
    calls = []
    clock = [datetime(2026, 11, 1, tzinfo=UTC)]

    def fetcher():
        calls.append(1)
        return snapshot_of(zones_xml)

    store = ZoneStore(fetcher, ttl=timedelta(hours=1), clock=lambda: clock[0])
    store.get()
    store.get()
    assert len(calls) == 1
    clock[0] += timedelta(hours=2)
    store.get()
    assert len(calls) == 2


def test_match_zones_alias_den_haag(zones_xml):
    xml = zones_xml.decode().replace(
        '<com:value lang="nl">Venlo</com:value>',
        '<com:value lang="nl">\'s-Gravenhage</com:value>',
    )
    zones = parse_zone_feed(xml.encode()).zones
    assert [z.name for z in match_zones(zones, "Den Haag")] == ["Identificatie146223"]
    assert [z.name for z in match_zones(zones, "ROTTERDAM")] == [
        "LEZ Rotterdam Maasvlakte",
        "ZE Rotterdam",
    ]


def test_front_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Can this vehicle enter the zone?" in response.text
    assert 'fetch("/zones")' in response.text or "fetch('/zones')" in response.text
