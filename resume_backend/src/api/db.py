import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from psycopg.rows import dict_row


def _build_dsn_from_env() -> str:
    """
    Build a libpq DSN from environment variables.

    Expected env vars (provided by orchestrator from resume_db container):
      - POSTGRES_URL (optional; if present used directly)
      - POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT

    Note:
      We intentionally assume host is reachable at 'localhost' from within the dev
      environment, consistent with db_connection.txt and the running container setup.
    """
    url = os.getenv("POSTGRES_URL")
    if url:
        return url

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    dbname = os.getenv("POSTGRES_DB")
    port = os.getenv("POSTGRES_PORT")

    missing = [k for k, v in {
        "POSTGRES_USER": user,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": dbname,
        "POSTGRES_PORT": port,
    }.items() if not v]

    if missing:
        raise RuntimeError(
            "Missing required Postgres environment variables: "
            + ", ".join(missing)
            + ". Please ensure they are set in the container .env."
        )

    # Keep host as localhost to match db_connection.txt pattern.
    return f"postgresql://{user}:{password}@localhost:{port}/{dbname}"


@contextmanager
def get_conn():
    """Context manager yielding a psycopg connection with dict rows."""
    dsn = _build_dsn_from_env()
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


# PUBLIC_INTERFACE
def fetch_one(query: str, params: Optional[Sequence[Any]] = None) -> Optional[Dict[str, Any]]:
    """Fetch a single row as a dict (or None)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return row


# PUBLIC_INTERFACE
def fetch_all(query: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    """Fetch all rows as a list of dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
            return list(rows)


# PUBLIC_INTERFACE
def execute(query: str, params: Optional[Sequence[Any]] = None) -> None:
    """Execute a statement (INSERT/UPDATE/DELETE) committing the transaction."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
        conn.commit()


# PUBLIC_INTERFACE
def execute_returning_one(query: str, params: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
    """Execute a statement that returns a single row (e.g. INSERT ... RETURNING *)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError("Expected a row to be returned, but query returned none.")
        return row
