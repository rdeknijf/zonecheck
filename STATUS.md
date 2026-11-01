# STATUS

Attention: focus

## Goal

A free public JSON API that answers "can licence plate X enter Dutch low- or zero-emission zone Y?" from NDW plus RDW open data. V1 runs locally only: no name, no repository remote, no deployment.

## Verified state (2026-11-01)

- 135 offline tests pass, coverage 94.0%. ruff, ty and `prek run --all-files` are clean.
- Live run against the real feeds: `/health` reports 42 zones, NDW publication time 2026-10-31T06:00:00Z. `/access` answers match a manual reading of the XML for the checked plates: 27GHTF (Euro 3 diesel Golf) `not_allowed` in Milieuzone Amsterdam; G590ZD (Euro 6 diesel) `allowed`; V68GJD (Euro 6 diesel N1) `allowed` in ZE Utrecht until 2027-12-31T23:00Z; 27BHRX (diesel camper) `unknown`.
- `docker build` succeeds. The container answers `/health` with the live feed (42 zones), and `/access?kenteken=27-GH-TF&zone=Amsterdam` gives `not_allowed` for Milieuzone Amsterdam and `allowed` for ZE Amsterdam.
- Every rule element in the current feed is encoded (see `docs/ndw-rules.md`). Leaves that stay unknown: owner type (not in RDW open data) and special-purpose vehicles that RDW registers as one.

## How to run

```sh
uv sync
uv run uvicorn ndw_zones.main:app --port 8011
curl "http://127.0.0.1:8011/access?kenteken=27-GH-TF&zone=Amsterdam"
```

## Open decisions (Rutger)

- Project name, and with it the package name (`ndw_zones` is a placeholder), repository and domain.
- Feed scope wider than the exemption set: the feed makes every diesel passenger car `not_allowed` in LEZ Breda 26072026, Milieuzone Maastricht, LEZ Delft, LEZ Rijswijk and LEZ Leiden, and every diesel N-category vehicle `not_allowed` in LEZ Haarlem. The service follows the feed. Options: keep it, flag these zones in the answer, or report the data to NDW.
- Whether to add beads (`bd init`) for this project. Not done, so no task list exists yet.

## Resume path

Read `AGENTS.md`, then `docs/ndw-rules.md`. Run `uv run pytest`. Check the live feed with the run commands above.
