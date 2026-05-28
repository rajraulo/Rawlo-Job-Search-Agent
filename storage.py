"""
Storage abstraction: local JSON file (dev) or Neon PostgreSQL (prod).
Uses Neon when DATABASE_URL env var is set (auto-injected by Vercel after
linking a Neon database in the Vercel dashboard → Storage → Neon).

Table created automatically on first use:
  store(key TEXT PRIMARY KEY, value TEXT)
"""
import json
import os
from pathlib import Path

_JOBS_KEY   = "agent_jobs"
_LOCAL_PATH = Path(__file__).resolve().parent / "data" / "jobs" / "found_jobs.json"


def _db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def use_db() -> bool:
    return bool(_db_url())


def _get_conn():
    import psycopg2
    return psycopg2.connect(_db_url(), sslmode="require")


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS store (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)


def load_jobs() -> list:
    if use_db():
        with _get_conn() as conn, conn.cursor() as cur:
            _ensure_table(cur)
            cur.execute("SELECT value FROM store WHERE key = %s", (_JOBS_KEY,))
            row = cur.fetchone()
            return json.loads(row[0]) if row else []
    if _LOCAL_PATH.exists():
        return json.loads(_LOCAL_PATH.read_text())
    return []


def save_jobs(jobs: list):
    if use_db():
        data = json.dumps(jobs, default=str)
        with _get_conn() as conn, conn.cursor() as cur:
            _ensure_table(cur)
            cur.execute("""
                INSERT INTO store (key, value, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value,
                      updated_at = now()
            """, (_JOBS_KEY, data))
            conn.commit()
    else:
        _LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_PATH.write_text(json.dumps(jobs, indent=2, default=str))
