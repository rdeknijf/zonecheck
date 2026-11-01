"""Parse the NDW emission-zone feed (DATEX II v3 controlled-zone table).

The parser keeps the access rule as a condition tree, exactly as the feed
states it. It does not decide anything. Every element that the parser does
not recognise becomes an ``Unsupported`` node, so the evaluator can answer
``unknown`` for it instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from xml.etree.ElementTree import register_namespace, tostring

from defusedxml.ElementTree import fromstring

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

NS = {
    "mc": "http://datex2.eu/schema/3/messageContainer",
    "nlxe": "http://datex2.eu/schema/3/nlxExtensions",
    "inf": "http://datex2.eu/schema/3/informationManagement",
    "comx": "http://datex2.eu/schema/3/commonExtension",
    "cz": "http://datex2.eu/schema/3/controlledZone",
    "ex": "http://datex2.eu/schema/3/exchangeInformation",
    "tro": "http://datex2.eu/schema/3/trafficRegulation",
    "loc": "http://datex2.eu/schema/3/locationReferencing",
    "com": "http://datex2.eu/schema/3/common",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
for _prefix, _uri in NS.items():
    register_namespace(_prefix, _uri)

_XSI_TYPE = f"{{{NS['xsi']}}}type"
_POLYGON_PLACEHOLDER = "[polygon coordinates omitted, see /zones/{id}.geojson]"


class FeedFormatError(ValueError):
    """The document is not a DATEX II controlled-zone publication."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xsi_type(element: Element) -> str:
    return (element.get(_XSI_TYPE) or "").rsplit(":", 1)[-1]


def _child(element: Element, name: str) -> Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _children(element: Element, name: str) -> list[Element]:
    return [child for child in element if _local(child.tag) == name]


def _text(element: Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip() or None


def _multilingual(element: Element | None) -> str | None:
    if element is None:
        return None
    values = [v.text.strip() for v in element.iter() if v.text and v.text.strip()]
    return values[0] if values else None


def _datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _raw(element: Element) -> str:
    """Serialise one condition without polygon coordinates."""
    text = tostring(element, encoding="unicode")
    text = re.sub(
        r"(<loc:posList>)[^<]*(</loc:posList>)",
        rf"\g<1>{_POLYGON_PLACEHOLDER}\g<2>",
        text,
    )
    # tostring repeats every namespace declaration on the snippet root.
    return re.sub(r' xmlns:\w+="[^"]*"', "", text)


# --- Condition tree -------------------------------------------------------


@dataclass(frozen=True)
class Characteristic:
    """One vehicle characteristic that a VehicleCondition tests."""

    kind: str  # fuelType, vehicleType, emissionClassificationEuro, ...
    value: str
    operator: str | None = None  # only for vehicleAge


@dataclass(frozen=True)
class ConditionSet:
    id: str | None
    operator: str  # "and" | "or" | anything else is unsupported
    negate: bool
    children: tuple[Condition, ...]
    raw: str = field(repr=False, compare=False)


@dataclass(frozen=True)
class ValidityCondition:
    id: str | None
    negate: bool
    start: datetime | None
    end: datetime | None
    raw: str = field(repr=False, compare=False)


@dataclass(frozen=True)
class LocationCondition:
    id: str | None
    negate: bool
    raw: str = field(repr=False, compare=False)


@dataclass(frozen=True)
class VehicleCondition:
    id: str | None
    negate: bool
    characteristics: tuple[Characteristic, ...]
    raw: str = field(repr=False, compare=False)


@dataclass(frozen=True)
class Unsupported:
    """A condition whose shape the parser cannot encode with certainty."""

    id: str | None
    negate: bool
    reason: str
    raw: str = field(repr=False, compare=False)


type Condition = (
    ConditionSet
    | ValidityCondition
    | LocationCondition
    | VehicleCondition
    | Unsupported
)


@dataclass(frozen=True)
class Regulation:
    """One trafficRegulation: a restriction type plus its condition tree."""

    id: str | None
    regulation_type: str  # xsi:type of typeOfRegulation, e.g. AccessRestriction
    restriction_type: str | None  # e.g. noEntry
    condition: Condition | None


@dataclass(frozen=True)
class Zone:
    id: str
    version: str | None
    name: str
    city: str | None
    zone_type: str | None
    status: str | None
    order_status: str | None
    regulation_id: str | None
    info_url: str | None
    record_version_time: datetime | None
    valid_from: datetime | None
    valid_until: datetime | None
    regulations: tuple[Regulation, ...]
    # Each polygon is a list of rings; each ring a list of (lon, lat).
    polygons: tuple[tuple[tuple[tuple[float, float], ...], ...], ...]


@dataclass(frozen=True)
class ZoneFeed:
    publication_time: datetime | None
    table_version_time: datetime | None
    zones: tuple[Zone, ...]


# --- Parsing ----------------------------------------------------------------


def _negate(element: Element) -> tuple[bool, str | None]:
    """Return (negate, error). A value other than true/false is an error."""
    value = _text(_child(element, "negate"))
    if value is None or value == "false":
        return False, None
    if value == "true":
        return True, None
    return False, f"unknown negate value {value!r}"


_KNOWN_VALIDITY_CHILDREN = {"overallStartTime", "overallEndTime"}


def _parse_validity(element: Element, cid: str | None, negate: bool) -> Condition:
    raw = _raw(element)
    by_order = _child(element, "validityByOrder")
    if by_order is None:
        return Unsupported(
            cid, negate, "validity condition without validityByOrder", raw
        )
    status = _text(_child(by_order, "validityStatus"))
    if status != "definedByValidityTimeSpec":
        return Unsupported(
            cid, negate, f"validityStatus {status!r} is not encoded", raw
        )
    spec = _child(by_order, "validityTimeSpecification")
    if spec is None:
        return Unsupported(cid, negate, "validity without time specification", raw)
    extra = {_local(c.tag) for c in spec} - _KNOWN_VALIDITY_CHILDREN
    if extra:
        # validPeriod, exceptionPeriod, recurring time windows, ...
        return Unsupported(cid, negate, f"time specification uses {sorted(extra)}", raw)
    try:
        start = _datetime(_text(_child(spec, "overallStartTime")))
        end = _datetime(_text(_child(spec, "overallEndTime")))
    except ValueError:
        return Unsupported(cid, negate, "validity time is not ISO 8601", raw)
    if any(t is not None and t.tzinfo is None for t in (start, end)):
        return Unsupported(cid, negate, "validity time without timezone", raw)
    return ValidityCondition(cid, negate, start, end, raw)


def _parse_characteristics(vc: Element) -> tuple[list[Characteristic], list[str]]:
    """Read the vehicleCharacteristics element. Return (found, problems)."""
    found: list[Characteristic] = []
    problems: list[str] = []
    for item in vc:
        name = _local(item.tag)
        if name in {"fuelType", "vehicleType"}:
            value = _text(item)
            if value is None or len(item):
                problems.append(f"empty or nested {name}")
            else:
                found.append(Characteristic(name, value))
        elif name == "emissions":
            for emission in item:
                if _local(emission.tag) != "emissionClassificationEuro":
                    problems.append(f"emissions/{_local(emission.tag)}")
                    continue
                value = _text(emission)
                if value == "_extended":
                    value = emission.get("_extendedValue")
                if value is None:
                    problems.append("emissionClassificationEuro without value")
                else:
                    found.append(Characteristic("emissionClassificationEuro", value))
        elif name == "_vehicleCharacteristicsExtension":
            for extended in item:
                if _local(extended.tag) != "vehicleCharacteristicsExtended":
                    problems.append(f"extension/{_local(extended.tag)}")
                    continue
                _parse_extended(extended, found, problems)
        else:
            problems.append(f"vehicleCharacteristics/{name}")
    return found, problems


def _parse_extended(
    extended: Element, found: list[Characteristic], problems: list[str]
) -> None:
    for group in extended:
        gname = _local(group.tag)
        if gname == "regulatedCharacteristics":
            for leaf in group:
                lname = _local(leaf.tag)
                value = _text(leaf)
                if lname in {"euVehicleCategory", "euSpecialPurposeVehicle"} and value:
                    found.append(Characteristic(lname, value))
                else:
                    problems.append(f"regulatedCharacteristics/{lname}")
        elif gname == "ownerCharacteristic":
            for leaf in group:
                value = _text(leaf)
                if _local(leaf.tag) == "ownerType" and value:
                    found.append(Characteristic("ownerType", value))
                else:
                    problems.append(f"ownerCharacteristic/{_local(leaf.tag)}")
        elif gname == "ageCharacteristic":
            operator = _text(_child(group, "comparisonOperator"))
            age = _text(_child(group, "vehicleAge"))
            names = {_local(c.tag) for c in group}
            if operator and age and names == {"comparisonOperator", "vehicleAge"}:
                found.append(Characteristic("vehicleAge", age, operator))
            else:
                problems.append(f"ageCharacteristic with {sorted(names)}")
        else:
            problems.append(f"vehicleCharacteristicsExtended/{gname}")


def _parse_condition(element: Element) -> Condition:
    cid = element.get("id")
    negate, negate_error = _negate(element)
    kind = _xsi_type(element)
    if negate_error:
        return Unsupported(cid, False, negate_error, _raw(element))
    if kind == "ConditionSet":
        operator = _text(_child(element, "operator")) or ""
        children = tuple(_parse_condition(c) for c in _children(element, "conditions"))
        if operator not in {"and", "or"} or not children:
            return Unsupported(
                cid,
                negate,
                f"condition set with operator {operator!r} and {len(children)} parts",
                _raw(element),
            )
        return ConditionSet(cid, operator, negate, children, _raw(element))
    if kind == "ValidityCondition":
        return _parse_validity(element, cid, negate)
    if kind == "LocationCondition":
        location = _child(element, "locationByOrder")
        if location is None or _xsi_type(location) != "AreaLocation":
            return Unsupported(cid, negate, "location is not an area", _raw(element))
        return LocationCondition(cid, negate, _raw(element))
    if kind == "VehicleCondition":
        vcs = _children(element, "vehicleCharacteristics")
        if len(vcs) != 1:
            return Unsupported(
                cid, negate, f"{len(vcs)} vehicleCharacteristics", _raw(element)
            )
        found, problems = _parse_characteristics(vcs[0])
        if problems or not found:
            reason = "unsupported vehicle characteristics: " + (
                ", ".join(problems) or "none given"
            )
            return Unsupported(cid, negate, reason, _raw(element))
        return VehicleCondition(cid, negate, tuple(found), _raw(element))
    return Unsupported(cid, negate, f"condition type {kind!r}", _raw(element))


def _parse_polygons(
    zone: Element,
) -> tuple[tuple[tuple[tuple[float, float], ...], ...], ...]:
    polygons = []
    for polygon in zone.iter(f"{{{NS['loc']}}}gmlPolygon"):
        rings = []
        for ring_name in ("exterior", "interior"):
            for ring in polygon.iter(f"{{{NS['loc']}}}{ring_name}"):
                pos = _text(_child(ring, "posList"))
                if not pos:
                    continue
                numbers = [float(n) for n in pos.split()]
                # DATEX II posList order is "lat lon"; GeoJSON wants [lon, lat].
                points = [
                    (numbers[i + 1], numbers[i]) for i in range(0, len(numbers) - 1, 2)
                ]
                if points and points[0] != points[-1]:
                    points.append(points[0])
                rings.append(tuple(points))
        if rings:
            polygons.append(tuple(rings))
    return tuple(polygons)


def _top_validity(
    condition: Condition | None,
) -> tuple[datetime | None, datetime | None]:
    """Return the start and end of the ValidityCondition at the top AND level."""
    if isinstance(condition, ConditionSet) and condition.operator == "and":
        for child in condition.children:
            if isinstance(child, ValidityCondition) and not child.negate:
                return child.start, child.end
    return None, None


def _parse_zone(element: Element) -> Zone:
    regulations = []
    regulation_id = order_status = city = None
    for order in _children(element, "trafficRegulationOrder"):
        city = city or _multilingual(_child(order, "issuingAuthority"))
        regulation_id = regulation_id or _text(_child(order, "regulationId"))
        order_status = order_status or _text(_child(order, "status"))
        for regulation in _children(order, "trafficRegulation"):
            type_el = _child(regulation, "typeOfRegulation")
            condition_el = _child(regulation, "condition")
            regulations.append(
                Regulation(
                    id=regulation.get("id"),
                    regulation_type=_xsi_type(type_el) if type_el is not None else "",
                    restriction_type=(
                        _text(_child(type_el, "accessRestrictionType"))
                        if type_el is not None
                        else None
                    ),
                    condition=(
                        _parse_condition(condition_el)
                        if condition_el is not None
                        else None
                    ),
                )
            )
    first = regulations[0].condition if len(regulations) == 1 else None
    valid_from, valid_until = _top_validity(first)
    zone_id = element.get("id")
    if not zone_id:
        raise FeedFormatError("zone without id")
    return Zone(
        id=zone_id,
        version=element.get("version"),
        name=_multilingual(_child(element, "name")) or zone_id,
        city=city,
        zone_type=_text(_child(element, "controlledZoneType")),
        status=_text(_child(element, "status")),
        order_status=order_status,
        regulation_id=regulation_id,
        info_url=_text(_child(element, "urlForFurtherInformation")),
        record_version_time=_datetime(
            _text(_child(element, "controlledZoneRecordVersionTime"))
        ),
        valid_from=valid_from,
        valid_until=valid_until,
        regulations=tuple(regulations),
        polygons=_parse_polygons(element),
    )


def parse_zone_feed(content: bytes) -> ZoneFeed:
    """Parse the decompressed emissiezones.xml document."""
    root = fromstring(content)
    payload = _child(root, "payload")
    if payload is None or _xsi_type(payload) != "ControlledZoneTablePublication":
        raise FeedFormatError("not a ControlledZoneTablePublication")
    table = _child(payload, "controlledZoneTable")
    if table is None:
        raise FeedFormatError("publication without controlledZoneTable")
    zones = tuple(
        _parse_zone(z) for z in _children(table, "urbanVehicleAccessRegulation")
    )
    return ZoneFeed(
        publication_time=_datetime(_text(_child(payload, "publicationTime"))),
        table_version_time=_datetime(_text(_child(table, "tableVersionTime"))),
        zones=zones,
    )
