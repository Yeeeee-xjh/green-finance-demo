"""SQLite connection, migration, and transaction management.

Connections are deliberately short-lived.  The existing web server is
threaded, so sharing one sqlite3 connection between requests would be unsafe.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..domain.models import utc_now


class MigrationError(RuntimeError):
    pass


class Database:
    def __init__(self, path: str | Path, migrations_dir: str | Path | None = None):
        self.path = Path(path).expanduser().resolve()
        self.migrations_dir = (
            Path(migrations_dir).expanduser().resolve()
            if migrations_dir
            else Path(__file__).with_name("migrations")
        )

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            str(self.path),
            timeout=5.0,
            isolation_level=None,
            check_same_thread=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> list[str]:
        """Apply pending SQL files atomically and return applied filenames."""
        connection = self.connect()
        applied: list[str] = []
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            for migration_file in sorted(self.migrations_dir.glob("*.sql")):
                sql = migration_file.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                existing = connection.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = ?",
                    (migration_file.name,),
                ).fetchone()
                if existing:
                    if existing["checksum"] != checksum:
                        raise MigrationError(
                            f"已执行的迁移文件被修改：{migration_file.name}"
                        )
                    continue

                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._execute_script_statements(connection, sql)
                    timestamp = utc_now()
                    connection.execute(
                        """
                        INSERT INTO schema_migrations
                            (version, checksum, applied_at, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (migration_file.name, checksum, timestamp, timestamp, timestamp),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                applied.append(migration_file.name)
            return applied
        finally:
            connection.close()

    @staticmethod
    def _execute_script_statements(connection: sqlite3.Connection, sql: str) -> None:
        """Execute complete SQL statements without sqlite3.executescript commits."""
        buffer = ""
        for line in sql.splitlines(keepends=True):
            buffer += line
            if sqlite3.complete_statement(buffer):
                statement = buffer.strip()
                buffer = ""
                if statement:
                    connection.execute(statement)
        if buffer.strip():
            raise MigrationError("迁移脚本结尾存在不完整SQL语句")

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
