from __future__ import annotations

from datetime import date

import httpx
import pytest

from conftest import rdw_transport
from ndw_zones.rdw import (
    InvalidKentekenError,
    RdwClient,
    RdwError,
    normalise_kenteken,
    vehicle_from_rows,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ab-12-cd", "AB12CD"),
        (" g-313-xb ", "G313XB"),
        ("G 313 XB", "G313XB"),
        ("v.68.gjd", "V68GJD"),
        ("1vzx50", "1VZX50"),
    ],
)
def test_normalise_kenteken(raw, expected):
    assert normalise_kenteken(raw) == expected


@pytest.mark.parametrize("raw", ["", "---", "AB12CD'; drop", "ÄB12CD", "ABCDEFGHIJ"])
def test_invalid_kenteken(raw):
    with pytest.raises(InvalidKentekenError):
        normalise_kenteken(raw)


def test_client_reads_both_datasets():
    calls: list[str] = []
    client = RdwClient(httpx.Client(transport=rdw_transport(calls)))
    vehicle = client.lookup("GZR60P")
    assert vehicle is not None
    assert vehicle.europese_voertuigcategorie == "M1"
    assert vehicle.datum_eerste_toelating == date(2023, 3, 3)
    assert [f.brandstof_omschrijving for f in vehicle.fuels] == [
        "Benzine",
        "Elektriciteit",
    ]
    assert calls == [
        "/resource/m9d7-ebf2.json?GZR60P",
        "/resource/8ys7-d773.json?GZR60P",
    ]
    client.close()


def test_missing_vehicle_skips_fuel_lookup():
    calls: list[str] = []
    client = RdwClient(httpx.Client(transport=rdw_transport(calls)))
    assert client.lookup("ZZ999Z") is None
    assert calls == ["/resource/m9d7-ebf2.json?ZZ999Z"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"error": True}),
    ],
)
def test_rdw_errors(response):
    client = RdwClient(httpx.Client(transport=httpx.MockTransport(lambda _: response)))
    with pytest.raises(RdwError):
        client.lookup("G313XB")


def test_vehicle_from_rows_edge_cases():
    assert vehicle_from_rows("X", [], []) is None
    assert vehicle_from_rows("X", [{}, {}], []) is None
    vehicle = vehicle_from_rows("X", [{"datum_eerste_toelating": "20231399"}], [])
    assert vehicle is not None
    assert vehicle.datum_eerste_toelating is None
    assert vehicle.fuels == ()
