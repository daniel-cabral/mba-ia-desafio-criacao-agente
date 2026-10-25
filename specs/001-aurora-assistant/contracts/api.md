# API Contract (verbatim from the challenge statement)

Base: `http://localhost:8000`. JSON in and out. Unknown `{session_id}` → `404`. Dates `AAAA-MM-DD`.

| Method | Path | Body | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/sessoes` | `{"apartamento": "101"}` | `201 {"session_id": "..."}` | |
| POST | `/sessoes/{session_id}/mensagens` | `{"texto": "..."}` | `200` ChatResponse | `404` |
| POST | `/sessoes/{session_id}/confirmacoes` | `{"id": "...", "confirmado": true}` | `200` ChatResponse | `404`, `409` |
| GET | `/sessoes/{session_id}/eventos` | | `200` list of all events, in order, full content | `404` |
| GET | `/apartamentos/{numero}/reservas` | | `200 [{"codigo", "area", "data"}]` (active only) | |
| GET | `/apartamentos/{numero}/visitantes` | | `200 [{"nome", "data"}]` | |

## ChatResponse

```json
{
  "resposta": "...",
  "confirmacoes_pendentes": [
    {"id": "...", "acao": "reservar_area", "detalhes": {"area": "salao-de-festas", "data": "2030-04-20"}},
    {"id": "...", "acao": "autorizar_visitante", "detalhes": {"nome": "Joana Ribeiro", "data": "2030-04-21"}}
  ]
}
```

- `resposta` may be `""` when the run stopped waiting for confirmation.
- `confirmacoes_pendentes` lists all pending confirmations of the session; `[]` when none.
- `409`: no pending confirmation with that `id` in this session (unknown, answered, other session).
- A concurrent loser in a reservation race gets `200` with a refusal in `resposta`.

## Internal tool contract (agents)

| Agent | Tool | Args | Confirmation |
|-------|------|------|--------------|
| reservas | `verificar_disponibilidade` | `area`, `data` | no; returns only `livre`/`ocupada` |
| reservas | `listar_minhas_reservas` | none | no |
| reservas | `reservar_area` | `area`, `data` | only when `taxa > 0` |
| reservas | `cancelar_reserva` | `codigo` or `area` + `data` | no; own apartment only |
| visitantes | `listar_meus_visitantes` | none | no |
| visitantes | `autorizar_visitante` | `nome`, `data` | always |
| regulamento | `consultar_regulamento` | `capitulo` (validated id) | no |

No tool takes an apartment argument; all read `tool_context.state["apartamento"]`.
