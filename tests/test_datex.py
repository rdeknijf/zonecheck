from __future__ import annotations

from datetime import UTC, datetime

import pytest

from zonecheck.datex import (
    ConditionSet,
    FeedFormatError,
    LocationCondition,
    Unsupported,
    ValidityCondition,
    VehicleCondition,
    parse_zone_feed,
)


def _leaves(condition):
    if isinstance(condition, ConditionSet):
        for child in condition.children:
            yield from _leaves(child)
    else:
        yield condition


def test_parser_reads_real_feed_header_and_zones(feed):
    assert feed.publication_time == datetime(2026, 10, 31, 6, 0, 0, 3072, tzinfo=UTC)
    assert feed.table_version_time is not None
    names = {z.name for z in feed.zones}
    assert names == {
        "ZES Maastricht",
        "LEZ Breda",
        "LEZ Rotterdam Maasvlakte",
        "LEZ Utrecht",
        "Identificatie146223",
        "Milieuzone Amsterdam",
        "ZE Rotterdam",
        "ZE Utrecht",
        "ZE Amsterdam",
    }
    for zone in feed.zones:
        assert zone.zone_type == "lowEmissionZone"
        assert zone.status == "active"
        assert zone.order_status == "madeAndImplemented"
        assert len(zone.regulations) == 1
        regulation = zone.regulations[0]
        assert regulation.regulation_type == "AccessRestriction"
        assert regulation.restriction_type == "noEntry"
        # Every shape in the real feed is encodable.
        leaves = list(_leaves(regulation.condition))
        assert not [leaf for leaf in leaves if isinstance(leaf, Unsupported)]


def test_zone_metadata(zone_by_name):
    amsterdam = zone_by_name("Milieuzone Amsterdam")
    assert amsterdam.id == "NDW11_acbf0f7f-56a6-4b36-9a66-4b6d0c69d474"
    assert amsterdam.city == "Amsterdam"
    assert amsterdam.valid_from == datetime(2025, 1, 1, tzinfo=UTC)
    assert amsterdam.valid_until == datetime(2030, 1, 1, tzinfo=UTC)
    assert amsterdam.info_url is not None
    assert amsterdam.info_url.startswith("https://")
    venlo = zone_by_name("Identificatie146223")
    assert venlo.city == "Venlo"
    assert venlo.valid_from == datetime(2027, 1, 1, tzinfo=UTC)


def test_geometry_is_lon_lat_and_closed(zone_by_name):
    amsterdam = zone_by_name("Milieuzone Amsterdam")
    assert len(amsterdam.polygons) == 6
    lon, lat = amsterdam.polygons[0][0][0]
    assert 4.7 < lon < 5.1
    assert 52.2 < lat < 52.5
    for polygon in amsterdam.polygons:
        for ring in polygon:
            assert ring[0] == ring[-1]


def test_extended_euro_values_are_read(zone_by_name):
    """Euro 1-4 sit in the _extendedValue attribute, not in the element text."""
    zone = zone_by_name("LEZ Rotterdam Maasvlakte")
    values = [
        c.value
        for leaf in _leaves(zone.regulations[0].condition)
        if isinstance(leaf, VehicleCondition)
        for c in leaf.characteristics
        if c.kind == "emissionClassificationEuro"
    ]
    assert values == ["euro1", "euro2", "euro3", "euro4", "euro5", "euro6", "euro6"]


def test_condition_tree_shape_ze_zone(zone_by_name):
    tree = zone_by_name("ZE Utrecht").regulations[0].condition
    assert isinstance(tree, ConditionSet)
    assert tree.operator == "and"
    assert not tree.negate
    kinds = [type(c).__name__ for c in tree.children]
    assert kinds == [
        "ValidityCondition",
        "LocationCondition",
        "ConditionSet",
        "ConditionSet",
    ]
    exemptions = tree.children[3]
    assert isinstance(exemptions, ConditionSet)
    assert exemptions.negate
    assert exemptions.operator == "or"
    leaf_kinds = {
        c.kind
        for leaf in _leaves(tree)
        if isinstance(leaf, VehicleCondition)
        for c in leaf.characteristics
    }
    assert leaf_kinds == {
        "euVehicleCategory",
        "emissionClassificationEuro",
        "euSpecialPurposeVehicle",
        "ownerType",
        "vehicleAge",
        "fuelType",
    }
    ages = [
        (c.operator, c.value)
        for leaf in _leaves(tree)
        if isinstance(leaf, VehicleCondition)
        for c in leaf.characteristics
        if c.kind == "vehicleAge"
    ]
    assert ages == [("greaterThanOrEqualTo", "40"), ("lessThan", "13")]


def test_raw_xml_has_no_coordinates(zone_by_name):
    tree = zone_by_name("ZE Utrecht").regulations[0].condition
    location = next(c for c in _leaves(tree) if isinstance(c, LocationCondition))
    assert "omitted" in location.raw
    assert "52." not in location.raw
    validity = next(c for c in _leaves(tree) if isinstance(c, ValidityCondition))
    assert "<com:overallStartTime>" in validity.raw


def _replace(xml: bytes, old: str, new: str) -> bytes:
    text = xml.decode()
    assert old in text
    return text.replace(old, new, 1).encode()


def _unsupported(feed):
    return [
        leaf
        for zone in feed.zones
        for leaf in _leaves(zone.regulations[0].condition)
        if isinstance(leaf, Unsupported)
    ]


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        (
            "<com:overallEndTime>2030-01-01T00:00:00Z</com:overallEndTime>",
            "<com:overallEndTime>2030-01-01T00:00:00Z</com:overallEndTime>"
            "<com:validPeriod><com:recurringTimePeriodOfDay/></com:validPeriod>",
            "time specification uses ['validPeriod']",
        ),
        (
            "<com:overallEndTime>2030-01-01T00:00:00Z</com:overallEndTime>",
            "<com:overallEndTime>2030-01-01T00:00:00</com:overallEndTime>",
            "validity time without timezone",
        ),
        (
            "<com:overallEndTime>2030-01-01T00:00:00Z</com:overallEndTime>",
            "<com:overallEndTime>soon</com:overallEndTime>",
            "validity time is not ISO 8601",
        ),
        (
            "<com:validityStatus>definedByValidityTimeSpec</com:validityStatus>",
            "<com:validityStatus>suspended</com:validityStatus>",
            "validityStatus 'suspended'",
        ),
        (
            "<com:fuelType>diesel</com:fuelType>",
            "<com:fuelType>diesel</com:fuelType><com:heightCharacteristic/>",
            "vehicleCharacteristics/heightCharacteristic",
        ),
        (
            '<tro:operator>or</tro:operator><tro:conditions xsi:type="tro:Vehicle',
            '<tro:operator>xor</tro:operator><tro:conditions xsi:type="tro:Vehicle',
            "operator 'xor'",
        ),
        (
            'xsi:type="tro:LocationCondition"',
            'xsi:type="tro:RoadCondition"',
            "condition type 'RoadCondition'",
        ),
    ],
)
def test_unknown_shapes_become_unsupported(zones_xml, old, new, reason):
    feed = parse_zone_feed(_replace(zones_xml, old, new))
    found = _unsupported(feed)
    assert len(found) == 1
    assert reason in found[0].reason


def test_not_a_zone_publication():
    with pytest.raises(FeedFormatError):
        parse_zone_feed(b"<root><payload/></root>")
