# NDW emission-zone rule shapes

Source: `https://opendata.ndw.nu/emissiezones.xml.gz` (CC0), DATEX II v3, publication time `2026-10-31T06:00:00.003072055Z`, SHA-256 of the gzip `402825a3...7c54cb`. Inspected on 2026-11-01. All counts below are for that file.

## Envelope

- Root `mc:messageContainer`, payload `xsi:type="cz:ControlledZoneTablePublication"`, one `cz:controlledZoneTable`.
- 42 `cz:urbanVehicleAccessRegulation` records. All 42 have `controlledZoneType` `lowEmissionZone` and `status` `active`. The feed uses `lowEmissionZone` for both milieuzones and zero-emission zones; only the rule tells them apart.
- Each record has one `cz:trafficRegulationOrder` (status `madeAndImplemented` in all 42) with one `tro:trafficRegulation`. The city is `tro:issuingAuthority` (for example `'s-Gravenhage` for Den Haag, `Haarlemmermeer` for Schiphol, `Venlo` for the zone named `Identificatie146223`).
- `typeOfRegulation` is `tro:AccessRestriction` with `accessRestrictionType` `noEntry` in all 42. The condition tree says when entry is forbidden.

## Condition elements (whole file)

| Element | Count | Notes |
| --- | --- | --- |
| `tro:ConditionSet` | 398 | operators `and` / `or` only; `negate` `true` on 42 sets (one per zone, the exemption list) |
| `tro:ValidityCondition` | 87 | 42 at zone level, 45 inside exemptions. `validityStatus` is `definedByValidityTimeSpec` in all 87. Only `overallStartTime` (87) and `overallEndTime` (76). No `validPeriod`, no time-of-day or day-of-week windows. |
| `tro:LocationCondition` | 42 | `loc:AreaLocation` with one `gmlMultiPolygon` each; 70 polygons, no interior rings, `posList` order is `lat lon` (WGS 84), every ring closed |
| `tro:VehicleCondition` | 664 | see below |

Vehicle characteristics inside the 664 vehicle conditions:

| Characteristic | Count | Values |
| --- | --- | --- |
| `euVehicleCategory` | 218 | n2 86, n1 80, n3 41, m 3, m2 3, m3 3, m1 2 |
| `euSpecialPurposeVehicle` | 168 | motorCaravan 42, armouredVehicle 42, mobileCrane 42, wheelChairAccessibleVehicle 42 |
| `ageCharacteristic` | 84 | `greaterThanOrEqualTo 40` 42, `lessThan 13` 42 |
| `emissionClassificationEuro` | 79 | euro6 39, euro5 28, `_extended` 12 (`_extendedValue` euro4 6, euro3 2, euro2 2, euro1 2) |
| `fuelType` alone | 62 | battery 31, hydrogen 31 |
| `fuelType` + `vehicleType` | 11 | diesel + anyVehicle 11 |
| `ownerType` | 42 | permanentResident 42 |

Note: Euro 1-4 are not in the DATEX enum, so the feed writes `_extended` as element text and puts the real value in the `_extendedValue` attribute. A parser that reads only the text loses these classes.

## Rule shapes

Every zone is `ALL(validity, location, scope, NOT ANY(exemptions))`. The national exemption block is the same in all 42 zones: motor caravan AND permanent resident; age >= 40 years; (armoured OR mobile crane) AND age < 13; wheelchair accessible.

| # | Zones | Scope | Extra exemptions | Zones |
| --- | --- | --- | --- | --- |
| 1 | 21 | N1/N2/N3 | N1/N2 Euro 5 until 2026-12-31T23:00Z (time-limited); N1/N2 Euro 6 until 2027-12-31T23:00Z (time-limited); battery OR hydrogen | ZES Maastricht, ZE Tilburg, ZE Schiphol, ZE 's-Hertogenbosch, ZE Enschede, ZE Delft, ZE Assen, ZE Groningen, ZE Leiden, ZE Nijmegen, Milieuzone Arnhem actualisering per 1 juni 2026, ZE Eindhoven, ZE Rotterdam, ZE Den Haag, ZE Utrecht, ZE Gouda, ZE Haarlem, ZE Amsterdam, ZE Zwolle, ZE Amersfoort 2025, ZE Den Haag Kust |
| 2 | 7 | N1/N2/N3 | battery OR hydrogen | ZE Apeldoorn, ZE Deventer, ZEZ Breda (voorlopig), ZE zone Almere Buiten, ZE zone Almere Haven, ZE Ede, ZE zone Almere Stad |
| 3 | 3 | N1/N2/N3 | N1/N2 Euro 6 (time-limited); battery OR hydrogen | Identificatie146223 (Venlo), ZE zone Alphen aan den Rijn, ZE Amersfoort 2027 |
| 4 | 4 | diesel, any vehicle | N2/N3 Euro 6 | LEZ Breda, LEZ Breda 26072026, Milieuzone Maastricht, LEZ Delft |
| 5 | 1 | diesel, any vehicle | M/N1 Euro 1-6; N2/N3 Euro 6 | LEZ Rotterdam Maasvlakte |
| 6 | 1 | diesel, any vehicle | M/N1 Euro 4-6; N2/N3 Euro 6 | LEZ Utrecht |
| 7 | 1 | diesel, any vehicle | M1/N1 Euro 5-6; M2/M3/N2/N3 Euro 6 | Milieuzone Amsterdam |
| 8 | 1 | diesel, any vehicle | M1/N1 Euro 4-6; M2/M3/N2/N3 Euro 6 | LEZ Den Haag |
| 9 | 1 | diesel, any vehicle | M2/M3/N2/N3 Euro 4-6 | LEZ Rijswijk |
| 10 | 1 | diesel, any vehicle | N2/N3 Euro 4-6 | LEZ Leiden |
| 11 | 1 | diesel, any vehicle | M Euro 1-6 | LEZ Haarlem |

Zone validity on 2026-11-01: LEZ Breda ended 2026-06-30. These zones start later: ZE Alphen aan den Rijn, ZE Amersfoort 2027 and Venlo (2027-01-01), ZE Deventer and the three Almere zones (2028-01-01), ZEZ Breda (2029-01-01), ZE Apeldoorn and ZE Ede (2030-01-01).

## How the service encodes each element

The evaluator uses three-valued (Kleene) logic: every leaf is true, false or unknown, and the zone result is `not_allowed` (true), `allowed` (false) or `unknown`. A result is only `allowed` or `not_allowed` when it holds for every possible value of the unknown leaves.

| Element | Encoded as | Unknown when |
| --- | --- | --- |
| ValidityCondition | `start <= now < end` (UTC) | `validityStatus` other than `definedByValidityTimeSpec`, or any child other than overall start/end (time windows) |
| LocationCondition | true (the question is about entering the zone) | negated |
| euVehicleCategory | RDW `europese_voertuigcategorie`; `m` matches M1/M2/M3 | RDW value missing, not a letter plus optional digit, or a bare letter that the feed value refines (RDW `N` against feed `n1`) |
| emissionClassificationEuro (euro1-euro6) | RDW `emissiecode_omschrijving` 0-6, else `uitlaatemissieniveau` `EURO <n>` or Roman `EURO VI` | conflict between the two fields, conflict between fuel rows, `EEV`, `EURO 5+`, `AX`/`ZX`, code 0 without `EURO 0`, no class; electric rows (code Z) carry no class |
| fuelType diesel | any RDW fuel row `Diesel` | no fuel rows, or an unknown fuel name |
| fuelType battery | every RDW fuel row is `Elektriciteit` (a plug-in hybrid is false) | as above |
| fuelType hydrogen | `Waterstof` with only `Elektriciteit` beside it | `Waterstof` plus a combustion fuel |
| vehicleType anyVehicle | true | any other vehicleType value |
| vehicleAge | completed years since RDW `datum_eerste_toelating` | no date, unknown operator |
| euSpecialPurposeVehicle | false when RDW `inrichting` is an ordinary body type (hatchback, stationwagen, gesloten opbouw, ...) | `inrichting` is the matching special type (kampeerwagen, gepantserd voertuig, mobiele kraan, voor rolstoelen toegankelijk voertuig), or not registered, or any value outside the ordinary list. The service never sets a special-purpose exemption to true. |
| ownerType permanentResident | never known | always (RDW open data has no owner data); harmless when the vehicle is certainly not a motor caravan |
| Any other element, type, operator or value | `Unsupported` node | always |
| No RDW record | whole answer `unknown` | always |

Encoded today: all 11 shapes. Every element in the current feed maps to an encoded leaf; the only leaves that are always unknown are `ownerType` and the special-purpose types for vehicles registered as one.

## Feed scope wider than the exemption set

Encoded as written, shapes 4, 9 and 10 make every diesel passenger car `not_allowed`, also a Euro 6 diesel car, in LEZ Breda 26072026, Milieuzone Maastricht, LEZ Delft, LEZ Rijswijk and LEZ Leiden (LEZ Breda has expired). Shape 11 (LEZ Haarlem) makes every diesel N1/N2/N3 vehicle `not_allowed`. The restriction has scope "diesel, any vehicle", and the exemptions mention only some categories. The municipal rules for these zones may be narrower (for example trucks only). The service does not correct the feed. This is a wrong `not_allowed` risk, not a wrong `allowed` risk; it needs a decision (see STATUS.md).
