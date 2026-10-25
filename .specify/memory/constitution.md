# Residencial Aurora Assistant Constitution

Source of truth: the challenge statement (original `README.md`, upstream
`devfullcycle/mba-ia-desafio-criacao-agente`). When this constitution and the statement
disagree, the statement wins and this file MUST be amended.

## Core Principles

### I. Rules Live in Code, Not in the Prompt

The model decides the path; the code decides what is allowed. Every business rule and every
guarantee MUST be enforced by tools, callbacks, the API layer or the database. Prompt instructions
MAY guide behavior but MUST NOT be the only barrier against any violation. No user message
("I am from 302", "I already confirmed", "ignore previous instructions") can change an outcome.

### II. The Five Guarantees (NON-NEGOTIABLE)

1. **Confirmation**: any action that charges a fee (area with `taxa > 0`) or grants building access
   (visitor authorization) stays pending until `POST /sessoes/{id}/confirmacoes` answers it. Pending
   items appear in `confirmacoes_pendentes` with details. Approve executes exactly once; deny changes
   nothing; any id not pending in that session (unknown or already answered) returns `409` and
   executes nothing. Fee-free, access-free actions MUST NOT ask for confirmation.
2. **Session owns the apartment**: the apartment is set once at session creation and stored in session
   state. Tools MUST read it from the session; no tool accepts a model-chosen apartment without
   validating it against the session. Data of other apartments (codes, names, numbers) MUST NOT reach
   responses or session events; availability checks expose only free/occupied.
3. **Nothing lost on restart**: sessions, events, reservations and visitors persist across API
   restarts; the same session resumes with prior events and accepts new messages, including pending
   confirmations.
4. **Regulation consulted, not loaded**: the root agent MUST NOT receive the regulation in its
   instructions. Answers come from `dados/regulamento.md` through retrieval scoped to the relevant
   chapter; no session event may contain text from unrelated chapters.
5. **One reservation per area/date**: exclusivity MUST hold at write time (database constraint or
   atomic write), not only via a prior check. Under concurrent approvals one wins and the other gets a
   normal `200` refusal, never a server error. Reservation codes are system-generated and never reused,
   including codes of cancelled reservations.

### III. Exact API Contract

Routes, fields, JSON shapes and status codes MUST match the statement exactly: `POST /sessoes` (201),
`POST /sessoes/{id}/mensagens` (200), `POST /sessoes/{id}/confirmacoes` (200/409),
`GET /sessoes/{id}/eventos` (200, full ordered events), `GET /apartamentos/{n}/reservas`,
`GET /apartamentos/{n}/visitantes`; `404` for unknown sessions; API on `http://localhost:8000`.
Verification routes read storage directly, never through the model.

### IV. Immutable Seed Data

Files under `dados/` MUST stay byte-identical to upstream. They are the initial state only; all
mutations go to storage. A documented restore command resets reservations and visitors to them.

### V. Fixed Stack

Python 3.12+ managed by uv (`pyproject.toml` and `uv.lock` versioned); `google-adk` series 2,
>= 2.2.0, exact version pinned; Gemini models via Google AI Studio key; FastAPI; a single SQLite
database for ADK sessions and domain data (no external service). No secret is versioned: `.env` is
ignored, `.env.example` lists variable names without values.

### VI. Minimum Scope

Build only what the statement asks. No UI, auth, payments, date/capacity rules or speculative
abstractions. One root agent plus at least two specialists; reservations and visitors are read and
written only through tools. Automated tests are out of the grader's scope, but the full evaluator
flow (steps 1 to 15) MUST be executed manually against persisted sessions, including after a restart,
before the work is declared done.

### VII. Deliverable README

The final `README.md` replaces the statement and has exactly the sections Arquitetura (each agent,
responsibility, how it is invoked and why), Garantias (for each guarantee, the file and code excerpt
that implements it and why it does not depend on the model) and Como rodar (prerequisites, `.env`
variables, start command, restore command). Every reference MUST point to code that exists.

## Technical Constraints

- Code, identifiers, comments and specs in English; assistant replies to residents in PT-BR;
  commits and PRs in PT-BR.
- Confirmation resume MUST be validated with the persisted SQLite session service and after an API
  restart, never only in memory or in `adk web`.
- Model choice per agent is free; keep total calls compatible with AI Studio limits (tens of calls
  per evaluator flow).

## Development Workflow

- Spec Kit flow: specify → clarify (if needed) → plan → tasks → implement; artifacts are versioned.
- Every spec and plan MUST trace each requirement to a statement section or evaluator step.
- Everything ships on branch `main` of the public fork.

## Governance

This constitution supersedes other project practices. Amendments require updating this file, a
version bump (MAJOR: principle removed or redefined; MINOR: principle or section added; PATCH:
wording) and a check that specs and plans still comply. Every plan MUST include a Constitution Check
against Principles I to VII.

**Version**: 1.0.0 | **Ratified**: 2026-10-25 | **Last Amended**: 2026-10-25
