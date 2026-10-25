import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from aurora import store

REPLACEMENT = "[dado restrito]"


def redact(text: str, terms: list[str], numbers: list[str]) -> str:
    for term in terms:
        text = text.replace(term, REPLACEMENT)
    if numbers:
        alternatives = "|".join(re.escape(number) for number in numbers)
        text = re.sub(rf"(?<![\w-])(?:{alternatives})(?![\w-])", REPLACEMENT, text)
    return text


async def redact_other_apartments(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse | None:
    apartamento = callback_context.state["apartamento"]
    terms, numbers = await store.foreign_data(apartamento)
    if llm_response.content is None:
        return None
    parts = []
    changed = False
    for part in llm_response.content.parts or []:
        if part.text:
            redacted = redact(part.text, terms, numbers)
            if redacted != part.text:
                changed = True
                part = part.model_copy(update={"text": redacted})
        parts.append(part)
    if not changed:
        return None
    content = llm_response.content.model_copy(update={"parts": parts})
    return llm_response.model_copy(update={"content": content})
