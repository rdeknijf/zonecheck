# zonecheck

Public repo `rdeknijf/zonecheck`, live at https://zonecheck.deknijf.com (name and domain chosen by Rutger, 2026-11-01). Deploy: square `context/zonecheck/` (k3s on Buckland, image SHA pinned, Flux reconciles); see `STATUS.md`.

## Mission

A small public JSON API: "can licence plate X enter Dutch low- or zero-emission zone Y?". Sources: the NDW emission-zone feed (DATEX II v3, CC0) and RDW open data (Socrata, public domain). Rutger approved the v1 build on 2026-11-01. Sister project and pattern reference: `isde-api` (same stack and layout).

## Correctness rule (most important)

A wrong `allowed` can cost a user a fine. Every decision comes from the NDW XML plus RDW facts, through three-valued (Kleene) logic in `src/zonecheck/rules.py`. Any rule shape the parser cannot encode becomes an `Unsupported` node (`src/zonecheck/datex.py`) and evaluates to unknown. Missing RDW data, an ambiguous category, or an unparseable Euro class gives unknown. Never add a default that turns unknown into `allowed`, and never import municipal knowledge into the code: the feed decides. `tests/test_rules.py` covers this ("Never allowed by default").

## Layout

- `src/zonecheck/ndw_feed.py`: generic NDW feed download (conditional GET, gunzip, disk cache with timestamps, stale fallback). Reusable for other NDW feeds; nothing zone-specific.
- `src/zonecheck/datex.py`: DATEX II controlled-zone parser into a condition tree, zone metadata and polygons.
- `src/zonecheck/rdw.py`: RDW lookup (`m9d7-ebf2` vehicle, `8ys7-d773` fuel) and kenteken normalisation.
- `src/zonecheck/rules.py`: fact derivation and Kleene evaluation, deciding conditions, readable rule.
- `src/zonecheck/main.py`: FastAPI app (`/health`, `/zones`, `/zones/{id}.geojson`, `/access`).
- `docs/ndw-rules.md`: every rule shape in the feed with counts, and the encoding table.
- `tests/fixtures/`: trimmed real feed (11 zones; the zone records are kept byte-for-byte) and recorded real RDW JSON (recorded 2026-11-01).

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
uv run uvicorn zonecheck.main:app --port 8011
docker build -t zonecheck:dev .
docker compose up -d --build
```

To refresh an RDW fixture: `curl -s "https://opendata.rdw.nl/resource/m9d7-ebf2.json?kenteken=XX"` and `.../8ys7-d773.json?kenteken=XX` into `tests/fixtures/rdw/XX.vehicle.json` and `XX.fuel.json`.

## State

Current verified state, open decisions and the resume path are in `STATUS.md`.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:1105d646 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
