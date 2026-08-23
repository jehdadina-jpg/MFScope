"""
Additive schema reconciliation
==============================
Compares the SQLAlchemy metadata against the live SQLite file and issues
``ALTER TABLE … ADD COLUMN`` for anything the models declare but the database
does not have.

Why not Alembic here
--------------------
Alembic is the right tool for a production Postgres deployment and the
``alembic/`` directory stays in place for that.  But the local SQLite file is
380 MB of NAV history that must survive schema evolution, and the columns
added by this release are all nullable additions with no data migration.  A
declarative, idempotent reconcile is both safer to re-run and honest about
what it does — it will refuse anything that is not a pure addition.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import text
from sqlalchemy.schema import CreateIndex

from backend.db.models import Base
from backend.db.session import engine

#: SQLite cannot add a column with a non-constant default, so we translate the
#: declarative default into a literal where one is needed.
_SQLITE_TYPES = {
    "INTEGER": "INTEGER",
    "BIGINT": "INTEGER",
    "FLOAT": "FLOAT",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "DATETIME": "DATETIME",
    "TEXT": "TEXT",
}


def _column_ddl(column) -> str:
    type_name = column.type.compile(dialect=engine.dialect)
    ddl = f'"{column.name}" {type_name}'
    default = column.default
    if default is not None and getattr(default, "is_scalar", False):
        value = default.arg
        if isinstance(value, bool):
            ddl += f" DEFAULT {1 if value else 0}"
        elif isinstance(value, (int, float)):
            ddl += f" DEFAULT {value}"
        elif isinstance(value, str):
            ddl += f" DEFAULT '{value}'"
    return ddl


async def reconcile_schema() -> dict[str, list[str]]:
    """Create missing tables, then add missing columns. Returns what changed."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    added: dict[str, list[str]] = {}

    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            rows = await conn.execute(text(f'PRAGMA table_info("{table.name}")'))
            existing = {row[1] for row in rows.all()}
            if not existing:
                continue

            missing = [c for c in table.columns if c.name not in existing]
            for column in missing:
                await conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN {_column_ddl(column)}')
                )
            if missing:
                added[table.name] = [c.name for c in missing]

        # Indexes declared on the models but absent from an older file.
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                statement = str(CreateIndex(index, if_not_exists=True).compile(bind=conn.engine))
                await conn.execute(text(statement))

    for table_name, columns in added.items():
        logger.info(f"Schema: added {len(columns)} column(s) to {table_name}: {', '.join(columns)}")
    if not added:
        logger.info("Schema: already up to date.")
    return added


if __name__ == "__main__":
    asyncio.run(reconcile_schema())
