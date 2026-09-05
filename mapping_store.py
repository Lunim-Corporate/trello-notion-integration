import json
import sqlite3
import time
from contextlib import contextmanager

from config import DATABASE_PATH, SYNC_ECHO_WINDOW_SECONDS


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS id_map (
                trello_card_id TEXT PRIMARY KEY,
                notion_page_id TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_writes (
                record_id TEXT NOT NULL,
                field_hash TEXT NOT NULL,
                written_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recent_writes_lookup "
            "ON recent_writes (record_id, field_hash)"
        )


def get_notion_id(trello_card_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT notion_page_id FROM id_map WHERE trello_card_id = ?",
            (trello_card_id,),
        ).fetchone()
        return row[0] if row else None


def get_trello_id(notion_page_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT trello_card_id FROM id_map WHERE notion_page_id = ?",
            (notion_page_id,),
        ).fetchone()
        return row[0] if row else None


def link_ids(trello_card_id: str, notion_page_id: str):
    with get_conn() as conn:
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
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO recent_writes (record_id, field_hash, written_at) VALUES (?, ?, ?)",
            (record_id, _hash_fields(fields), time.time()),
        )
        conn.execute(
            "DELETE FROM recent_writes WHERE written_at < ?",
            (time.time() - SYNC_ECHO_WINDOW_SECONDS * 4,),
        )


def is_echo(record_id: str, fields: dict) -> bool:
    """True if this exact field set was written by us to this record within
    the echo window -- meaning the incoming webhook is our own write bouncing
    back, not a genuine external change."""
    cutoff = time.time() - SYNC_ECHO_WINDOW_SECONDS
    target_hash = _hash_fields(fields)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM recent_writes WHERE record_id = ? AND field_hash = ? AND written_at >= ?",
            (record_id, target_hash, cutoff),
        ).fetchone()
        return row is not None
