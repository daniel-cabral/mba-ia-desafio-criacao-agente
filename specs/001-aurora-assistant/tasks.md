---
description: "Task list for Residencial Aurora Assistant"
---

# Tasks: Residencial Aurora Assistant

**Input**: Design documents from `specs/001-aurora-assistant/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Only the two offline tests named in plan.md (storage exclusivity, output filter). The
evaluator flow (E1..E15) is the acceptance check, run against the live API.

**Organization**: grouped by user story (spec.md US1..US7). E-numbers are evaluator steps.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: user story from spec.md

---

## Interfaces (fixed signatures, binding for all tasks)

`src/aurora/config.py`
- `ROOT_DIR: Path`, `DADOS_DIR: Path` (`ROOT_DIR / "dados"`), `DB_PATH: Path` (`ROOT_DIR / "data" / "aurora.db"`), `DB_URL: str` (`f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"`)
- `MODEL: str = "gemini-3.8-flash"`, `APP_NAME: str = "aurora"`, `USER_ID: str = "morador"`
- `RETRY_OPTIONS: google.genai.types.HttpRetryOptions` (retries 429/503); loads `.env` on import

`src/aurora/store.py` (every function takes keyword `db: Path | None = None`, default `config.DB_PATH`, so tests pass a temp path)
- `AREAS: dict[str, dict]` (`id -> {"nome": str, "taxa": float}`), `APARTMENTS: dict[str, str]` (`numero -> morador`), loaded from `dados/` at import
- `def create_schema(db=None) -> None` (sync; creates `data/` dir, WAL, tables and index if missing)
- `def seed(db=None) -> None` (sync; drop + recreate `reservations` and `visitors`, load seed JSON)
- `async def list_reservations(apartamento: str, db=None) -> list[dict]` → `[{"codigo", "area", "data"}]`, active only
- `async def is_occupied(area: str, data: str, db=None) -> bool`
- `async def insert_reservation(apartamento: str, area: str, data: str, db=None) -> str | None` → new code `AUR-{id:04d}`, or `None` when the partial unique index rejects it (`IntegrityError` caught)
- `async def cancel_reservation(apartamento: str, *, codigo: str | None = None, area: str | None = None, data: str | None = None, db=None) -> str | None` → cancelled code, or `None` if no active reservation of that apartment matches
- `async def insert_visitor(apartamento: str, nome: str, data: str, db=None) -> None`
- `async def list_visitors(apartamento: str, db=None) -> list[dict]` → `[{"nome", "data"}]`
- `async def foreign_data(apartamento: str, db=None) -> tuple[list[str], list[str]]` → (`terms`: reservation codes of any status, visitor names and resident names of other apartments; `numbers`: other apartment numbers)

`src/aurora/regulation.py`
- `CHAPTERS: dict[str, dict]` (`"I".."XIV" -> {"titulo": str, "texto": str}`, insertion order), parsed at import
- `def chapter_index() -> str` (one line per chapter, `"IV: Piscina"`)
- `def get_chapter(chapter_id: str) -> dict | None`

`src/aurora/output_filter.py`
- `def redact(text: str, terms: list[str], numbers: list[str]) -> str` (pure; terms replaced literally, numbers only when standalone: not adjacent to a digit, letter or `-`; replacement `[dado restrito]`)
- `async def redact_other_apartments(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None` (reads `callback_context.state["apartamento"]`, calls `store.foreign_data`, rewrites text parts only, returns `None` when nothing changed)

`src/aurora/confirmations.py`
- `def pending(session: Session) -> list[dict]` → `[{"id", "acao", "detalhes"}]`
- `def answer_content(confirmation_id: str, confirmed: bool) -> google.genai.types.Content`

`src/aurora/tools.py`: async tools named as in `contracts/api.md`, each last param `tool_context: ToolContext`, each returning a `dict`
`src/aurora/agents.py`: `root_agent: LlmAgent`
`src/aurora/api.py`: `app: FastAPI`, `def main() -> None`
`src/aurora/restore.py`: `def main() -> None` (`create_schema()`, `seed()`, then delete all sessions of `APP_NAME`/`USER_ID` via `DatabaseSessionService`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: project skeleton and the go/no-go spike

- [x] T001 Create `pyproject.toml` with uv: `requires-python = ">=3.12"`, deps `google-adk[db]==2.13.0`, `fastapi`, `uvicorn`, `aiosqlite`, `python-dotenv`, dev dep `pytest`; package `src/aurora/`; scripts `aurora-api = "aurora.api:main"` and `aurora-restore = "aurora.restore:main"`; run `uv lock` to create `uv.lock`
- [x] T002 [P] Create `.env.example` with `GEMINI_API_KEY=` (no value); add `data/` to `.gitignore`
- [x] T003 Spike (throwaway, in the session scratchpad, NOT in the repo): one root agent + one sub_agent on `gemini-3.8-flash`, one tool calling `tool_context.request_confirmation(hint=, payload=)`, `DatabaseSessionService("sqlite+aiosqlite:///...")`; pause, build a NEW Runner + session service, send `FunctionResponse(name="adk_request_confirmation", id=<confirmation call id>, response={"confirmed": True})` alone; PASS = tool executes once, no 400 from Gemini, resend executes nothing. Also: two confirmations pending from one message, answered one at a time (each executes once, the other stays pending), and a pending confirmation that survives a new text message and is approved afterwards (FR-012b). Gate: stop and report if it fails

**Checkpoint**: spike PASS before Phase 2

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: storage, sessions, API skeleton, confirmation plumbing used by every story

- [x] T004 Implement `src/aurora/config.py`: load `.env`, constants `MODEL = "gemini-3.8-flash"`, `APP_NAME`, fixed `USER_ID`, paths `dados/` and `data/aurora.db`, `DB_URL` (absolute, see Interfaces), Gemini HTTP retry options for 429/503 (plan rule 7)
- [x] T005 Implement `src/aurora/store.py`: `create_schema()` (WAL, `busy_timeout`); table `reservations` (`id INTEGER PRIMARY KEY AUTOINCREMENT`, `codigo TEXT UNIQUE NOT NULL`, `apartamento TEXT NOT NULL`, `area TEXT NOT NULL`, `data TEXT NOT NULL`, `status TEXT NOT NULL` in `ativa|cancelada`) with partial unique index `(area, data) WHERE status = 'ativa'`; table `visitors` (`id`, `apartamento`, `nome`, `data`, all NOT NULL); seed loaders for `dados/*.json` (read only); queries: active reservations by apartment, area/date occupied (bool only), insert reservation returning `AUR-{id:04d}` or a refusal on `IntegrityError`, cancel own reservation by code or area+date, insert/list visitors; every query function is `async` and wraps `sqlite3` in `asyncio.to_thread` (plan rule 2); `create_schema` and `seed` are sync (startup/restore only); exact signatures in "Interfaces" above
- [x] T006 Implement `src/aurora/restore.py` `main()`: drop and recreate `reservations` and `visitors` (resets AUTOINCREMENT), load seed from `dados/`, delete all ADK sessions of `APP_NAME`
- [x] T007 Implement `src/aurora/confirmations.py`: `pending(session)` = `adk_request_confirmation` calls in `session.events` with no later function response of the same id, mapped to `{"id", "acao", "detalhes"}` from `args.toolConfirmation.payload`; `answer_content(id, confirmed)` building a Content with only `FunctionResponse(name="adk_request_confirmation", id=id, response={"confirmed": confirmed})`
- [x] T008 Implement `src/aurora/agents.py`: root `LlmAgent` `aurora` (PT-BR, routes to specialists, no regulation text) with `sub_agents` list ready for specialists added per story
- [x] T009 Implement `src/aurora/api.py`: lifespan calls `store.create_schema()` only (never seeds, plan rule 4); `DatabaseSessionService(DB_URL)`; Runner over `agents.root_agent`; per-session `asyncio.Lock`; routes per `contracts/api.md`: `POST /sessoes` (201, `state={"apartamento": ...}`), `POST /sessoes/{id}/mensagens`, `POST /sessoes/{id}/confirmacoes` (409 when id not in `confirmations.pending`, before calling the Runner), `GET /sessoes/{id}/eventos` (`event.model_dump(mode="json")`, in order), `GET /apartamentos/{n}/reservas`, `GET /apartamentos/{n}/visitantes`; `404` for unknown session, checked before the `409` check; `resposta` = final text of the run; `main()` runs uvicorn on `localhost:8000`

**Checkpoint**: `uv run aurora-restore` + `uv run aurora-api` pass E1 and E2

---

## Phase 3: User Story 1 - Resident manages own reservations (P1) 🎯 MVP

**Goal**: book, cancel and list own reservations; fee areas only after confirmation

**Independent Test**: E5, E6, E7, E8, E9

- [x] T010 [US1] Add reservation tools in `src/aurora/tools.py`: `verificar_disponibilidade(area, data)` → only `livre`/`ocupada`; `listar_minhas_reservas()`; `reservar_area(area, data)`: validate area id and `AAAA-MM-DD`, check availability first (occupied → refusal, no confirmation, FR-012a), fee 0 → insert, fee > 0 → `request_confirmation(payload={"acao": "reservar_area", "detalhes": {"area", "data"}})` with `skip_summarization`, on re-run insert only if `tool_confirmation.confirmed`, denial → no write; `cancelar_reserva(codigo=None, area=None, data=None)` own apartment only, not found → "não encontrada entre as suas reservas"; apartment always from `tool_context.state["apartamento"]`, no apartment argument
- [x] T011 [US1] Add specialist `reservas` in `src/aurora/agents.py` with the T010 tools; instruction: reply in PT-BR, call the action tool directly, never ask "você confirma?" in chat (plan rule 6); register in root `sub_agents`
- [x] T012 [P] [US1] `tests/test_store.py::test_concurrent_insert_same_area_date` — Test: new, because distinct contract (write-time exclusivity, the only lock on G5 below the API): two concurrent `store` inserts for `salao-de-festas`/`2030-05-11` → exactly one active row, the other a refusal, no exception; plus a cancelled row keeps its code and a new insert gets a different code (literal expected codes)
- [ ] T013 [US1] Run E5..E9 against the live API and fix until they pass

**Checkpoint**: US1 works end to end

---

## Phase 4: User Story 2 - Session cannot reach other apartments (P1)

**Goal**: no data of other apartments in responses or events

**Independent Test**: E3, E4, E10

- [x] T014 [US2] Implement `src/aurora/output_filter.py` `after_model_callback`: rewrite text parts only (never `function_call` args); load from the DB on every call the reservation codes (any status), visitor names and resident names of apartments other than `state["apartamento"]`, plus other apartment numbers matched standalone (not inside other numbers or codes); replace each with `[dado restrito]` (plan rule 5)
- [x] T015 [US2] Attach the callback to root and every specialist in `src/aurora/agents.py`
- [x] T016 [P] [US2] `tests/test_output_filter.py::test_redacts_other_apartments` — Test: new, because distinct contract (redaction rules): one parametrised test of `redact(text, terms=["RSV-4821", "Marina Duarte"], numbers=["302"])` over literal cases: `RSV-4821` and `Marina Duarte` replaced by `[dado restrito]`; standalone `302` replaced; `2030-03-02`, `AUR-0302` and `101` kept (callback wiring and function_call untouched-ness are covered by live E3/E4/E10, not here)
- [ ] T017 [US2] Run E3, E4, E10 and fix until they pass

**Checkpoint**: US1 + US2 pass

---

## Phase 5: User Story 3 - Visitor authorization only with confirmation (P1)

**Goal**: authorize visitors only via the confirmation route

**Independent Test**: E11

- [x] T018 [US3] Add visitor tools in `src/aurora/tools.py`: `listar_meus_visitantes()`; `autorizar_visitante(nome, data)` always via `request_confirmation(payload={"acao": "autorizar_visitante", "detalhes": {"nome", "data"}})`, insert only if confirmed; apartment from state
- [x] T019 [US3] Add specialist `visitantes` in `src/aurora/agents.py` (same instruction rules as T011: PT-BR, no chat confirmation; callback attached); register in root
- [ ] T020 [US3] Run E11 and fix until it passes

---

## Phase 6: User Story 7 - Operator setup and restore (P1)

**Goal**: clean clone to running API with documented commands

**Independent Test**: E1 from a fresh clone

- [ ] T021 [US7] In a fresh local clone (`git clone <repo path> <scratchpad dir>`, after committing the work so far): copy `.env.example` to `.env`, `uv sync`, `uv run aurora-restore`, `uv run aurora-api`; check E1; then modify data, rerun restore and confirm seed state

---

## Phase 7: User Story 4 - Regulation answered from the rules (P2)

**Goal**: answers from one whole chapter; nothing else enters events

**Independent Test**: E12

- [x] T022 [US4] Implement `src/aurora/regulation.py`: parse `dados/regulamento.md` by `## Capítulo` headings into 14 chapters `{id (I..XIV), titulo, texto}` at import
- [x] T023 [US4] Add tool `consultar_regulamento(capitulo)` in `src/aurora/tools.py`: id validated against the parsed set, returns that chapter only (plan rule 3)
- [x] T024 [US4] Add specialist `regulamento` in `src/aurora/agents.py`: chapter ids and titles in its `instruction` only (not `description`), reply in PT-BR, callback attached; register in root; confirm root instruction has no regulation text
- [ ] T025 [US4] Run E12: closing time 20h on Sundays; events contain only Chapter IV text

---

## Phase 8: User Story 5 - Nothing lost on restart (P2)

**Goal**: sessions, pending confirmations and data survive restart

**Independent Test**: E13

- [ ] T026 [US5] Run E13 (stop with Ctrl+C, same start command, no restore); also leave a confirmation pending, restart, approve, confirm single execution (constitution, Technical Constraints)

---

## Phase 9: User Story 6 - Two residents, one reservation (P2)

**Goal**: exactly one reservation under concurrent approvals

**Independent Test**: E14

- [x] T027 [US6] Stress offline, outside the repo, with the fake-LLM harness from research (`scratchpad/adk-src/probe.py` adapted to the real tools and DB): 20+ rounds of two concurrent approvals for the same area/date → always one reservation, both `200`, no "database is locked"; if it fails, apply the research R6 fallback (split DB files) with a PATCH amendment to the constitution
- [ ] T028 [US6] Run E14 with two `curl` approvals joined by `&`

---

## Phase 10: Polish & Cross-Cutting Concerns

- [x] T029 [P] Write `scripts/evaluator_flow.py`: runs E1..E14 via HTTP against `localhost:8000` and prints each check (restart in E13 done by hand, script pauses)
- [x] T030 Replace `README.md` with sections Arquitetura (each agent, responsibility, how invoked, why transfer and not AgentTool), Garantias (G1..G5: file + excerpt + why it does not depend on the model), Como rodar (prerequisites, `GEMINI_API_KEY`, `uv sync`, `uv run aurora-restore`, `uv run aurora-api`); every reference must point to existing code
- [x] T031 Remove the Sync Impact Report comment from `.specify/memory/constitution.md`
- [x] T032 Verify `dados/` is identical to upstream (`git diff upstream/main -- dados/` empty), no key versioned (`git ls-files` has no `.env`), `uv.lock` committed, ADK pinned
- [ ] T033 Full run: `uv run pytest`, then `aurora-restore` and the complete evaluator flow E1..E15 in one pass, recording the total model calls (SC-007); commit in PT-BR on `main` and push to the fork

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (T003 spike gates everything)
- Phase 2 → all stories
- US1 → US2 (filter validated on reservation flows) → US3
- US7 after US1..US3 (needs something to run); US4 independent after Phase 2
- US5 and US6 after US1 + US3 (need confirmations and data)
- Polish last; T033 is the final gate

## Parallel Opportunities

- T002 with T001
- T012 with T010/T011 (different files)
- T016 with T014/T015
- T022 with any US1..US3 task (separate file)
- T029 with Phases 7..9

## Implementation Strategy

1. Setup + spike, Foundational → E1/E2 green
2. US1 (MVP) → E5..E9
3. US2, US3 → E3, E4, E10, E11
4. US7, US4, US5, US6 → E1 clean clone, E12, E13, E14
5. Polish → README, full flow, push
