"""HTTP API: can licence plate X enter Dutch low- or zero-emission zone Y?"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import ndw_feed
from .datex import Zone, ZoneFeed, parse_zone_feed
from .models import (
    AccessResponse,
    DecidingCondition,
    FeedInfo,
    FuelFacts,
    Health,
    VehicleFacts,
    ZoneAccess,
    ZoneList,
    ZoneSummary,
)
from .rdw import InvalidKentekenError, RdwClient, RdwError, Vehicle, normalise_kenteken
from .rules import decide, euro_class, vehicle_age

ZONES_URL = "https://opendata.ndw.nu/emissiezones.xml.gz"
DISCLAIMER = (
    "Informational only. This answer comes from the NDW emission-zone feed and "
    "RDW open data. Both can be incomplete or out of date, and the feed does not "
    "contain individual exemptions (ontheffingen) or local rules outside it. "
    "Check the municipality's own information before you enter the zone. "
    "No liability is accepted for any decision based on this answer."
)
SOURCES = [
    "NDW emission zones, https://opendata.ndw.nu/emissiezones.xml.gz (CC0)",
    "RDW Open Data m9d7-ebf2 and 8ys7-d773, https://opendata.rdw.nl (public domain)",
]
# The feed names the city as the issuing municipality; "Den Haag" is
# "'s-Gravenhage" there.
_CITY_ALIASES = {"den haag": "'s-gravenhage", "the hague": "'s-gravenhage"}
_ORDER = {"not_allowed": 0, "unknown": 1, "allowed": 2}

type Clock = Callable[[], datetime]


class ZoneStore:
    """Keep the parsed zone feed in memory and refresh it after ``ttl``."""

    def __init__(
        self,
        fetcher: Callable[[], ndw_feed.FeedSnapshot],
        ttl: timedelta = timedelta(hours=1),
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._fetcher = fetcher
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._loaded_at: datetime | None = None
        self._snapshot: ndw_feed.FeedSnapshot | None = None
        self._feed: ZoneFeed | None = None

    def get(self) -> tuple[ZoneFeed, ndw_feed.FeedSnapshot]:
        with self._lock:
            now = self._clock()
            fresh = self._loaded_at is not None and now - self._loaded_at < self._ttl
            feed, snapshot = self._feed, self._snapshot
            if not fresh or feed is None or snapshot is None:
                new = self._fetcher()
                if feed is None or snapshot is None or new.sha256 != snapshot.sha256:
                    feed = parse_zone_feed(new.content)
                snapshot = new
                self._feed, self._snapshot, self._loaded_at = feed, snapshot, now
            return feed, snapshot


def _feed_info(feed: ZoneFeed, snapshot: ndw_feed.FeedSnapshot) -> FeedInfo:
    return FeedInfo(
        url=snapshot.url,
        publication_time=feed.publication_time,
        table_version_time=feed.table_version_time,
        fetched_at=snapshot.fetched_at,
        checked_at=snapshot.checked_at,
        last_modified=snapshot.last_modified,
        sha256=snapshot.sha256,
        stale_reason=snapshot.from_cache_after_error,
    )


def _summary(zone: Zone) -> ZoneSummary:
    return ZoneSummary(
        id=zone.id,
        name=zone.name,
        city=zone.city,
        type=zone.zone_type,
        status=zone.status,
        valid_from=zone.valid_from,
        valid_until=zone.valid_until,
        regulation_id=zone.regulation_id,
        info_url=zone.info_url,
        record_version_time=zone.record_version_time,
        geojson_url=f"/zones/{zone.id}.geojson" if zone.polygons else None,
    )


def _vehicle_facts(
    kenteken: str, vehicle: Vehicle | None, now: datetime
) -> VehicleFacts:
    if vehicle is None:
        return VehicleFacts(kenteken=kenteken, found=False)
    cls, basis = euro_class(vehicle)
    first = vehicle.datum_eerste_toelating
    return VehicleFacts(
        kenteken=kenteken,
        found=True,
        voertuigsoort=vehicle.voertuigsoort,
        merk=vehicle.merk,
        handelsbenaming=vehicle.handelsbenaming,
        europese_voertuigcategorie=vehicle.europese_voertuigcategorie,
        datum_eerste_toelating=first,
        inrichting=vehicle.inrichting,
        fuels=[
            FuelFacts(
                brandstof_omschrijving=f.brandstof_omschrijving,
                emissiecode_omschrijving=f.emissiecode_omschrijving,
                uitlaatemissieniveau=f.uitlaatemissieniveau,
            )
            for f in vehicle.fuels
        ],
        euro_class=cls,
        euro_class_basis=basis,
        age_years=vehicle_age(first, now.date()) if first else None,
    )


def match_zones(zones: tuple[Zone, ...], query: str) -> list[Zone]:
    """Find zones by exact id, else by city, else by zone name (case-insensitive)."""
    by_id = [z for z in zones if z.id == query]
    if by_id:
        return by_id
    wanted = query.strip().casefold()
    wanted = _CITY_ALIASES.get(wanted, wanted)
    by_city = [z for z in zones if (z.city or "").casefold() == wanted]
    if by_city:
        return by_city
    return [z for z in zones if z.name.casefold() == wanted]


def _default_store() -> ZoneStore:
    cache_dir = Path(os.environ.get("CACHE_DIR", "data/cache"))
    ttl = timedelta(seconds=int(os.environ.get("FEED_TTL_SECONDS", "3600")))
    return ZoneStore(partial(ndw_feed.fetch, ZONES_URL, cache_dir), ttl=ttl)


def create_app(
    store: ZoneStore | None = None,
    rdw: RdwClient | None = None,
    clock: Clock = lambda: datetime.now(UTC),
) -> FastAPI:
    zone_store = store or _default_store()
    rdw_client = rdw or RdwClient()
    app = FastAPI(
        title="zonecheck",
        version="0.1.0",
        description=(
            "Can licence plate X enter Dutch low- or zero-emission zone Y? "
            "Answers come from the NDW emission-zone feed plus RDW open data. "
            + DISCLAIMER
        ),
    )

    def zones_or_503() -> tuple[ZoneFeed, ndw_feed.FeedSnapshot]:
        try:
            return zone_store.get()
        except (ndw_feed.FeedError, ValueError) as exc:
            raise HTTPException(503, f"emission-zone feed unavailable: {exc}") from exc

    index_html = Path(__file__).with_name("static").joinpath("index.html").read_text()

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return index_html

    @app.get("/health", response_model=Health)
    def health() -> Health | JSONResponse:
        try:
            feed, snapshot = zone_store.get()
        except (ndw_feed.FeedError, ValueError) as exc:
            body = Health(status="unavailable", detail=str(exc))
            return JSONResponse(body.model_dump(mode="json"), status_code=503)
        return Health(
            status="ok", zones=len(feed.zones), feed=_feed_info(feed, snapshot)
        )

    @app.get("/zones", response_model=ZoneList)
    def list_zones() -> ZoneList:
        feed, snapshot = zones_or_503()
        return ZoneList(
            feed=_feed_info(feed, snapshot),
            count=len(feed.zones),
            zones=[_summary(z) for z in feed.zones],
        )

    @app.get("/zones/{zone_id}.geojson")
    def zone_geojson(zone_id: str) -> JSONResponse:
        feed, _ = zones_or_503()
        zone = next((z for z in feed.zones if z.id == zone_id), None)
        if zone is None:
            raise HTTPException(404, f"no zone with id {zone_id!r}")
        if not zone.polygons:
            raise HTTPException(404, f"zone {zone_id!r} has no geometry in the feed")
        body = {
            "type": "Feature",
            "id": zone.id,
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[list(point) for point in ring] for ring in polygon]
                    for polygon in zone.polygons
                ],
            },
            "properties": {
                **_summary(zone).model_dump(mode="json"),
                "feed_publication_time": (
                    feed.publication_time.isoformat() if feed.publication_time else None
                ),
                "source": SOURCES[0],
            },
        }
        return JSONResponse(body, media_type="application/geo+json")

    @app.get("/access", response_model=AccessResponse)
    def access(
        kenteken: Annotated[str, Query(description="Registration, e.g. AB-123-C")],
        zone: Annotated[str, Query(description="Zone id, city, or zone name")],
    ) -> AccessResponse:
        try:
            plate = normalise_kenteken(kenteken)
        except InvalidKentekenError as exc:
            raise HTTPException(422, str(exc)) from exc
        feed, snapshot = zones_or_503()
        zones = match_zones(feed.zones, zone)
        if not zones:
            cities = sorted({z.city for z in feed.zones if z.city})
            raise HTTPException(
                404, {"detail": f"no zone matches {zone!r}", "cities": cities}
            )
        try:
            vehicle = rdw_client.lookup(plate)
        except RdwError as exc:
            raise HTTPException(502, str(exc)) from exc
        now = clock()
        results = []
        for z in zones:
            decision = decide(z, vehicle, now)
            results.append(
                ZoneAccess(
                    zone=_summary(z),
                    result=decision.result,
                    reason=decision.reason,
                    allowed_until=decision.allowed_until,
                    deciding_conditions=[
                        DecidingCondition(
                            condition_id=leaf.condition_id,
                            readable=leaf.readable,
                            value=leaf.value,
                            vehicle_fact=leaf.fact,
                            in_exemption=leaf.in_exemption,
                            raw_xml=leaf.raw,
                        )
                        for leaf in decision.deciding_conditions
                    ],
                    rule_readable=list(decision.rule_readable),
                )
            )
        overall = min((r.result for r in results), key=_ORDER.__getitem__)
        return AccessResponse(
            kenteken=plate,
            zone_query=zone,
            result=overall,
            evaluated_at=now,
            zones=results,
            vehicle=_vehicle_facts(plate, vehicle, now),
            feed=_feed_info(feed, snapshot),
            sources=SOURCES,
            disclaimer=DISCLAIMER,
        )

    @app.exception_handler(HTTPException)
    def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        return JSONResponse(detail, status_code=exc.status_code)

    return app


app = create_app()
