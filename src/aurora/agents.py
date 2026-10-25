from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini

from aurora import config, regulation
from aurora.output_filter import redact_other_apartments
from aurora.tools import (
    autorizar_visitante,
    cancelar_reserva,
    consultar_regulamento,
    listar_meus_visitantes,
    listar_minhas_reservas,
    reservar_area,
    verificar_disponibilidade,
)

llm = Gemini(model=config.MODEL, retry_options=config.RETRY_OPTIONS)

reservas = LlmAgent(
    name="reservas",
    model=llm,
    description="Consulta, reserva e cancela áreas comuns do condomínio.",
    instruction=(
        "Responda em PT-BR. Use as ferramentas para verificar disponibilidade, listar, reservar "
        "e cancelar as reservas do morador. Chame reservar_area diretamente. Nunca pergunte "
        "'você confirma?' no chat: a confirmação é feita pelo sistema."
    ),
    tools=[verificar_disponibilidade, listar_minhas_reservas, reservar_area, cancelar_reserva],
    after_model_callback=redact_other_apartments,
)

visitantes = LlmAgent(
    name="visitantes",
    model=llm,
    description="Lista e autoriza visitantes do condomínio.",
    instruction=(
        "Responda em PT-BR. Use as ferramentas para listar e autorizar os visitantes do morador. "
        "Chame autorizar_visitante diretamente. Nunca pergunte 'você confirma?' no chat: a "
        "confirmação é feita pelo sistema."
    ),
    tools=[listar_meus_visitantes, autorizar_visitante],
    after_model_callback=redact_other_apartments,
)

regulamento = LlmAgent(
    name="regulamento",
    model=llm,
    description="Responde dúvidas sobre o regulamento do condomínio.",
    instruction=(
        "Responda em PT-BR, com base somente no capítulo consultado. Chame "
        "consultar_regulamento com o número romano do capítulo que responde à pergunta. "
        f"Capítulos:\n{regulation.chapter_index()}"
    ),
    tools=[consultar_regulamento],
    after_model_callback=redact_other_apartments,
)

root_agent = LlmAgent(
    name="aurora",
    model=llm,
    instruction=(
        "Responda em PT-BR. Encaminhe pedidos de reserva e cancelamento de áreas comuns ao agente "
        "reservas, pedidos sobre visitantes ao agente visitantes e dúvidas sobre o regulamento ao "
        "agente regulamento."
    ),
    sub_agents=[reservas, visitantes, regulamento],
    after_model_callback=redact_other_apartments,
)
