"""Decide access with three-valued (Kleene) logic over the NDW condition tree.

Every leaf evaluates to True, False or None (unknown). The regulation is a
``noEntry`` restriction, so the top condition means "this vehicle may not
enter". True gives ``not_allowed``, False gives ``allowed`` and None gives
``unknown``. Kleene logic only returns True or False when the answer is the
same for every possible value of the unknown leaves, so an unknown fact can
never turn into ``allowed`` by default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Literal

from .datex import (
    Characteristic,
    Condition,
    ConditionSet,
    LocationCondition,
    Unsupported,
    ValidityCondition,
    VehicleCondition,
)

if TYPE_CHECKING:
    from .datex import Zone
    from .rdw import Vehicle

type Tri = bool | None
type Result = Literal["allowed", "not_allowed", "unknown"]


def k_not(value: Tri) -> Tri:
    return None if value is None else not value


def k_and(values: list[Tri]) -> Tri:
    if any(v is False for v in values):
        return False
    if any(v is None for v in values):
        return None
    return True


def k_or(values: list[Tri]) -> Tri:
    if any(v is True for v in values):
        return True
    if any(v is None for v in values):
        return None
    return False


# --- Vehicle facts ------------------------------------------------------------

_COMBUSTION = {"Benzine", "Diesel", "LPG", "CNG", "LNG", "Alcohol"}
_KNOWN_FUELS = _COMBUSTION | {"Elektriciteit", "Waterstof"}
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
_LEVEL = re.compile(r"EURO ([0-6]|VI|IV|V|I{1,3})(?: [A-Z]{1,2})?")

# RDW "inrichting" values that are the special-purpose body types the feed
# names. A match stays unknown, never True: the body description is not the
# EU special-purpose code, and True would grant an exemption.
_SPECIAL_INRICHTING = {
    "kampeerwagen": "motorCaravan",
    "gepantserd voertuig": "armouredVehicle",
    "mobiele kraan": "mobileCrane",
    "voor rolstoelen toegankelijk voertuig": "wheelChairAccessibleVehicle",
}
# Ordinary body types: certainly none of the four special-purpose types.
# Any other value (Niet geregistreerd, N.v.t., speciale groep, kraanwagen,
# ...) leaves the special-purpose question unknown.
_ORDINARY_INRICHTING = {
    "hatchback",
    "stationwagen",
    "MPV",
    "sedan",
    "cabriolet",
    "coupe",
    "limousine",
    "truckstationwagen",
    "gesloten opbouw",
    "open laadvloer",
    "open wagen",
    "open wagen met vast dak",
    "gedeeltelijk open wagen",
    "pick-up truck",
    "opleggertrekker",
    "huifopbouw",
    "neerklapbare zijschotten",
    "kipper",
    "achterwaartse kipper",
    "driezijdige kipper",
    "bus",
    "veewagen",
    "tankwagen",
    "koelwagen",
    "geconditioneerd voertuig",
    "gecond. met temperatuurreg.",
    "gecond. zndr temperatuurreg.",
    "voor vervoer voertuigen",
    "containercarrier",
    "afneembare bovenbouw",
    "voertuig met haakarm",
    "vuilniswagen",
    "betonmixer",
}
_SPECIAL_PURPOSE_VALUES = set(_SPECIAL_INRICHTING.values())


def euro_class(vehicle: Vehicle) -> tuple[int | None, str]:
    """Return the Euro emission class from the RDW fuel rows, or None.

    Uses emissiecode_omschrijving (0-6) and uitlaatemissieniveau ("EURO 6 AP",
    "EURO VI D"). Rows of an electric drive (code Z) carry no class. Conflicts,
    unparseable codes, or a code 0 without "EURO 0" give None.
    """
    classes: set[int] = set()
    for fuel in vehicle.fuels:
        code = (fuel.emissiecode_omschrijving or "").strip()
        level_text = (fuel.uitlaatemissieniveau or "").strip()
        match = _LEVEL.fullmatch(level_text)
        level = None
        if match:
            token = match.group(1)
            level = int(token) if token.isdigit() else _ROMAN[token]
        if code == "Z" or (fuel.brandstof_omschrijving == "Elektriciteit" and not code):
            continue
        if code in {"1", "2", "3", "4", "5", "6"}:
            if level is not None and level != int(code):
                return None, f"emissiecode {code} conflicts with {level_text!r}"
            classes.add(int(code))
        elif code == "0":
            if level != 0:
                return None, "emissiecode 0 without uitlaatemissieniveau EURO 0"
            classes.add(0)
        elif not code and level is not None:
            classes.add(level)
        else:
            return None, (
                f"no usable Euro class for {fuel.brandstof_omschrijving}: "
                f"emissiecode={code or None!r}, "
                f"uitlaatemissieniveau={level_text or None!r}"
            )
    if len(classes) == 1:
        value = classes.pop()
        return value, f"Euro {value}"
    if not classes:
        return None, "RDW gives no Euro class"
    return None, f"fuel rows give different Euro classes {sorted(classes)}"


def _fuel_set(vehicle: Vehicle) -> set[str] | None:
    names = {f.brandstof_omschrijving or "" for f in vehicle.fuels}
    if not names or not names <= _KNOWN_FUELS:
        return None
    return names


def vehicle_age(first_admission: date, on: date) -> int:
    years = on.year - first_admission.year
    if (on.month, on.day) < (first_admission.month, first_admission.day):
        years -= 1
    return years


_AGE_OPERATORS = {
    "greaterThanOrEqualTo": (">=", lambda a, b: a >= b),
    "greaterThan": (">", lambda a, b: a > b),
    "lessThan": ("<", lambda a, b: a < b),
    "lessThanOrEqualTo": ("<=", lambda a, b: a <= b),
    "equalTo": ("=", lambda a, b: a == b),
}
_FUEL_LABEL = {
    "diesel": "diesel",
    "battery": "battery-electric",
    "hydrogen": "hydrogen",
}
_SPECIAL_LABEL = {
    "motorCaravan": "motor caravan",
    "armouredVehicle": "armoured vehicle",
    "mobileCrane": "mobile crane",
    "wheelChairAccessibleVehicle": "wheelchair-accessible vehicle",
}


def describe_characteristic(c: Characteristic) -> str:
    match c.kind:
        case "fuelType":
            return f"fuel type is {_FUEL_LABEL.get(c.value, c.value)}"
        case "vehicleType":
            return "any vehicle type" if c.value == "anyVehicle" else f"type {c.value}"
        case "emissionClassificationEuro":
            return f"Euro emission class is {c.value.replace('euro', 'Euro ')}"
        case "euVehicleCategory":
            v = c.value.upper()
            return f"EU vehicle category is {v}" + (" (any)" if len(v) == 1 else "")
        case "euSpecialPurposeVehicle":
            return f"special-purpose vehicle: {_SPECIAL_LABEL.get(c.value, c.value)}"
        case "ownerType":
            return f"owner type is {c.value}"
        case "vehicleAge":
            symbol = _AGE_OPERATORS.get(c.operator or "", (c.operator, None))[0]
            return f"vehicle age {symbol} {c.value} years"
    return f"{c.kind} = {c.value}"


def evaluate_characteristic(
    c: Characteristic, vehicle: Vehicle, now: datetime
) -> tuple[Tri, str]:
    """Return (value, RDW fact used) for one characteristic."""
    match c.kind:
        case "fuelType":
            fuels = _fuel_set(vehicle)
            fact = "RDW brandstof: " + (
                ", ".join(f.brandstof_omschrijving or "?" for f in vehicle.fuels)
                or "none"
            )
            if fuels is None or c.value not in _FUEL_LABEL:
                return None, fact
            if c.value == "diesel":
                return "Diesel" in fuels, fact
            if c.value == "battery":
                return fuels == {"Elektriciteit"}, fact
            if "Waterstof" not in fuels:
                return False, fact
            return (True if fuels <= {"Waterstof", "Elektriciteit"} else None), fact
        case "vehicleType":
            return (True if c.value == "anyVehicle" else None), "applies to all types"
        case "emissionClassificationEuro":
            cls, fact = euro_class(vehicle)
            wanted = re.fullmatch(r"euro([0-6])", c.value)
            if cls is None or wanted is None:
                return None, fact
            return cls == int(wanted.group(1)), fact
        case "euVehicleCategory":
            rdw = (vehicle.europese_voertuigcategorie or "").strip().upper()
            fact = f"RDW europese_voertuigcategorie: {rdw or None}"
            want = c.value.strip().upper()
            pattern = r"[A-Z]\d?"
            if not re.fullmatch(pattern, rdw) or not re.fullmatch(pattern, want):
                return None, fact
            if len(want) == 1:
                return rdw[0] == want, fact
            if len(rdw) == 1:
                return (False if rdw != want[0] else None), fact
            return rdw == want, fact
        case "euSpecialPurposeVehicle":
            inrichting = vehicle.inrichting
            fact = f"RDW inrichting: {inrichting}"
            if c.value not in _SPECIAL_PURPOSE_VALUES or inrichting is None:
                return None, fact
            if inrichting in _SPECIAL_INRICHTING:
                return (
                    None if _SPECIAL_INRICHTING[inrichting] == c.value else False
                ), fact
            if inrichting in _ORDINARY_INRICHTING:
                return False, fact
            return None, fact
        case "ownerType":
            return None, "RDW open data has no owner information"
        case "vehicleAge":
            first = vehicle.datum_eerste_toelating
            operator = _AGE_OPERATORS.get(c.operator or "")
            if first is None or operator is None or not c.value.isdigit():
                return None, f"RDW datum_eerste_toelating: {first}"
            age = vehicle_age(first, now.astimezone(UTC).date())
            fact = f"RDW datum_eerste_toelating {first.isoformat()}: age {age}"
            return operator[1](age, int(c.value)), fact
    return None, f"characteristic {c.kind} is not encoded"


# --- Tree evaluation ----------------------------------------------------------


@dataclass(frozen=True)
class LeafResult:
    condition_id: str | None
    readable: str
    value: Tri
    fact: str | None
    in_exemption: bool
    valid_until: datetime | None
    raw: str


@dataclass(frozen=True)
class Outcome:
    value: Tri
    decisive: tuple[LeafResult, ...]


def _leaf(
    condition: Condition, vehicle: Vehicle, now: datetime, in_exemption: bool
) -> LeafResult:
    valid_until = None
    match condition:
        case ValidityCondition(start=start, end=end):
            value: Tri = (start is None or start <= now) and (end is None or now < end)
            readable = (
                f"valid from {start.isoformat() if start else 'always'}"
                f" until {end.isoformat() if end else 'open end'}"
            )
            fact = f"evaluated at {now.isoformat()}"
            valid_until = end
        case LocationCondition():
            # The caller asks about entering this zone. A negated area is not
            # encoded.
            value = None if condition.negate else True
            readable = "vehicle is inside the zone area"
            fact = "assumed: the question is about entering this zone"
        case VehicleCondition(characteristics=characteristics):
            parts = [evaluate_characteristic(c, vehicle, now) for c in characteristics]
            value = k_and([p[0] for p in parts])
            readable = " and ".join(describe_characteristic(c) for c in characteristics)
            fact = "; ".join(dict.fromkeys(p[1] for p in parts))
        case Unsupported(reason=reason):
            value = None
            readable = f"rule shape not encoded: {reason}"
            fact = None
        case _:  # pragma: no cover - ConditionSet is handled by the caller
            raise TypeError(condition)
    if condition.negate and not isinstance(condition, LocationCondition):
        value = k_not(value)
        readable = f"NOT ({readable})"
    return LeafResult(
        condition_id=condition.id,
        readable=readable,
        value=value,
        fact=fact,
        in_exemption=in_exemption,
        valid_until=valid_until,
        raw=condition.raw,
    )


def evaluate(
    condition: Condition, vehicle: Vehicle, now: datetime, *, negated: bool = False
) -> Outcome:
    """Evaluate a condition tree. ``negated`` marks the inside of a NOT."""
    if not isinstance(condition, ConditionSet):
        leaf = _leaf(condition, vehicle, now, negated ^ condition.negate)
        return Outcome(leaf.value, (leaf,))
    inner = negated ^ condition.negate
    outcomes = [evaluate(c, vehicle, now, negated=inner) for c in condition.children]
    values = [o.value for o in outcomes]
    if condition.operator == "and":
        value, stop = k_and(values), False
    else:
        value, stop = k_or(values), True
    if value is stop:
        decisive = next(o.decisive for o in outcomes if o.value is stop)
    elif value is None:
        decisive = tuple(
            leaf for o in outcomes if o.value is None for leaf in o.decisive
        )
    else:
        decisive = tuple(leaf for o in outcomes for leaf in o.decisive)
    if condition.negate:
        value = k_not(value)
    return Outcome(value, decisive)


def render(condition: Condition, indent: int = 0) -> list[str]:
    """Render the condition tree as indented readable lines."""
    pad = "  " * indent
    prefix = "NOT " if condition.negate else ""
    match condition:
        case ConditionSet(operator=operator, children=children):
            head = "ALL of" if operator == "and" else "ANY of"
            lines = [f"{pad}{prefix}{head}:"]
            for child in children:
                lines.extend(render(child, indent + 1))
            return lines
        case ValidityCondition(start=start, end=end):
            text = (
                f"valid from {start.isoformat() if start else 'always'}"
                f" until {end.isoformat() if end else 'open end'}"
            )
        case LocationCondition():
            text = "inside the zone area"
        case VehicleCondition(characteristics=characteristics):
            text = " and ".join(describe_characteristic(c) for c in characteristics)
        case Unsupported(reason=reason):
            text = f"[not encoded: {reason}]"
    return [f"{pad}{prefix}{text}"]


# --- Zone decision -------------------------------------------------------------


@dataclass(frozen=True)
class ZoneDecision:
    result: Result
    reason: str
    deciding_conditions: tuple[LeafResult, ...]
    allowed_until: datetime | None
    rule_readable: tuple[str, ...]


_RESULT: dict[Tri, Result] = {True: "not_allowed", False: "allowed", None: "unknown"}


def decide(zone: Zone, vehicle: Vehicle | None, now: datetime) -> ZoneDecision:
    readable: list[str] = []
    for regulation in zone.regulations:
        readable.append(
            f"{regulation.regulation_type} {regulation.restriction_type} when:"
        )
        if regulation.condition is not None:
            readable.extend(render(regulation.condition, 1))
    rule = tuple(readable)

    if vehicle is None:
        return ZoneDecision(
            "unknown", "RDW has no vehicle record for this kenteken", (), None, rule
        )
    if zone.status != "active" or not zone.regulations:
        return ZoneDecision(
            "unknown",
            f"zone status is {zone.status!r} with {len(zone.regulations)} regulations",
            (),
            None,
            rule,
        )

    outcomes: list[Outcome] = []
    for regulation in zone.regulations:
        if (
            regulation.regulation_type != "AccessRestriction"
            or regulation.restriction_type != "noEntry"
            or regulation.condition is None
        ):
            leaf = LeafResult(
                regulation.id,
                f"regulation type {regulation.regulation_type}/"
                f"{regulation.restriction_type} is not encoded",
                None,
                None,
                False,
                None,
                "",
            )
            outcomes.append(Outcome(None, (leaf,)))
        else:
            outcomes.append(evaluate(regulation.condition, vehicle, now))

    value = k_or([o.value for o in outcomes])
    if value is True:
        decisive = next(o.decisive for o in outcomes if o.value is True)
    else:
        decisive = tuple(
            leaf for o in outcomes if o.value == value for leaf in o.decisive
        )

    allowed_until = None
    if value is False:
        if all(leaf.in_exemption for leaf in decisive):
            ends = [
                leaf.valid_until
                for leaf in decisive
                if leaf.valid_until is not None and leaf.value is True
            ]
            allowed_until = min(ends) if ends else None
            reason = "an exemption in the feed matches this vehicle"
            if allowed_until:
                reason += f"; the exemption ends at {allowed_until.isoformat()}"
        elif any(
            leaf.readable.startswith("valid ") and not leaf.in_exemption
            for leaf in decisive
        ):
            reason = "the zone restriction is not in force at the evaluation time"
        else:
            reason = "the restriction does not cover this vehicle"
    elif value is True:
        reason = "the restriction applies and no exemption in the feed matches"
    else:
        reason = "a fact or rule shape that decides the answer is unknown"
    return ZoneDecision(_RESULT[value], reason, decisive, allowed_until, rule)
