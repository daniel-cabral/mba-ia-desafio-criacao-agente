import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, Session
from google.genai import types
from pydantic import BaseModel

from aurora import config, confirmations, store
from aurora.agents import root_agent

session_service = DatabaseSessionService(db_url=config.DB_URL)
runner = Runner(app_name=config.APP_NAME, agent=root_agent, session_service=session_service)
locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.create_schema()
    yield


app = FastAPI(lifespan=lifespan)


class SessaoIn(BaseModel):
    apartamento: str


class MensagemIn(BaseModel):
    texto: str


class ConfirmacaoIn(BaseModel):
    id: str
    confirmado: bool


async def _sessao(session_id: str) -> Session:
    session = await session_service.get_session(
        app_name=config.APP_NAME, user_id=config.USER_ID, session_id=session_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="sessão não encontrada")
    return session


async def _pendentes(session_id: str) -> list[dict]:
    return confirmations.pending(await _sessao(session_id))


async def _chat(session_id: str, content: types.Content) -> dict:
    textos = []
    async for event in runner.run_async(
        user_id=config.USER_ID, session_id=session_id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            textos += [part.text for part in event.content.parts if part.text and not part.thought]
    return {"resposta": "\n".join(textos), "confirmacoes_pendentes": await _pendentes(session_id)}


@app.post("/sessoes", status_code=201)
async def criar_sessao(corpo: SessaoIn) -> dict:
    session = await session_service.create_session(
        app_name=config.APP_NAME, user_id=config.USER_ID, state={"apartamento": corpo.apartamento}
    )
    return {"session_id": session.id}


@app.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, corpo: MensagemIn) -> dict:
    await _sessao(session_id)
    async with locks[session_id]:
        content = types.Content(role="user", parts=[types.Part(text=corpo.texto)])
        return await _chat(session_id, content)


@app.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, corpo: ConfirmacaoIn) -> dict:
    await _sessao(session_id)
    async with locks[session_id]:
        if corpo.id not in {pendente["id"] for pendente in await _pendentes(session_id)}:
            raise HTTPException(status_code=409, detail="confirmação não pendente nesta sessão")
        content = confirmations.answer_content(corpo.id, corpo.confirmado)
        return await _chat(session_id, content)


@app.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str) -> list[dict]:
    session = await _sessao(session_id)
    return [event.model_dump(mode="json") for event in session.events]


@app.get("/apartamentos/{numero}/reservas")
async def listar_reservas(numero: str) -> list[dict]:
    return await store.list_reservations(numero)


@app.get("/apartamentos/{numero}/visitantes")
async def listar_visitantes(numero: str) -> list[dict]:
    return await store.list_visitors(numero)


def main() -> None:
    uvicorn.run(app, host="localhost", port=8000)
