Project name pending (Rutger picks it); working directory name is a placeholder.

# Dutch emission-zone access API

Answers "can licence plate X enter Dutch low- or zero-emission zone Y?" from the NDW emission-zone feed (`https://opendata.ndw.nu/emissiezones.xml.gz`, CC0) and RDW open data (public domain). Every answer is `allowed`, `not_allowed` or `unknown`, with the deciding NDW conditions (raw XML and readable), the RDW facts used, the feed timestamp and a disclaimer. Informational only; check the municipality.

## Endpoints

- `GET /health`: feed status and zone count.
- `GET /zones`: all zones (id, name, city, type, validity dates).
- `GET /zones/{id}.geojson`: zone geometry as a GeoJSON Feature (MultiPolygon, `[lon, lat]`).
- `GET /access?kenteken=AB-123-C&zone=Amsterdam`: `zone` is a zone id, a city (issuing municipality, `Den Haag` maps to `'s-Gravenhage`) or a zone name. A city with several zones returns one result per zone; the top-level `result` is the worst of them (`not_allowed` before `unknown` before `allowed`).

## Run

```sh
uv sync
uv run uvicorn ndw_zones.main:app --port 8011
docker compose up -d --build   # http://127.0.0.1:8011
```

Configuration: `CACHE_DIR` (default `data/cache`) keeps the last good copy of each NDW feed; `FEED_TTL_SECONDS` (default 3600) sets how often the feed is checked with a conditional GET.

The rule shapes in the feed and how each one is encoded: [docs/ndw-rules.md](docs/ndw-rules.md).
