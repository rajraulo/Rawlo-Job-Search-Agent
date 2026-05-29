"""
Storage abstraction: local files (dev) or Neon PostgreSQL (prod).
DATABASE_URL is auto-injected by Vercel after linking a Neon database.

Keys in the store table:
  agent_jobs    — list of all tracked jobs (JSON)
  agent_config  — search config: keywords, locations, schedule, credentials
  run_trigger   — flag set by dashboard to trigger an immediate run
  agent_status  — last run time, run count, etc.
"""
import json
import os
from pathlib import Path

_JOBS_KEY    = "agent_jobs"
_CONFIG_KEY  = "agent_config"
_TRIGGER_KEY = "run_trigger"
_STATUS_KEY  = "agent_status"
_RESUME_KEY  = "user_resume"
_ROOT        = Path(__file__).resolve().parent


def _uk(user_id: int, key: str) -> str:
    """Namespace a store key by user_id so each user's data is isolated."""
    return f"u{user_id}_{key}" if user_id else key


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

_LOCAL_JOBS = _ROOT / "data" / "jobs" / "found_jobs.json"

def load_jobs(user_id: int = 0) -> list:
    if use_db():
        return _db_get(_uk(user_id, _JOBS_KEY)) or []
    if _LOCAL_JOBS.exists():
        return json.loads(_LOCAL_JOBS.read_text())
    return []

def save_jobs(jobs: list, user_id: int = 0):
    if use_db():
        _db_set(_uk(user_id, _JOBS_KEY), jobs)
    else:
        _LOCAL_JOBS.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_JOBS.write_text(json.dumps(jobs, indent=2, default=str))


# ── Config ────────────────────────────────────────────────────────────────────

def _default_config() -> dict:
    try:
        import yaml
        with open(_ROOT / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        with open(_ROOT / "keywords.yaml") as f:
            keywords = yaml.safe_load(f)
        locs = settings.get("search", {}).get("locations", {})
        return {
            "primary_keywords":    keywords.get("primary_keywords", []),
            "secondary_keywords":  keywords.get("secondary_keywords", []),
            "exclude_keywords":    keywords.get("exclude_keywords", []),
            "locations":           locs.get("uae", []) + locs.get("global", []),
            "experience_levels":   settings.get("search", {}).get("experience_levels", ["mid-senior"]),
            "job_types":           settings.get("search", {}).get("job_types", ["full-time"]),
            "min_relevance_score": settings.get("search", {}).get("min_relevance_score", 60),
            "schedule_minutes":    settings.get("agent", {}).get("run_interval_minutes", 10),
            "max_jobs_per_run":    settings.get("agent", {}).get("max_jobs_per_run", 20),
            "credentials": {
                "approval_email":    settings.get("agent", {}).get("approval_email", ""),
                "approval_base_url": os.getenv("APPROVAL_BASE_URL", ""),
                "smtp_host":         os.getenv("SMTP_HOST", "smtp.gmail.com"),
                "smtp_port":         int(os.getenv("SMTP_PORT", "587")),
                "smtp_user":         os.getenv("SMTP_USER", ""),
                "smtp_password":     os.getenv("SMTP_PASSWORD", ""),
                "li_at":             os.getenv("LI_AT", ""),
                "li_user_email":     os.getenv("LI_USER_EMAIL", ""),
                "li_user_phone":     os.getenv("LI_USER_PHONE", ""),
            },
        }
    except Exception:
        return {
            "primary_keywords": [], "secondary_keywords": [], "exclude_keywords": [],
            "locations": [], "experience_levels": ["mid-senior"], "job_types": ["full-time"],
            "min_relevance_score": 60, "schedule_minutes": 10, "max_jobs_per_run": 20,
            "credentials": {
                "approval_email": "", "approval_base_url": "", "smtp_host": "smtp.gmail.com",
                "smtp_port": 587, "smtp_user": "", "smtp_password": "",
                "li_at": "", "li_user_email": "", "li_user_phone": "",
            },
        }

def load_config(user_id: int = 0) -> dict:
    if use_db():
        saved = _db_get(_uk(user_id, _CONFIG_KEY))
        if saved:
            if "credentials" not in saved:
                saved["credentials"] = _default_config()["credentials"]
            return saved
    return _default_config()

def save_config(config: dict, user_id: int = 0):
    if use_db():
        _db_set(_uk(user_id, _CONFIG_KEY), config)


# ── Run trigger ───────────────────────────────────────────────────────────────

def get_trigger(user_id: int = 0) -> bool:
    if use_db():
        return bool(_db_get(_uk(user_id, _TRIGGER_KEY)))
    return False

def set_trigger(user_id: int = 0):
    if use_db():
        _db_set(_uk(user_id, _TRIGGER_KEY), True)

def clear_trigger(user_id: int = 0):
    if use_db():
        _db_set(_uk(user_id, _TRIGGER_KEY), False)


# ── Agent status ──────────────────────────────────────────────────────────────

def save_status(data: dict, user_id: int = 0):
    if use_db():
        existing = _db_get(_uk(user_id, _STATUS_KEY)) or {}
        existing.update(data)
        _db_set(_uk(user_id, _STATUS_KEY), existing)

def load_status(user_id: int = 0) -> dict:
    if use_db():
        return _db_get(_uk(user_id, _STATUS_KEY)) or {}
    return {}


# ── Resume ────────────────────────────────────────────────────────────────────

def save_resume(text: str, filename: str, base64_data: str, user_id: int = 0):
    from datetime import datetime as _dt
    _db_set(_uk(user_id, _RESUME_KEY), {
        "text":        text,
        "filename":    filename,
        "base64":      base64_data,
        "uploaded_at": _dt.utcnow().isoformat(),
    })

def load_resume(user_id: int = 0) -> dict:
    if use_db():
        return _db_get(_uk(user_id, _RESUME_KEY)) or {}
    local = _ROOT / "data" / "resumes" / "base_resume.docx"
    if local.exists():
        try:
            from docx import Document
            doc = Document(str(local))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return {"text": text, "filename": "base_resume.docx", "uploaded_at": ""}
        except Exception:
            pass
    return {}


# ── ATS Scoring ───────────────────────────────────────────────────────────────

def ats_score(resume_text: str, job: dict) -> int:
    """
    Calculate ATS compatibility: what % of meaningful job keywords
    appear in the resume. Returns 0-100.
    """
    import re
    if not resume_text or not job.get("description"):
        return 0

    stop = {
        "the","and","for","are","this","that","with","have","from","they",
        "will","your","been","more","when","than","which","their","would",
        "about","could","should","these","those","also","into","over",
        "work","team","role","you","our","who","must","can","may","has",
        "its","all","any","but","not","we","or","in","of","to","a","an",
        "is","it","be","as","at","so","if","on","do","by","he","she",
        "was","had","his","her","they","we","you","i",
    }

    resume_words = {
        w for w in re.findall(r"\b[a-zA-Z]{3,}\b", resume_text.lower())
        if w not in stop
    }

    job_text  = f"{job.get('title','')} {job.get('description','')}"
    job_words = {
        w for w in re.findall(r"\b[a-zA-Z]{4,}\b", job_text.lower())
        if w not in stop
    }

    if not job_words:
        return 0

    matches = resume_words & job_words
    raw     = len(matches) / len(job_words)
    return min(100, int(raw * 300))  # scale: 33% word overlap → 100 ATS
