# Research: Residencial Aurora Assistant

Source: google-adk 2.13.0 installed source plus offline runs with a scripted fake LLM (16
combinations: in-memory/SQLite, transfer flags on/off, resumability on/off, new Runner between
pause and approval). Paths are relative to `site-packages/google/adk/`.

## R1. ADK version

- **Decision**: `google-adk[db]==2.13.0` (latest stable on PyPI, 2026-10-23).
- **Rationale**: series 2, >= 2.2.0, exact pin required. The `[db]` extra brings SQLAlchemy, which
  `DatabaseSessionService` needs; `aiosqlite` alone fails.
- **Alternatives**: 2.2.0 (course version); rejected, the challenge reports routing changes between
  versions and 2.13.0 is the version we verified.

## R2. Agent topology

- **Decision**: root `LlmAgent` `aurora` with `sub_agents=[reservas, visitantes, regulamento]`,
  transfer-based. No `AgentTool`. No App resumability config.
- **Rationale**: on a user function response the router always routes to the author of the
  matching call (`flows/llm_flows/core/_resume.py:295`, `agents/_agent_router.py:186-222`), so the
  confirmation reaches the specialist that asked, whatever the transfer flags or session service.
  `AgentTool` drops the nested session and cannot resume a confirmation
  (`tools/agent_tool.py:409-424`).
- **Alternatives**: AgentTool specialists (rejected: confirmation never surfaces); single agent
  (rejected: challenge requires >= 2 specialists).
- **Transfer flags**: specialists keep the default (may transfer back to root/peers) so a follow-up
  message on another subject works.

## R3. Confirmation mechanism

- **Decision**: manual `tool_context.request_confirmation(hint=, payload={"acao", "detalhes"})`
  inside the tool, with `skip_summarization` on the pending turn; on re-run the tool checks
  `tool_context.tool_confirmation.confirmed` and executes only when true.
- **Rationale**: lets the tool check availability before asking (FR-012a), puts our own `acao`/
  `detalhes` in the payload, and returns a custom denial. The pending event is the
  `adk_request_confirmation` function call, authored by the specialist, with
  `args.toolConfirmation.payload` (`flows/llm_flows/tools/_functions.py:205-247`).
- **Client answer**: a message holding only
  `FunctionResponse(name="adk_request_confirmation", id=<confirmation call id>,
  response={"confirmed": bool})` (`flows/llm_flows/tools/_confirmation.py:280-297`). Mixing text
  and function responses raises `ValueError` (`runners.py:646-659`).
- **Alternatives**: `FunctionTool(require_confirmation=True)` (rejected: generic hint/payload, no
  pre-check before asking).

## R4. Pending list and 409

- **Decision**: the API derives pending confirmations from `session.events`: every
  `adk_request_confirmation` call whose id has no later function response. The confirmation route
  returns `409` before calling the Runner when the id is not in that set.
- **Rationale**: single source of truth, persisted with the session. ADK itself ignores a resent
  answer (`_confirmation.py:302-355`), and our check also blocks unknown ids. A per-session
  `asyncio.Lock` serializes requests in one session.
- **Alternatives**: separate pending table (rejected: duplicates state that ADK already persists).

## R5. Session persistence

- **Decision**: `DatabaseSessionService("sqlite+aiosqlite:///data/aurora.db")`, fixed `app_name`
  and `user_id`; apartment stored in `state["apartamento"]` at `create_session`.
- **Rationale**: the v1 schema stores the full `event.model_dump` (`sessions/schemas/v1.py:222`),
  so `long_running_tool_ids` and `requested_tool_confirmations` survive restart (verified).
  State set at creation is readable via `tool_context.state` after restart (verified). Fixed
  `user_id` allows lookup by `session_id` alone for the `404` check.

## R6. Domain storage and exclusivity

- **Decision**: same SQLite file, stdlib `sqlite3`, WAL mode and `busy_timeout`. Table
  `reservations` with `id INTEGER PRIMARY KEY AUTOINCREMENT`, `codigo UNIQUE`, and partial unique
  index `ON reservations(area, data) WHERE status = 'ativa'`. Insert catches `IntegrityError` and
  returns a normal refusal.
- **Rationale**: exclusivity enforced by the database at write time (G5). `AUTOINCREMENT` never
  reuses ids, so `AUR-{id:04d}` never repeats while cancelled rows are kept (rule 5).
- **Risk**: aiosqlite (sessions) and sqlite3 (domain) writing the same file at once. Mitigated by
  WAL, `busy_timeout` and running every `sqlite3` call in `asyncio.to_thread` (a sync call on the
  event loop could block aiosqlite's commit and deadlock). Validated offline under stress, then
  by E14.
- **Alternatives**: separate `sessions.db` and `domain.db` (rejected for now: constitution V says
  single SQLite; fallback if stress fails, via PATCH amendment).

## R7. Regulation

- **Decision**: parse `dados/regulamento.md` by `## Capítulo` headings into 14 chapters at startup.
  The `regulamento` specialist instruction lists ids and titles only; tool
  `consultar_regulamento(capitulo)` validates the id in code and returns that chapter's text.
- **Rationale**: only one whole, relevant chapter enters the events (G4). The root instruction has
  no regulation text.

## R8. Output filter

- **Decision**: `after_model_callback` on every agent rewrites model text, replacing other
  apartments' reservation codes, visitor names, resident names and apartment numbers (standalone,
  not inside other numbers or codes). The rewritten response is what gets persisted (verified).
- **Rationale**: defense in depth for FR-014 and E10 ("302" standalone).

## R9. Model

- **Decision**: `gemini-3.8-flash` for all agents, set in a single constant. Key env var:
  `GEMINI_API_KEY`.
- **Rationale**: smoke test (2 runs each, injection-style prompt with one declared tool):
  3.8-flash 2/2 correct calls, ~4s; 3.5-flash-lite 2/2, ~1s; 3.5-flash hallucinated undeclared
  tools once; 2.5-flash answered in text only once.
- **Alternatives**: 3.5-flash-lite (faster, too little evidence on routing/injection); mixed models
  (two models to validate).

## Not verified yet (validate in implementation)

- Real Gemini behavior (research used a fake LLM).
- Two confirmations pending in the same invocation.
