"""
Storage abstraction: local files (dev) or Neon PostgreSQL (prod).
DATABASE_URL is auto-injected by Vercel after linking a Neon database.

Two keys in the store table:
  agent_jobs   — list of all tracked jobs (JSON)
  agent_config — search configuration: keywords, locations, schedule (JSON)
"""
import json
import os
from pathlib import Path

_JOBS_KEY   = "agent_jobs"
_CONFIG_KEY = "agent_config"
_LOCAL_PATH = Path(__file__).resolve().parent / "data" / "jobs" / "found_jobs.json"
_ROOT       = Path(__file__).resolve().parent


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


def _db_get(key: str):
    with _get_conn() as conn, conn.cursor() as cur:
        _ensure_table(cur)
        cur.execute("SELECT value FROM store WHERE key = %s", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else None


def _db_set(key: str, value):
    data = json.dumps(value, default=str)
    with _get_conn() as conn, conn.cursor() as cur:
        _ensure_table(cur)
        cur.execute("""
            INSERT INTO store (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value, updated_at = now()
        """, (key, data))
        conn.commit()


# ── Jobs ──────────────────────────────────────────────────────────────────────

def load_jobs() -> list:
    if use_db():
        return _db_get(_JOBS_KEY) or []
    if _LOCAL_PATH.exists():
        return json.loads(_LOCAL_PATH.read_text())
    return []


def save_jobs(jobs: list):
    if use_db():
        _db_set(_JOBS_KEY, jobs)
    else:
        _LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_PATH.write_text(json.dumps(jobs, indent=2, default=str))


# ── Config ────────────────────────────────────────────────────────────────────

def _default_config() -> dict:
    """Read default config from local YAML files."""
    try:
        import yaml
        with open(_ROOT / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        with open(_ROOT / "keywords.yaml") as f:
            keywords = yaml.safe_load(f)

        locs = settings.get("search", {}).get("locations", {})
        return {
            "primary_keywords":   keywords.get("primary_keywords", []),
            "secondary_keywords": keywords.get("secondary_keywords", []),
            "exclude_keywords":   keywords.get("exclude_keywords", []),
            "locations":          locs.get("uae", []) + locs.get("global", []),
            "experience_levels":  settings.get("search", {}).get("experience_levels", ["mid-senior"]),
            "job_types":          settings.get("search", {}).get("job_types", ["full-time"]),
            "min_relevance_score": settings.get("search", {}).get("min_relevance_score", 60),
            "schedule_minutes":   settings.get("agent", {}).get("run_interval_minutes", 10),
            "max_jobs_per_run":   settings.get("agent", {}).get("max_jobs_per_run", 20),
        }
    except Exception:
        return {
            "primary_keywords":   [],
            "secondary_keywords": [],
            "exclude_keywords":   [],
            "locations":          [],
            "experience_levels":  ["mid-senior"],
            "job_types":          ["full-time"],
            "min_relevance_score": 60,
            "schedule_minutes":   10,
            "max_jobs_per_run":   20,
        }


def load_config() -> dict:
    if use_db():
        saved = _db_get(_CONFIG_KEY)
        if saved:
            return saved
    return _default_config()


def save_config(config: dict):
    if use_db():
        _db_set(_CONFIG_KEY, config)
