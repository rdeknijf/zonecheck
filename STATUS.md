# STATUS

Attention: focus

## Goal

A free public JSON API that answers "can licence plate X enter Dutch low- or zero-emission zone Y?" from NDW plus RDW open data. Name and domain chosen by Rutger on 2026-11-01: `zonecheck`, https://zonecheck.deknijf.com. Public repo `rdeknijf/zonecheck`; deploy through square `context/zonecheck/` (k3s on Buckland).

## Verified state (2026-11-01)

- Live since 2026-11-01 20:30 UTC at https://zonecheck.deknijf.com (square PR #1026, image `6809d95`, namespace `zonecheck`, 1 pod, about 61Mi memory). Public checks: `/health` 200 with 42 zones; `/access` gives `not_allowed` for 27GHTF in Milieuzone Amsterdam, `allowed` for V68GJD in ZE Utrecht and for GZS88K in Rotterdam, `unknown` for 27BHRX. `/` returns 404 (bead open).
- Release: merge to `main` here, the `build` workflow pushes `ghcr.io/rdeknijf/zonecheck:<sha>`, then bump the SHA in square `context/zonecheck/infra/deployment.yaml` (see square `context/zonecheck/README.md`).
- 135 offline tests pass, coverage 94.0%. ruff, ty and `prek run --all-files` are clean.
- Live run against the real feeds: `/health` reports 42 zones, NDW publication time 2026-10-31T06:00:00Z. `/access` answers match a manual reading of the XML for the checked plates: 27GHTF (Euro 3 diesel Golf) `not_allowed` in Milieuzone Amsterdam; G590ZD (Euro 6 diesel) `allowed`; V68GJD (Euro 6 diesel N1) `allowed` in ZE Utrecht until 2027-12-31T23:00Z; 27BHRX (diesel camper) `unknown`.
- `docker build` succeeds. The container answers `/health` with the live feed (42 zones), and `/access?kenteken=27-GH-TF&zone=Amsterdam` gives `not_allowed` for Milieuzone Amsterdam and `allowed` for ZE Amsterdam.
- Every rule element in the current feed is encoded (see `docs/ndw-rules.md`). Leaves that stay unknown: owner type (not in RDW open data) and special-purpose vehicles that RDW registers as one.

## How to run

```sh
uv sync
uv run uvicorn zonecheck.main:app --port 8011
curl "http://127.0.0.1:8011/access?kenteken=27-GH-TF&zone=Amsterdam"
```

## Open decisions (Rutger)

- Feed scope wider than the exemption set: the feed makes every diesel passenger car `not_allowed` in LEZ Breda 26072026, Milieuzone Maastricht, LEZ Delft, LEZ Rijswijk and LEZ Leiden, and every diesel N-category vehicle `not_allowed` in LEZ Haarlem. The service follows the feed. Options: keep it, flag these zones in the answer, or report the data to NDW. Decision is with Rutger (Muninn bead muninn-o6y); work bead zonecheck-0qu.

## Resume path

Read `AGENTS.md`, then `docs/ndw-rules.md`. Run `bd ready` for open work. Run `uv run pytest`. Check the live feed with the run commands above.
