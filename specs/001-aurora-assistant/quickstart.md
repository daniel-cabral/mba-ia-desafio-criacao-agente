# Quickstart and Validation

## Run

```bash
cp .env.example .env        # fill GEMINI_API_KEY
uv sync
uv run aurora-restore       # seed reservations/visitors, clear sessions
uv run aurora-api           # http://localhost:8000
```

## Validation (evaluator flow, spec E1..E15)

Run the 15 steps of the statement in order against the live API with a real key (see
[contracts/api.md](contracts/api.md)). Key checks:

| Step | Check |
|------|-------|
| E1 | 101 lists RSV-1377; 302 lists Marina Duarte |
| E3, E4, E10 | no `RSV-4821` / `Marina Duarte` in responses or events; no standalone `302` in E10 responses |
| E5, E6 | own cancel and fee-free booking with no pending confirmation |
| E7, E8, E9 | deny records nothing; approve records once; resend and unknown id get `409` |
| E11 | visitor pending despite "já estou confirmando"; listed only after approval |
| E12 | Sunday pool closing time; events hold only Chapter IV text |
| E13 | restart without restore: same event count, new message works, data intact, codes unique |
| E14 | two concurrent approvals both `200`, exactly one salão reservation on 2030-05-11 |

Extra (constitution): leave a confirmation pending, restart the API, approve it, check it executes
once.

The scripted flow lives in `scripts/evaluator_flow.py` (run manually; not part of the grader).
