import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from aurora import config

BUSY_TIMEOUT_MS = 5000

SCHEMA = """
CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    apartamento TEXT NOT NULL,
    area TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ativa', 'cancelada'))
);
CREATE UNIQUE INDEX IF NOT EXISTS reservations_ativa_area_data
    ON reservations (area, data) WHERE status = 'ativa';
CREATE TABLE IF NOT EXISTS visitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL,
    nome TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


def _load(name: str) -> list[dict]:
    return json.loads((config.DADOS_DIR / name).read_text(encoding="utf-8"))


AREAS: dict[str, dict] = {
    area["id"]: {"nome": area["nome"], "taxa": area["taxa"]} for area in _load("areas.json")
}
APARTMENTS: dict[str, str] = {
    apartment["numero"]: apartment["morador"] for apartment in _load("apartamentos.json")
}


def _connect(db: Path | None) -> sqlite3.Connection:
    conn = sqlite3.connect(db or config.DB_PATH, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


def create_schema(db: Path | None = None) -> None:
    path = db or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


def seed(db: Path | None = None) -> None:
    with closing(_connect(db)) as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS reservations; DROP TABLE IF EXISTS visitors;" + SCHEMA
        )
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "INSERT INTO reservations (codigo, apartamento, area, data, status)"
            " VALUES (?, ?, ?, ?, 'ativa')",
            [
                (row["codigo"], row["apartamento"], row["area"], row["data"])
                for row in _load("reservas.json")
            ],
        )
        conn.executemany(
            "INSERT INTO visitors (apartamento, nome, data) VALUES (?, ?, ?)",
            [(row["apartamento"], row["nome"], row["data"]) for row in _load("visitantes.json")],
        )
        conn.execute("COMMIT")


def _list_reservations(apartamento: str, db: Path | None) -> list[dict]:
    with closing(_connect(db)) as conn:
        rows = conn.execute(
            "SELECT codigo, area, data FROM reservations"
            " WHERE apartamento = ? AND status = 'ativa' ORDER BY id",
            (apartamento,),
        ).fetchall()
    return [{"codigo": codigo, "area": area, "data": data} for codigo, area, data in rows]


async def list_reservations(apartamento: str, db: Path | None = None) -> list[dict]:
    return await asyncio.to_thread(_list_reservations, apartamento, db)


def _is_occupied(area: str, data: str, db: Path | None) -> bool:
    with closing(_connect(db)) as conn:
        row = conn.execute(
            "SELECT 1 FROM reservations WHERE area = ? AND data = ? AND status = 'ativa'",
            (area, data),
        ).fetchone()
    return row is not None


async def is_occupied(area: str, data: str, db: Path | None = None) -> bool:
    return await asyncio.to_thread(_is_occupied, area, data, db)


def _insert_reservation(apartamento: str, area: str, data: str, db: Path | None) -> str | None:
    with closing(_connect(db)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # codigo is UNIQUE NOT NULL, so it is set to a placeholder and rewritten from the id
            # while the write lock is held; the exclusive lock keeps the placeholder unique.
            cursor = conn.execute(
                "INSERT INTO reservations (codigo, apartamento, area, data, status)"
                " VALUES ('', ?, ?, ?, 'ativa')",
                (apartamento, area, data),
            )
            codigo = f"AUR-{cursor.lastrowid:04d}"
            conn.execute(
                "UPDATE reservations SET codigo = ? WHERE id = ?", (codigo, cursor.lastrowid)
            )
            conn.execute("COMMIT")
            return codigo
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return None


async def insert_reservation(
    apartamento: str, area: str, data: str, db: Path | None = None
) -> str | None:
    return await asyncio.to_thread(_insert_reservation, apartamento, area, data, db)


def _cancel_reservation(
    apartamento: str,
    codigo: str | None,
    area: str | None,
    data: str | None,
    db: Path | None,
) -> str | None:
    filters = {"codigo": codigo, "area": area, "data": data}
    active = {column: value for column, value in filters.items() if value is not None}
    where = " AND ".join(
        ["apartamento = ?", "status = 'ativa'"] + [f"{column} = ?" for column in active]
    )
    with closing(_connect(db)) as conn:
        row = conn.execute(
            "UPDATE reservations SET status = 'cancelada' WHERE id = ("
            f"SELECT id FROM reservations WHERE {where} ORDER BY id LIMIT 1) RETURNING codigo",
            (apartamento, *active.values()),
        ).fetchone()
    return row[0] if row else None


async def cancel_reservation(
    apartamento: str,
    *,
    codigo: str | None = None,
    area: str | None = None,
    data: str | None = None,
    db: Path | None = None,
) -> str | None:
    return await asyncio.to_thread(_cancel_reservation, apartamento, codigo, area, data, db)


def _insert_visitor(apartamento: str, nome: str, data: str, db: Path | None) -> None:
    with closing(_connect(db)) as conn:
        conn.execute(
            "INSERT INTO visitors (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome, data),
        )


async def insert_visitor(apartamento: str, nome: str, data: str, db: Path | None = None) -> None:
    await asyncio.to_thread(_insert_visitor, apartamento, nome, data, db)


def _list_visitors(apartamento: str, db: Path | None) -> list[dict]:
    with closing(_connect(db)) as conn:
        rows = conn.execute(
            "SELECT nome, data FROM visitors WHERE apartamento = ? ORDER BY id", (apartamento,)
        ).fetchall()
    return [{"nome": nome, "data": data} for nome, data in rows]


async def list_visitors(apartamento: str, db: Path | None = None) -> list[dict]:
    return await asyncio.to_thread(_list_visitors, apartamento, db)


def _foreign_data(apartamento: str, db: Path | None) -> tuple[list[str], list[str]]:
    with closing(_connect(db)) as conn:
        codes = [
            row[0]
            for row in conn.execute(
                "SELECT codigo FROM reservations WHERE apartamento <> ?", (apartamento,)
            )
        ]
        visitor_names = [
            row[0]
            for row in conn.execute(
                "SELECT nome FROM visitors WHERE apartamento <> ?", (apartamento,)
            )
        ]
    residents = [name for number, name in APARTMENTS.items() if number != apartamento]
    numbers = [number for number in APARTMENTS if number != apartamento]
    return codes + visitor_names + residents, numbers


async def foreign_data(apartamento: str, db: Path | None = None) -> tuple[list[str], list[str]]:
    return await asyncio.to_thread(_foreign_data, apartamento, db)
