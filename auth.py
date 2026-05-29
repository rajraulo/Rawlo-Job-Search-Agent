"""
auth.py — User registration and login with bcrypt passwords.
Each user gets their own isolated jobs, resume, config, and credentials.
"""
import bcrypt
from storage import _get_conn


def _ensure_users_table():
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           SERIAL PRIMARY KEY,
                email        TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at   TIMESTAMPTZ DEFAULT now()
            )
        """)
        conn.commit()


def register(email: str, password: str) -> dict | None:
    """Create a new user. Returns user dict or None if email already taken."""
    email = email.lower().strip()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            _ensure_users_table()
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
                (email, pw_hash),
            )
            row = cur.fetchone()
            conn.commit()
            return {"id": row[0], "email": row[1]}
    except Exception:
        return None


def login(email: str, password: str) -> dict | None:
    """Verify credentials. Returns user dict or None on failure."""
    email = email.lower().strip()
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            _ensure_users_table()
            cur.execute(
                "SELECT id, email, password_hash FROM users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
        if not row:
            return None
        if bcrypt.checkpw(password.encode(), row[2].encode()):
            return {"id": row[0], "email": row[1]}
        return None
    except Exception:
        return None


def get_user_by_id(user_id: int) -> dict | None:
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            _ensure_users_table()
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        return {"id": row[0], "email": row[1]} if row else None
    except Exception:
        return None


def get_user_by_email(email: str) -> dict | None:
    email = email.lower().strip()
    try:
        with _get_conn() as conn, conn.cursor() as cur:
            _ensure_users_table()
            cur.execute("SELECT id, email FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
        return {"id": row[0], "email": row[1]} if row else None
    except Exception:
        return None
