import asyncio

from google.adk.sessions import DatabaseSessionService

from aurora import config, store


async def _delete_sessions() -> None:
    service = DatabaseSessionService(db_url=config.DB_URL)
    response = await service.list_sessions(app_name=config.APP_NAME, user_id=config.USER_ID)
    for session in response.sessions:
        await service.delete_session(
            app_name=config.APP_NAME, user_id=config.USER_ID, session_id=session.id
        )


def main() -> None:
    store.create_schema()
    store.seed()
    asyncio.run(_delete_sessions())
