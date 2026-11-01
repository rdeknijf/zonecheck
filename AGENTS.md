# Dutch emission-zone access API (project name pending)

Project name pending (Rutger picks it). The directory name `ndw-zones-unnamed` and the package name `ndw_zones` are placeholders. Do not name the project, register a domain, create a GitHub repository, push or deploy without Rutger.

## Mission

A small public JSON API: "can licence plate X enter Dutch low- or zero-emission zone Y?". Sources: the NDW emission-zone feed (DATEX II v3, CC0) and RDW open data (Socrata, public domain). Rutger approved the v1 build on 2026-11-01. Sister project and pattern reference: `isde-api` (same stack and layout).

## Correctness rule (most important)

A wrong `allowed` can cost a user a fine. Every decision comes from the NDW XML plus RDW facts, through three-valued (Kleene) logic in `src/ndw_zones/rules.py`. Any rule shape the parser cannot encode becomes an `Unsupported` node (`src/ndw_zones/datex.py`) and evaluates to unknown. Missing RDW data, an ambiguous category, or an unparseable Euro class gives unknown. Never add a default that turns unknown into `allowed`, and never import municipal knowledge into the code: the feed decides. `tests/test_rules.py` covers this ("Never allowed by default").

## Layout

- `src/ndw_zones/ndw_feed.py`: generic NDW feed download (conditional GET, gunzip, disk cache with timestamps, stale fallback). Reusable for other NDW feeds; nothing zone-specific.
- `src/ndw_zones/datex.py`: DATEX II controlled-zone parser into a condition tree, zone metadata and polygons.
- `src/ndw_zones/rdw.py`: RDW lookup (`m9d7-ebf2` vehicle, `8ys7-d773` fuel) and kenteken normalisation.
- `src/ndw_zones/rules.py`: fact derivation and Kleene evaluation, deciding conditions, readable rule.
- `src/ndw_zones/main.py`: FastAPI app (`/health`, `/zones`, `/zones/{id}.geojson`, `/access`).
- `docs/ndw-rules.md`: every rule shape in the feed with counts, and the encoding table.
- `tests/fixtures/`: trimmed real feed (9 zones; the zone records are kept byte-for-byte) and recorded real RDW JSON (recorded 2026-11-01).

## Stack

Python 3.15 (`.python-version`), uv with uv_build, FastAPI, httpx, pydantic, defusedxml; ruff, ty, pytest with pytest-cov and pytest-socket (network blocked in tests), prek. src layout, no `__init__.py` in `tests/`.

## Commands

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run ty check
uv run prek run --all-files
uv run prek install
uv run uvicorn ndw_zones.main:app --port 8011
docker build -t ndw-zones-unnamed:dev .
docker compose up -d --build
```

To refresh an RDW fixture: `curl -s "https://opendata.rdw.nl/resource/m9d7-ebf2.json?kenteken=XX"` and `.../8ys7-d773.json?kenteken=XX` into `tests/fixtures/rdw/XX.vehicle.json` and `XX.fuel.json`.

## State

Current verified state, open decisions and the resume path are in `STATUS.md`.
