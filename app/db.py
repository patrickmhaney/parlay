"""DuckDB access layer.

Two things matter here and are easy to get wrong:

1. DuckDB allows a single writer. Every write goes through `Database.write()`,
   which holds a process-wide lock. The app therefore MUST run with a single
   uvicorn worker (see docker-compose.yml and the README).

2. A DuckDB connection is not safe to share across threads. FastAPI runs sync
   route handlers in a threadpool, so each thread gets its own cursor derived
   from the root connection via `.cursor()`.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import duckdb

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._root = duckdb.connect(self.path)
        self._local = threading.local()
        self._write_lock = threading.RLock()

    # -- connections ------------------------------------------------------

    @property
    def _cur(self) -> duckdb.DuckDBPyConnection:
        cur = getattr(self._local, "cur", None)
        if cur is None:
            cur = self._root.cursor()
            self._local.cur = cur
        return cur

    def close(self) -> None:
        try:
            self._root.close()
        except Exception:  # pragma: no cover - shutdown best effort
            pass

    # -- reads ------------------------------------------------------------

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        cur = self._cur.execute(sql, list(params))
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def row(self, sql: str, params: Sequence[Any] = ()) -> dict | None:
        out = self.rows(sql, params)
        return out[0] if out else None

    def value(self, sql: str, params: Sequence[Any] = ()) -> Any:
        r = self._cur.execute(sql, list(params)).fetchone()
        return r[0] if r else None

    # -- writes -----------------------------------------------------------

    @contextmanager
    def write(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Serialized write transaction. All mutations must go through this."""
        with self._write_lock:
            cur = self._cur
            cur.execute("BEGIN TRANSACTION")
            try:
                yield cur
                cur.execute("COMMIT")
            except Exception:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self.write() as cur:
            cur.execute(sql, list(params))

    def execute_many(self, sql: str, seq: Iterable[Sequence[Any]]) -> int:
        n = 0
        with self.write() as cur:
            for params in seq:
                cur.execute(sql, list(params))
                n += 1
        return n

    # -- migrations -------------------------------------------------------

    def migrate(self, migrations_dir: Path = MIGRATIONS_DIR) -> list[int]:
        """Apply any .sql files whose numeric prefix is above schema_version."""
        self._root.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "  version INTEGER PRIMARY KEY,"
            "  applied_at TIMESTAMP NOT NULL"
            ")"
        )
        current = self._root.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]

        applied: list[int] = []
        files = sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name)
        for f in files:
            version = int(f.name.split("_", 1)[0])
            if version <= current:
                continue
            sql = f.read_text()
            log.info("applying migration %s", f.name)
            with self._write_lock:
                self._root.execute("BEGIN TRANSACTION")
                try:
                    self._root.execute(sql)
                    self._root.execute(
                        "INSERT INTO schema_version VALUES (?, now()::TIMESTAMP)",
                        [version],
                    )
                    self._root.execute("COMMIT")
                except Exception:
                    self._root.execute("ROLLBACK")
                    raise
            applied.append(version)
        return applied


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                from app.config import get_settings

                _db = Database(get_settings().database_path)
    return _db


def close_db() -> None:
    """Close the shared connection and clear the singleton, so a later
    get_db() reconnects instead of handing back a dead handle. Makes shutdown
    idempotent and lets the app be started more than once in a process."""
    global _db
    with _db_lock:
        if _db is not None:
            _db.close()
            _db = None


def reset_db_for_tests(path: str | Path) -> Database:
    global _db
    with _db_lock:
        if _db is not None:
            _db.close()
        _db = Database(path)
    return _db
