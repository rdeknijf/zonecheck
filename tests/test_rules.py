from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from zonecheck.datex import Characteristic, parse_zone_feed
from zonecheck.rdw import Fuel, Vehicle
from zonecheck.rules import (
    decide,
    euro_class,
    evaluate_characteristic,
    k_and,
    k_not,
    k_or,
    vehicle_age,
)


def _vehicle(**overrides) -> Vehicle:
    base = Vehicle(
        kenteken="XX00XX",
        voertuigsoort="Personenauto",
        europese_voertuigcategorie="M1",
        datum_eerste_toelating=date(2015, 6, 1),
        inrichting="hatchback",
        merk="TEST",
        handelsbenaming="TEST",
        fuels=(Fuel("Diesel", "6", "EURO 6 W"),),
    )
    return replace(base, **overrides)


# --- Kleene logic ----------------------------------------------------------


def test_kleene_tables():
    assert k_and([True, None]) is None
    assert k_and([False, None]) is False
    assert k_or([True, None]) is True
    assert k_or([False, None]) is None
    assert k_not(None) is None
    assert k_not(True) is False


# --- Facts -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fuels", "expected"),
    [
        ((Fuel("Diesel", "6", "EURO 6 AP"),), 6),
        ((Fuel("Diesel", "3", "EURO 3"),), 3),
        ((Fuel("Diesel", "3", None),), 3),
        ((Fuel("Diesel", None, "EURO VI D"),), 6),
        ((Fuel("Diesel", "6", "EURO VI D"),), 6),
        ((Fuel("Diesel", None, "EURO III"),), 3),
        ((Fuel("Benzine", "0", "EURO 0"),), 0),
        (
            (
                Fuel("Benzine", "6", "EURO 6 AP"),
                Fuel("Elektriciteit", "Z", "EURO 6 AP"),
            ),
            6,
        ),
        # Unknown cases: never guess a class.
        ((Fuel("Benzine", "0", None),), None),
        ((Fuel("Diesel", "5", "EURO 6 W"),), None),
        ((Fuel("Diesel", None, "EEV K"),), None),
        ((Fuel("Diesel", None, "EURO 5+"),), None),
        ((Fuel("Diesel", None, None),), None),
        ((Fuel("Elektriciteit", "Z", "AX"),), None),
        ((Fuel("Benzine", "5", None), Fuel("LPG", "4", None)), None),
        ((), None),
    ],
)
def test_euro_class(fuels, expected):
    assert euro_class(_vehicle(fuels=fuels))[0] == expected


def test_vehicle_age_counts_completed_years():
    assert vehicle_age(date(1986, 11, 2), date(2026, 11, 1)) == 39
    assert vehicle_age(date(1986, 11, 1), date(2026, 11, 1)) == 40


@pytest.mark.parametrize(
    ("characteristic", "vehicle", "expected"),
    [
        (Characteristic("fuelType", "diesel"), _vehicle(), True),
        (
            Characteristic("fuelType", "diesel"),
            _vehicle(
                fuels=(Fuel("Diesel", "6", None), Fuel("Elektriciteit", "Z", None))
            ),
            True,
        ),
        (
            Characteristic("fuelType", "battery"),
            _vehicle(fuels=(Fuel("Elektriciteit", "Z", None),)),
            True,
        ),
        (
            Characteristic("fuelType", "battery"),
            _vehicle(
                fuels=(Fuel("Benzine", "6", None), Fuel("Elektriciteit", "Z", None))
            ),
            False,
        ),
        (
            Characteristic("fuelType", "hydrogen"),
            _vehicle(
                fuels=(Fuel("Waterstof", None, None), Fuel("Elektriciteit", "Z", None))
            ),
            True,
        ),
        (
            Characteristic("fuelType", "hydrogen"),
            _vehicle(fuels=(Fuel("Waterstof", None, None), Fuel("Benzine", "6", None))),
            None,
        ),
        (Characteristic("fuelType", "diesel"), _vehicle(fuels=()), None),
        (
            Characteristic("fuelType", "diesel"),
            _vehicle(fuels=(Fuel("Kerosine", None, None),)),
            None,
        ),
        (Characteristic("fuelType", "petrol"), _vehicle(), None),
        (Characteristic("vehicleType", "anyVehicle"), _vehicle(), True),
        (Characteristic("vehicleType", "lorry"), _vehicle(), None),
        (Characteristic("euVehicleCategory", "m"), _vehicle(), True),
        (Characteristic("euVehicleCategory", "m1"), _vehicle(), True),
        (Characteristic("euVehicleCategory", "n1"), _vehicle(), False),
        (
            Characteristic("euVehicleCategory", "n1"),
            _vehicle(europese_voertuigcategorie=None),
            None,
        ),
        (
            Characteristic("euVehicleCategory", "n1"),
            _vehicle(europese_voertuigcategorie="N"),
            None,
        ),
        (
            Characteristic("euVehicleCategory", "n1"),
            _vehicle(europese_voertuigcategorie="T"),
            False,
        ),
        (Characteristic("euSpecialPurposeVehicle", "motorCaravan"), _vehicle(), False),
        (
            Characteristic("euSpecialPurposeVehicle", "motorCaravan"),
            _vehicle(inrichting="kampeerwagen"),
            None,
        ),
        (
            Characteristic("euSpecialPurposeVehicle", "armouredVehicle"),
            _vehicle(inrichting="kampeerwagen"),
            False,
        ),
        (
            Characteristic("euSpecialPurposeVehicle", "wheelChairAccessibleVehicle"),
            _vehicle(inrichting="voor rolstoelen toegankelijk voertuig"),
            None,
        ),
        (
            Characteristic("euSpecialPurposeVehicle", "mobileCrane"),
            _vehicle(inrichting="kraanwagen"),
            None,
        ),
        (
            Characteristic("euSpecialPurposeVehicle", "mobileCrane"),
            _vehicle(inrichting="Niet geregistreerd"),
            None,
        ),
        (Characteristic("ownerType", "permanentResident"), _vehicle(), None),
        (Characteristic("vehicleAge", "40", "greaterThanOrEqualTo"), _vehicle(), False),
        (
            Characteristic("vehicleAge", "40", "greaterThanOrEqualTo"),
            _vehicle(datum_eerste_toelating=date(1980, 1, 1)),
            True,
        ),
        (Characteristic("vehicleAge", "13", "lessThan"), _vehicle(), True),
        (
            Characteristic("vehicleAge", "40", "greaterThanOrEqualTo"),
            _vehicle(datum_eerste_toelating=None),
            None,
        ),
        (Characteristic("vehicleAge", "40", "about"), _vehicle(), None),
        (Characteristic("emissionClassificationEuro", "euro6"), _vehicle(), True),
        (Characteristic("emissionClassificationEuro", "euro5"), _vehicle(), False),
        (Characteristic("emissionClassificationEuro", "euro6d"), _vehicle(), None),
        (Characteristic("heightCharacteristic", "4"), _vehicle(), None),
    ],
)
def test_characteristics(characteristic, vehicle, expected, now):
    assert evaluate_characteristic(characteristic, vehicle, now)[0] is expected


# --- Decisions on the real zones and recorded RDW vehicles -------------------

CASES = [
    # (zone name, vehicle profile, expected result)
    ("Milieuzone Amsterdam", "euro6_diesel_car", "allowed"),
    ("Milieuzone Amsterdam", "old_diesel_car", "not_allowed"),
    ("Milieuzone Amsterdam", "electric_car", "allowed"),
    ("Milieuzone Amsterdam", "petrol_car", "allowed"),
    ("Milieuzone Amsterdam", "euro6_diesel_van", "allowed"),
    ("Milieuzone Amsterdam", "diesel_camper", "unknown"),
    ("Milieuzone Amsterdam", "tractor_no_emission", "unknown"),
    ("LEZ Utrecht", "old_diesel_car", "not_allowed"),
    ("LEZ Utrecht", "euro6_diesel_car", "allowed"),
    ("LEZ Rotterdam Maasvlakte", "old_diesel_car", "allowed"),
    ("ZE Utrecht", "euro6_diesel_van", "allowed"),
    ("ZE Utrecht", "euro5_diesel_van", "allowed"),
    ("ZE Utrecht", "electric_van", "allowed"),
    ("ZE Utrecht", "old_diesel_car", "allowed"),
    ("ZE Utrecht", "diesel_camper", "unknown"),
    ("ZE Amsterdam", "euro6_diesel_van", "allowed"),
    ("ZE Rotterdam", "phev_car", "allowed"),
    # Feed scope: LEZ Breda 2020-2026-06-30 has expired.
    ("LEZ Breda", "old_diesel_car", "allowed"),
    # Venlo starts 2027-01-01.
    ("Identificatie146223", "euro6_diesel_van", "allowed"),
]


@pytest.mark.parametrize(("zone", "profile", "expected"), CASES)
def test_decisions(zone, profile, expected, zone_by_name, vehicle, now):
    assert decide(zone_by_name(zone), vehicle(profile), now).result == expected


def test_not_allowed_lists_scope_and_failed_exemptions(zone_by_name, vehicle, now):
    decision = decide(
        zone_by_name("Milieuzone Amsterdam"), vehicle("old_diesel_car"), now
    )
    assert decision.reason.startswith("the restriction applies")
    readable = {leaf.readable: leaf.value for leaf in decision.deciding_conditions}
    assert readable["fuel type is diesel and any vehicle type"] is True
    assert readable["Euro emission class is Euro 5"] is False
    assert all(
        leaf.value is False
        for leaf in decision.deciding_conditions
        if leaf.in_exemption
    )
    assert any(
        "RDW brandstof: Diesel" in (leaf.fact or "")
        for leaf in decision.deciding_conditions
    )


def test_allowed_by_scope_names_the_scope_leaf(zone_by_name, vehicle, now):
    decision = decide(zone_by_name("Milieuzone Amsterdam"), vehicle("petrol_car"), now)
    assert decision.reason == "the restriction does not cover this vehicle"
    [leaf] = decision.deciding_conditions
    assert leaf.readable == "fuel type is diesel and any vehicle type"
    assert leaf.value is False
    assert "<com:fuelType>diesel</com:fuelType>" in leaf.raw


def test_time_limited_exemption_reports_end(zone_by_name, vehicle, now):
    zone = zone_by_name("ZE Utrecht")
    decision = decide(zone, vehicle("euro5_diesel_van"), now)
    assert decision.result == "allowed"
    assert decision.allowed_until == datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
    assert "exemption ends" in decision.reason
    # After the Euro 5 exemption ends, the same van may not enter.
    later = decide(zone, vehicle("euro5_diesel_van"), datetime(2027, 1, 2, tzinfo=UTC))
    assert later.result == "not_allowed"
    euro6 = decide(zone, vehicle("euro6_diesel_van"), now)
    assert euro6.allowed_until == datetime(2027, 12, 31, 23, 0, tzinfo=UTC)


def test_zone_not_in_force(zone_by_name, vehicle, now):
    decision = decide(
        zone_by_name("Identificatie146223"), vehicle("euro6_diesel_van"), now
    )
    assert (
        decision.reason == "the zone restriction is not in force at the evaluation time"
    )
    in_2027 = decide(
        zone_by_name("Identificatie146223"),
        vehicle("euro6_diesel_van"),
        datetime(2028, 6, 1, tzinfo=UTC),
    )
    assert in_2027.result == "not_allowed"


def test_unknown_lists_the_unknown_leaves(zone_by_name, vehicle, now):
    decision = decide(zone_by_name("ZE Utrecht"), vehicle("diesel_camper"), now)
    assert decision.result == "unknown"
    values = {leaf.value for leaf in decision.deciding_conditions}
    assert values == {None}
    facts = " ".join(leaf.fact or "" for leaf in decision.deciding_conditions)
    assert "kampeerwagen" in facts
    assert "no owner information" in facts


# --- Never allowed by default ----------------------------------------------------


def test_missing_rdw_record_is_unknown(feed, now):
    for zone in feed.zones:
        decision = decide(zone, None, now)
        assert decision.result == "unknown"
        assert "RDW has no vehicle record" in decision.reason


def test_vehicle_without_facts_is_never_allowed_in_force(feed, now):
    blank = Vehicle("XX00XX", None, None, None, None, None, None, ())
    for zone in feed.zones:
        in_force = zone.valid_from <= now < zone.valid_until
        result = decide(zone, blank, now).result
        assert result == ("unknown" if in_force else "allowed"), zone.name


def test_ambiguous_category_is_unknown(zone_by_name, vehicle, now):
    van = vehicle("euro6_diesel_van")
    assert van is not None
    vague = replace(van, europese_voertuigcategorie="N")
    assert decide(zone_by_name("ZE Utrecht"), vague, now).result == "unknown"


def test_unencodable_exemption_never_yields_allowed(zones_xml, vehicle, now):
    """Break the exemption the Euro 6 diesel car relies on in Amsterdam."""
    text = zones_xml.decode()
    marker = "NDW11_acbf0f7f-56a6-4b36-9a66-4b6d0c69d474"
    start = text.index(marker)
    euro6 = text.index("<com:emissionClassificationEuro>euro6<", start)
    broken = (
        text[:euro6]
        + "<com:emissionClassificationEuro>euro6d<"
        + text[euro6 + len("<com:emissionClassificationEuro>euro6<") :]
    )
    feed = parse_zone_feed(broken.encode())
    zone = next(z for z in feed.zones if z.id == marker)
    assert decide(zone, vehicle("euro6_diesel_car"), now).result == "unknown"


def test_unsupported_regulation_type_is_unknown(zones_xml, vehicle, now):
    broken = zones_xml.decode().replace(
        "<tro:accessRestrictionType>noEntry<",
        "<tro:accessRestrictionType>noThroughTraffic<",
    )
    feed = parse_zone_feed(broken.encode())
    for zone in feed.zones:
        assert decide(zone, vehicle("petrol_car"), now).result == "unknown"


def test_inactive_zone_is_unknown(zone_by_name, vehicle, now):
    zone = replace(zone_by_name("ZE Utrecht"), status="inactive")
    assert decide(zone, vehicle("petrol_car"), now).result == "unknown"
