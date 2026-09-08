"""
ID mapping and echo/loop-prevention store.

Uses Postgres when DATABASE_URL is set (e.g. on Heroku, where the
filesystem is wiped on every dyno restart -- SQLite alone would lose the
mapping table regularly and risk duplicate Notion pages being created for
cards that were already synced). Falls back to a local SQLite file when
DATABASE_URL isn't set, for local development.
"""
import json
import sqlite3
import time
from contextlib import contextmanager

from config import DATABASE_PATH, DATABASE_URL, SYNC_ECHO_WINDOW_SECONDS

USE_POSTGRES = bool(DATABASE_URL)
PLACEHOLDER = "%s" if USE_POSTGRES else "?"

if USE_POSTGRES:
    import psycopg2

    _PG_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


@contextmanager
def get_conn():
    if USE_POSTGRES:
        conn = psycopg2.connect(_PG_URL, sslmode="require")
    else:
        conn = sqlite3.connect(DATABASE_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor() if USE_POSTGRES else conn
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS id_map (
                trello_card_id TEXT PRIMARY KEY,
                notion_page_id TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_writes (
                record_id TEXT NOT NULL,
                field_hash TEXT NOT NULL,
                written_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_recent_writes_lookup "
            "ON recent_writes (record_id, field_hash)"
        )


def _execute(conn, query_sqlite: str, query_pg: str, params: tuple):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(query_pg, params)
        return cur
    return conn.execute(query_sqlite, params)


def get_notion_id(trello_card_id: str):
    with get_conn() as conn:
        cur = _execute(
            conn,
            "SELECT notion_page_id FROM id_map WHERE trello_card_id = ?",
            "SELECT notion_page_id FROM id_map WHERE trello_card_id = %s",
            (trello_card_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_trello_id(notion_page_id: str):
    with get_conn() as conn:
        cur = _execute(
            conn,
            "SELECT trello_card_id FROM id_map WHERE notion_page_id = ?",
            "SELECT trello_card_id FROM id_map WHERE notion_page_id = %s",
            (notion_page_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def link_ids(trello_card_id: str, notion_page_id: str):
    with get_conn() as conn:
        if USE_POSTGRES:
            conn.cursor().execute(
                """
                INSERT INTO id_map (trello_card_id, notion_page_id, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (trello_card_id) DO UPDATE
                SET notion_page_id = EXCLUDED.notion_page_id, created_at = EXCLUDED.created_at
                """,
                (trello_card_id, notion_page_id, time.time()),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO id_map (trello_card_id, notion_page_id, created_at) "
                "VALUES (?, ?, ?)",
                (trello_card_id, notion_page_id, time.time()),
            )


def _hash_fields(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, default=str)


def mark_written(record_id: str, fields: dict):
    """Call right after WE write `fields` to `record_id`, so the echoing
    webhook event our own write triggers on the other platform can be
    recognized and skipped instead of syncing back and forth forever."""
    field_hash = _hash_fields(fields)
    with get_conn() as conn:
        _execute(
            conn,
            "INSERT INTO recent_writes (record_id, field_hash, written_at) VALUES (?, ?, ?)",
            "INSERT INTO recent_writes (record_id, field_hash, written_at) VALUES (%s, %s, %s)",
            (record_id, field_hash, time.time()),
        )
        _execute(
            conn,
            "DELETE FROM recent_writes WHERE written_at < ?",
            "DELETE FROM recent_writes WHERE written_at < %s",
            (time.time() - SYNC_ECHO_WINDOW_SECONDS * 4,),
        )


def is_echo(record_id: str, fields: dict) -> bool:
    """True if this exact field set was written by us to this record within
    the echo window -- meaning the incoming webhook is our own write bouncing
    back, not a genuine external change."""
    cutoff = time.time() - SYNC_ECHO_WINDOW_SECONDS
    target_hash = _hash_fields(fields)
    with get_conn() as conn:
        cur = _execute(
            conn,
            "SELECT 1 FROM recent_writes WHERE record_id = ? AND field_hash = ? AND written_at >= ?",
            "SELECT 1 FROM recent_writes WHERE record_id = %s AND field_hash = %s AND written_at >= %s",
            (record_id, target_hash, cutoff),
        )
        return cur.fetchone() is not None
