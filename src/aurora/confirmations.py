from google.adk.sessions import Session
from google.genai import types

CONFIRMATION_CALL = "adk_request_confirmation"


def pending(session: Session) -> list[dict]:
    parts = [part for event in session.events if event.content for part in event.content.parts or []]
    answered = {part.function_response.id for part in parts if part.function_response}
    found = []
    for part in parts:
        call = part.function_call
        if call and call.name == CONFIRMATION_CALL and call.id not in answered:
            payload = call.args["toolConfirmation"]["payload"]
            found.append({"id": call.id, "acao": payload["acao"], "detalhes": payload["detalhes"]})
    return found


def answer_content(confirmation_id: str, confirmed: bool) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name=CONFIRMATION_CALL, id=confirmation_id, response={"confirmed": confirmed}
                )
            )
        ],
    )
