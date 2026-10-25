# Implementation Plan: Residencial Aurora Assistant

**Branch**: `main` (spec dir `001-aurora-assistant`) | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-aurora-assistant/spec.md`

## Summary

FastAPI service exposing the exact challenge contract over a Google ADK assistant: root agent
`aurora` transfers to specialists `reservas`, `visitantes`, `regulamento`. Business rules and the
five guarantees live in tools, an output callback, the API layer and SQLite constraints. Tool
confirmation uses `request_confirmation`, answered by an `adk_request_confirmation` function
response that ADK routes back to the requesting specialist, verified with persisted sessions and a
simulated restart ([research.md](research.md)).

## Technical Context

**Language/Version**: Python 3.12+ (uv-managed, `requires-python = ">=3.12"`)

**Primary Dependencies**: `google-adk[db]==2.13.0`, FastAPI, uvicorn, aiosqlite, python-dotenv

**Storage**: one SQLite file `data/aurora.db`: ADK `DatabaseSessionService` tables + domain tables
`reservations`, `visitors` (stdlib `sqlite3`, WAL, `busy_timeout`)

**Testing**: pytest for offline checks of storage exclusivity and the output filter; scripted
evaluator flow (`scripts/evaluator_flow.py`) run manually against the live API

**Target Platform**: local, `http://localhost:8000`, Windows/Linux/macOS

**Project Type**: web service (single project)

**Performance Goals**: complete the evaluator flow within AI Studio quotas (tens of model calls)

**Constraints**: `dados/` immutable; no secrets in Git; replies in PT-BR

**Scale/Scope**: 6 apartments, 3 areas, a few concurrent sessions

## Constitution Check

| Principle | Status | How |
|-----------|--------|-----|
| I. Rules in code | PASS | apartment from state, confirmation in tool, unique index, output callback, 409 in API |
| II. Five guarantees | PASS | G1 R3/R4, G2 tools + R8, G3 R5, G4 R7, G5 R6 |
| III. Exact contract | PASS | [contracts/api.md](contracts/api.md) mirrors the statement |
| IV. Immutable seed | PASS | `dados/` read only; restore reloads from it |
| V. Fixed stack | PASS | Python 3.12+, uv, ADK 2.13.0 pinned, Gemini, FastAPI, single SQLite |
| VI. Minimum scope | PASS | 3 specialists, no extra features; flow run manually before done |
| VII. README | PASS | final task writes Arquitetura, Garantias, Como rodar |

Post-design re-check: PASS, no violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-aurora-assistant/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/api.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
pyproject.toml / uv.lock / .env.example
dados/                   # immutable seed
data/aurora.db           # gitignored
src/aurora/
├── config.py            # paths, model id, env loading
├── store.py             # SQLite schema, seed restore, reservation/visitor queries (G5)
├── regulation.py        # chapter parser and lookup (G4)
├── tools.py             # ADK tools; apartment from state (G2), confirmation (G1)
├── output_filter.py     # after_model_callback redaction (G2)
├── agents.py            # root + specialists
├── confirmations.py     # pending list from events, answer building (G1)
├── api.py               # FastAPI routes, Runner, session service (G3), per-session lock
└── restore.py           # `aurora-restore` entry point
scripts/evaluator_flow.py
tests/test_store.py, tests/test_output_filter.py
```

**Structure Decision**: single `src/aurora` package, one module per responsibility so the README
Garantias section can point to one file per guarantee.

## Key Flows

1. **Message**: lock session → `runner.run_async(new_message=text)` → collect final agent text →
   pending list from events → ChatResponse.
2. **Confirmation**: lock session → id not in pending list → `409` → else send
   `FunctionResponse(name="adk_request_confirmation", id, response={"confirmed": b})` alone →
   specialist tool re-runs → executes only if confirmed → ChatResponse.
3. **Reservation write**: `INSERT` under partial unique index; `IntegrityError` → refusal result,
   `200` to the client.

## Design Rules (from plan review)

1. **Spike first**: before any other build task, a real-Gemini spike (one specialist, one
   confirming tool, SQLite session, new Runner between pause and approve) MUST pass. Research
   used a fake LLM; the risk is Gemini rejecting the history (placeholder + real response for the
   same call id) with a 400.
2. **No blocking on the event loop**: tools are `async` and run every `sqlite3` call via
   `asyncio.to_thread`, with WAL and `busy_timeout`, so aiosqlite (sessions) and the domain never
   deadlock on the shared file. Stress concurrent approvals 20+ times offline with the fake-LLM
   harness before E14.
3. **G4 checked**: Sunday pool hours (Art. 22, II: 9h to 20h) are fully inside Chapter IV; no
   other chapter overrides them. Chapter titles live in the `regulamento` specialist
   `instruction`, never in its `description` (descriptions are injected into the root). Each
   lookup returns exactly one chapter by validated id; no per-turn cap (a two-subject question may
   legitimately need two chapters).
4. **Startup never seeds**: API startup only creates the schema if missing; seeding happens only
   in `aurora-restore` (otherwise RSV-1377 returns at E13).
5. **Output filter**: rewrites text parts only, never `function_call` args; loads other
   apartments' codes, visitor names and resident names from the DB on every call.
6. **Specialist instructions**: call the action tool directly; never ask "você confirma?" in chat.
   The system confirmation is the only confirmation.
7. **Model retries**: configure HTTP retry for 429/503 on the Gemini model so an overload does not
   surface as a 500.

## Risks

- Real Gemini may answer the tool's pending result instead of stopping: mitigated by
  `skip_summarization`; covered by the spike and E7/E11.
- aiosqlite + sqlite3 contention on one file during E14: rule 2; validate with E14.
- Model: `gemini-3.8-flash` for all agents (smoke-tested, see research R9).

## Complexity Tracking

No violations.
