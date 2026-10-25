# Data Model: Residencial Aurora Assistant

Single SQLite file `data/aurora.db` (gitignored). ADK owns its session tables; the domain tables
below are owned by the app.

## Seed (read-only, from `dados/`)

- **Apartment** (`apartamentos.json`): `numero`, `morador`. Loaded in memory.
- **Area** (`areas.json`): `id`, `nome`, `taxa`. `taxa > 0` → charge → confirmation.
- **Regulation chapter** (`regulamento.md`): `id` (I..XIV), `titulo`, `texto`. Loaded in memory.

## reservations

| Column | Type | Rules |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | never reused |
| codigo | TEXT UNIQUE NOT NULL | seed codes kept; new = `AUR-{id:04d}` |
| apartamento | TEXT NOT NULL | always the session's apartment |
| area | TEXT NOT NULL | must be an `areas.json` id |
| data | TEXT NOT NULL | `AAAA-MM-DD`, validated |
| status | TEXT NOT NULL | `ativa` or `cancelada` |

- Partial unique index: `(area, data) WHERE status = 'ativa'` (rule 1, G5).
- Transition: `ativa → cancelada` only by the owner apartment; no delete (rule 5).

## visitors

| Column | Type | Rules |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| apartamento | TEXT NOT NULL | always the session's apartment |
| nome | TEXT NOT NULL | non-empty |
| data | TEXT NOT NULL | `AAAA-MM-DD`, validated |

## Session (ADK)

- `state["apartamento"]` set once at creation; tools read it, never write it.
- Events: the full ordered history; source of the pending confirmations.

## Pending confirmation (derived, not stored)

- An `adk_request_confirmation` function call in the session events with no later function
  response of the same id.
- Exposed as `{"id": call.id, "acao": payload.acao, "detalhes": payload.detalhes}`.
- States: pending → answered (approved/denied). Answered or unknown id → `409`.

## Restore

- Drops and recreates `reservations` and `visitors` (resets AUTOINCREMENT), reloads the seed and
  deletes all ADK sessions. Codes stay unique among stored reservations (FR-005): after a restore
  no earlier `AUR-*` reservation exists.
