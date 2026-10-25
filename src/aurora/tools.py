import re
from datetime import date

from google.adk.tools import ToolContext

from aurora import regulation, store

DATA_FORMATO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _data_valida(data: str) -> bool:
    if DATA_FORMATO.fullmatch(data) is None:
        return False
    try:
        date.fromisoformat(data)
    except ValueError:
        return False
    return True


def _erro_area_data(area: str, data: str) -> dict | None:
    if area not in store.AREAS:
        return {"status": "erro", "mensagem": "área inexistente"}
    if not _data_valida(data):
        return {"status": "erro", "mensagem": "data deve estar no formato AAAA-MM-DD"}
    return None


def _confirmar(tool_context: ToolContext, hint: str, acao: str, detalhes: dict) -> dict | None:
    """Return None when the resident confirmed; otherwise the result the tool must return."""
    confirmation = tool_context.tool_confirmation
    if confirmation is None:
        tool_context.request_confirmation(hint=hint, payload={"acao": acao, "detalhes": detalhes})
        tool_context.actions.skip_summarization = True
        return {"status": "aguardando_confirmacao"}
    if not confirmation.confirmed:
        return {"status": "negada"}
    return None


async def verificar_disponibilidade(area: str, data: str, tool_context: ToolContext) -> dict:
    """Informa se uma área comum está livre ou ocupada numa data. Áreas: salao-de-festas, churrasqueira, quadra. Data no formato AAAA-MM-DD."""
    erro = _erro_area_data(area, data)
    if erro is not None:
        return erro
    ocupada = await store.is_occupied(area, data)
    return {"status": "ocupada" if ocupada else "livre"}


async def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento do morador."""
    return {"reservas": await store.list_reservations(tool_context.state["apartamento"])}


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum numa data (AAAA-MM-DD). Áreas com taxa só são gravadas após confirmação do morador."""
    erro = _erro_area_data(area, data)
    if erro is not None:
        return erro
    if await store.is_occupied(area, data):
        return {"status": "ocupada"}
    if store.AREAS[area]["taxa"] > 0:
        pendencia = _confirmar(
            tool_context,
            f"Confirmar reserva de {area} em {data}",
            "reservar_area",
            {"area": area, "data": data},
        )
        if pendencia is not None:
            return pendencia
    codigo = await store.insert_reservation(tool_context.state["apartamento"], area, data)
    if codigo is None:
        return {"status": "ocupada"}
    return {"status": "reservada", "codigo": codigo}


async def cancelar_reserva(
    codigo: str | None = None,
    area: str | None = None,
    data: str | None = None,
    *,
    tool_context: ToolContext,
) -> dict:
    """Cancela uma reserva ativa do apartamento do morador, pelo código ou pela área e data (AAAA-MM-DD)."""
    if codigo is None and (area is None or data is None):
        return {"status": "erro", "mensagem": "informe o código ou a área e a data"}
    cancelado = await store.cancel_reservation(
        tool_context.state["apartamento"], codigo=codigo, area=area, data=data
    )
    if cancelado is None:
        return {"status": "nao_encontrada", "mensagem": "reserva não encontrada entre as suas reservas"}
    return {"status": "cancelada", "codigo": cancelado}


async def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados do apartamento do morador."""
    return {"visitantes": await store.list_visitors(tool_context.state["apartamento"])}


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante numa data (AAAA-MM-DD). Só é gravado após confirmação do morador."""
    pendencia = _confirmar(
        tool_context,
        f"Autorizar visitante {nome} em {data}",
        "autorizar_visitante",
        {"nome": nome, "data": data},
    )
    if pendencia is not None:
        return pendencia
    await store.insert_visitor(tool_context.state["apartamento"], nome, data)
    return {"status": "autorizado", "nome": nome, "data": data}


async def consultar_regulamento(capitulo: str, tool_context: ToolContext) -> dict:
    """Retorna um único capítulo do regulamento pelo número romano (I a XIV)."""
    chapter = regulation.get_chapter(capitulo)
    if chapter is None:
        return {"status": "erro", "mensagem": "capítulo inexistente"}
    return {"capitulo": capitulo, **chapter}
