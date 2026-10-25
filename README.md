# Residencial Aurora: assistente virtual

Assistente do Residencial Aurora construído com Google ADK 2.13.0, exposto por uma API FastAPI e persistido em um arquivo SQLite. O enunciado original do desafio está no commit `be87e1d`.

## Arquitetura

Um agente principal conversa com o morador e transfere cada pedido ao especialista certo.

| Agente | Arquivo | Responsabilidade | Como é acionado |
|---|---|---|---|
| `aurora` (principal) | `src/aurora/agents.py` | Entende o pedido e encaminha. Não recebe o regulamento. | Ponto de entrada: o `Runner` executa `root_agent` |
| `reservas` | `src/aurora/agents.py` | Verifica disponibilidade, reserva, lista e cancela reservas do morador | Transferência a partir de `aurora` (`sub_agents`) |
| `visitantes` | `src/aurora/agents.py` | Lista e autoriza visitantes | Transferência a partir de `aurora` (`sub_agents`) |
| `regulamento` | `src/aurora/agents.py` | Responde dúvidas consultando um capítulo do regulamento | Transferência a partir de `aurora` (`sub_agents`) |

### Por que transferência e não `AgentTool`

- Com `sub_agents`, quando o morador responde uma confirmação, o `Runner` entrega a resposta ao agente que fez a chamada pendente, e a ação retoma nele.
- Com `AgentTool`, o especialista roda numa sessão aninhada, e a confirmação não é retomada. Essa conclusão vem da leitura do código do ADK 2.13.0 em `google/adk/tools/agent_tool.py`.

### Modelo, tools e acesso aos dados

- Todos os agentes usam a constante `MODEL` de `src/aurora/config.py` (`gemini-3.8-flash`), com retry para os códigos 429 e 503.
- Reservas e visitantes são lidos e gravados só por tools, em `src/aurora/tools.py`. Cada tool recebe `tool_context` e usa o apartamento de `tool_context.state["apartamento"]`.
- O acesso ao SQLite fica em `src/aurora/store.py`. As chamadas síncronas rodam em `asyncio.to_thread`, com WAL e `busy_timeout`.

### Confirmação

Tools que geram cobrança ou liberam acesso chamam `tool_context.request_confirmation`. A pendência vira um evento da sessão. A API lista as pendências a partir desses eventos e recebe a resposta em `POST /sessoes/{session_id}/confirmacoes`, que devolve ao ADK uma `FunctionResponse` com o mesmo `id`.

### Restauração

`aurora-restore` recria as tabelas de reservas e visitantes a partir de `dados/` e apaga as sessões do ADK, para que o estado inicial volte junto com os dados. A API nunca popula dados: na subida, só cria o esquema que faltar.

## Garantias

Cada garantia indica o arquivo e o trecho que a implementam. "Não depende do modelo" significa que o código bloqueia a ação mesmo que o modelo a peça ou a descreva de outra forma.

### G1: cobrança ou acesso só com confirmação

Arquivos: `src/aurora/tools.py` (`_confirmar`, `reservar_area`, `autorizar_visitante`), `src/aurora/api.py` (`enviar_mensagem`, `responder_confirmacao`), `src/aurora/confirmations.py` (`answer_content`).

Em `_confirmar`, a tool pausa antes de gravar:

```python
confirmation = tool_context.tool_confirmation
if confirmation is None:
    tool_context.request_confirmation(hint=hint, payload={"acao": acao, "detalhes": detalhes})
    tool_context.actions.skip_summarization = True
    return {"status": "aguardando_confirmacao"}
if not confirmation.confirmed:
    return {"status": "negada"}
```

Na rota de mensagens, o texto do morador vira sempre uma parte de texto. A rota de confirmações só monta a resposta depois de checar a pendência:

```python
content = types.Content(role="user", parts=[types.Part(text=corpo.texto)])
```

```python
if corpo.id not in {pendente["id"] for pendente in await _pendentes(session_id)}:
    raise HTTPException(status_code=409, detail="confirmação não pendente nesta sessão")
content = confirmations.answer_content(corpo.id, corpo.confirmado)
```

Por que não depende do modelo:

- A tool só grava a cobrança ou a autorização quando `tool_confirmation.confirmed` é verdadeiro, e esse valor só chega pela `FunctionResponse` que a rota de confirmações monta.
- Uma frase como "já estou confirmando" vira texto comum. Ela não consegue produzir essa resposta.
- A rota recusa com `409` qualquer `id` que não esteja entre as pendências gravadas na sessão, então uma confirmação já respondida não executa de novo.
- Negar retorna antes de `insert_reservation` ou `insert_visitor`, então nada é gravado.

### G2: cada sessão pertence a um apartamento

Arquivos: `src/aurora/api.py` (`criar_sessao`), `src/aurora/tools.py` (`cancelar_reserva`, `verificar_disponibilidade`), `src/aurora/store.py` (`_cancel_reservation`), `src/aurora/output_filter.py` (`redact_other_apartments`).

O apartamento entra uma única vez, na criação da sessão:

```python
session = await session_service.create_session(
    app_name=config.APP_NAME, user_id=config.USER_ID, state={"apartamento": corpo.apartamento}
)
```

Nenhuma tool recebe o apartamento como argumento. O cancelamento usa o apartamento da sessão e a consulta do banco filtra por ele:

```python
cancelado = await store.cancel_reservation(
    tool_context.state["apartamento"], codigo=codigo, area=area, data=data
)
```

```python
where = " AND ".join(
    ["apartamento = ?", "status = 'ativa'"] + [f"{column} = ?" for column in active]
)
```

A consulta de disponibilidade devolve só o status, nunca quem reservou:

```python
return {"status": "ocupada" if ocupada else "livre"}
```

Por que não depende do modelo:

- As assinaturas das tools não têm campo de apartamento, então o modelo não tem onde escolher outro apartamento.
- O `WHERE apartamento = ?` está na consulta do banco. Um código de outro apartamento não é cancelado: a tool responde que a reserva não foi encontrada.
- O filtro de saída `redact_other_apartments` é defesa em profundidade. Ele troca, no texto do modelo, códigos, nomes e números de outros apartamentos lidos do banco a cada resposta. Como trabalha com texto literal, não é a garantia: a garantia é o que as tools não devolvem.

### G3: nada se perde no reinício

Arquivos: `src/aurora/config.py` (`DB_URL`), `src/aurora/api.py` (`session_service`, `lifespan`), `src/aurora/confirmations.py` (`pending`), `src/aurora/store.py` (`create_schema`).

```python
DB_PATH = ROOT_DIR / "data" / "aurora.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
```

```python
session_service = DatabaseSessionService(db_url=config.DB_URL)
```

```python
async def lifespan(app: FastAPI):
    store.create_schema()
```

Por que não depende do modelo:

- Sessões e eventos ficam no SQLite, pelo `DatabaseSessionService`, e não na memória do processo.
- A confirmação pendente não tem tabela própria: ela sai dos eventos gravados (`confirmations.pending`). Depois do reinício, a mesma pendência continua valendo.
- Reservas e visitantes ficam no mesmo arquivo `data/aurora.db`. A subida da API só cria o esquema que faltar e nunca reinicializa os dados.

### G4: o regulamento é consultado, não carregado

Arquivos: `src/aurora/regulation.py` (`CHAPTERS`, `get_chapter`), `src/aurora/tools.py` (`consultar_regulamento`), `src/aurora/agents.py` (`regulamento`, `root_agent`).

Em `consultar_regulamento`, a tool valida o id e devolve um único capítulo:

```python
chapter = regulation.get_chapter(capitulo)
if chapter is None:
    return {"status": "erro", "mensagem": "capítulo inexistente"}
return {"capitulo": capitulo, **chapter}
```

O agente principal só declara os especialistas, sem texto do regulamento:

```python
sub_agents=[reservas, visitantes, regulamento],
```

Os títulos dos capítulos ficam só nas instruções do especialista `regulamento`:

```python
f"Capítulos:\n{regulation.chapter_index()}"
```

Por que não depende do modelo:

- O regulamento inteiro nunca entra no contexto. Cada chamada devolve um único capítulo.
- A tool recusa qualquer id fora dos capítulos carregados (`CHAPTERS.get`), e o principal não tem o texto do regulamento nas instruções.
- Qual capítulo o modelo escolhe continua sendo decisão dele. O limite que o código impõe é um capítulo por chamada, não a resposta.

### G5: dois moradores, uma reserva

Arquivos: `src/aurora/store.py` (`SCHEMA`, `_insert_reservation`), `src/aurora/tools.py` (`reservar_area`).

O banco impede duas reservas ativas para a mesma área e data:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS reservations_ativa_area_data
    ON reservations (area, data) WHERE status = 'ativa';
```

A gravação trata a violação do índice como recusa normal:

```python
except sqlite3.IntegrityError:
    conn.execute("ROLLBACK")
    return None
```

A tool transforma essa recusa em resultado comum:

```python
codigo = await store.insert_reservation(tool_context.state["apartamento"], area, data)
if codigo is None:
    return {"status": "ocupada"}
```

Por que não depende do modelo:

- A exclusividade é do índice e vale no instante do `INSERT`. Mesmo que duas aprovações passem ao mesmo tempo pela checagem de disponibilidade, só uma linha ativa para a mesma área e data consegue entrar.
- A checagem prévia em `reservar_area` só antecipa a recusa na conversa. Ela não garante a exclusividade.
- A segunda aprovação recebe `{"status": "ocupada"}` como resultado normal, e a rota responde `200`.
- Reservas canceladas continuam no banco com o seu código, e `AUTOINCREMENT` impede que um código seja reaproveitado.

## Como rodar

Pré-requisitos:

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/)
- Chave de API do Google AI Studio

Variável de ambiente: crie o arquivo `.env` na raiz a partir do exemplo e preencha a chave. O `.env` fica fora do Git.

```bash
cp .env.example .env
```

No Windows, use `copy .env.example .env`. O arquivo tem uma única variável:

```
GEMINI_API_KEY=
```

Só a conversa com o modelo precisa da chave. Restaurar os dados e ler as rotas de verificação não precisam.

Comandos, nesta ordem:

```bash
uv sync
uv run aurora-restore
uv run aurora-api
```

- `uv sync` instala as dependências na versão fixada em `uv.lock`.
- `uv run aurora-restore` cria `data/aurora.db` com as reservas e os visitantes de `dados/` e apaga as sessões antigas. Rode antes da primeira subida em um clone novo, porque a API só cria o esquema e não carrega dados.
- `uv run aurora-api` sobe a API em `http://localhost:8000`.

Para conferir a subida, `GET http://localhost:8000/apartamentos/101/reservas` deve listar a `RSV-1377`.

Parar com Ctrl+C e subir de novo, sem restaurar, mantém as sessões e os dados. Não há serviço externo para subir além da API do Gemini.
