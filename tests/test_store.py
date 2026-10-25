import asyncio
import sqlite3
from contextlib import closing

from aurora import store


def test_concurrent_insert_same_area_date(tmp_path):
    db = tmp_path / "aurora.db"
    store.create_schema(db=db)

    async def scenario():
        first, second = await asyncio.gather(
            store.insert_reservation("101", "salao-de-festas", "2030-05-11", db=db),
            store.insert_reservation("202", "salao-de-festas", "2030-05-11", db=db),
        )
        owner = "101" if first else "202"
        cancelled = await store.cancel_reservation(
            owner, area="salao-de-festas", data="2030-05-11", db=db
        )
        renewed = await store.insert_reservation("303", "salao-de-festas", "2030-05-11", db=db)
        return {first, second}, cancelled, renewed

    outcomes, cancelled, renewed = asyncio.run(scenario())

    assert outcomes == {None, "AUR-0001"}
    assert cancelled == "AUR-0001"
    assert renewed == "AUR-0002"
    with closing(sqlite3.connect(db)) as conn:
        rows = conn.execute("SELECT codigo, status FROM reservations ORDER BY id").fetchall()
    assert rows == [("AUR-0001", "cancelada"), ("AUR-0002", "ativa")]
