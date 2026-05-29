"""
orchestrator.py
───────────────
Main pipeline. Runs every 10 minutes, processing all pending job transitions.

Two-stage approval flow:
  Stage 1 — New job found → email user "Want to apply?"
  Stage 2 — User approves → tailor resume → email "Here's your resume, apply?"
  Apply   — User gives final OK → apply to job → record as applied (dedup guard)

Run:
  python orchestrator.py          # continuous, every 10 minutes
  python orchestrator.py --once   # single run and exit
"""

import argparse
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "settings.yaml") as f:
    SETTINGS = yaml.safe_load(f)

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_FILE = ROOT / SETTINGS["logging"]["log_file"]
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, SETTINGS["logging"]["level"]),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=SETTINGS["logging"]["max_log_size_mb"] * 1024 * 1024,
            backupCount=SETTINGS["logging"]["backup_count"],
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("orchestrator")

JOBS_FILE    = ROOT / "data" / "jobs" / "found_jobs.json"
APPLIED_FILE = ROOT / "data" / "jobs" / "applied_jobs.json"


# ── Storage helpers ────────────────────────────────────────────────────────────

def load_json(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _sync_db_to_local():
    """Pull latest jobs from Neon DB into the local file so all agents use current data."""
    from storage import use_db, load_jobs, save_jobs
    if use_db():
        jobs = load_jobs()
        save_json(JOBS_FILE, jobs)
        logger.debug(f"Synced {len(jobs)} jobs from Neon to local.")


def _push_new_jobs_to_db(new_jobs: list):
    """Append newly found jobs to Neon without overwriting existing statuses."""
    from storage import use_db, load_jobs, save_jobs
    if not use_db() or not new_jobs:
        return
    db_jobs = load_jobs()
    known_ids = {j["id"] for j in db_jobs}
    to_add = [j for j in new_jobs if j["id"] not in known_ids]
    if to_add:
        save_jobs(db_jobs + to_add)
        logger.debug(f"Pushed {len(to_add)} new job(s) to Neon.")


def _update_job(job_id: str, **updates):
    """Update a single job's fields in local file and Neon (read-modify-write).
    Read-modify-write on Neon prevents overwriting approval decisions made
    by the Vercel approval server between orchestrator runs."""
    ts = {"status_updated_at": datetime.utcnow().isoformat()}

    def _apply(jobs: list) -> list:
        for job in jobs:
            if job["id"] == job_id:
                job.update(updates)
                job.update(ts)
                break
        return jobs

    save_json(JOBS_FILE, _apply(load_json(JOBS_FILE)))

    from storage import use_db, load_jobs, save_jobs
    if use_db():
        save_jobs(_apply(load_jobs()))


# ── Pipeline steps ─────────────────────────────────────────────────────────────

def step_search() -> list[dict]:
    """Step 1: Find new jobs on LinkedIn (deduped against already-seen + applied)."""
    logger.info("=" * 60)
    logger.info("STEP 1 — Job Search")
    logger.info("=" * 60)

    from job_searcher import JobSearcher
    searcher = JobSearcher()
    new_jobs = searcher.run()  # writes existing + new to local JOBS_FILE

    _push_new_jobs_to_db(new_jobs)
    logger.info(f"Step 1 complete. {len(new_jobs)} new job(s) found.")
    return new_jobs


def step_notify_stage1(new_jobs: list[dict]):
    """Step 2: Send Stage 1 approval emails for newly found jobs."""
    logger.info("=" * 60)
    logger.info("STEP 2 — Stage 1 Notifications (Want to apply?)")
    logger.info("=" * 60)

    if not new_jobs:
        logger.info("No new jobs to notify about.")
        return

    from email_notifier import EmailNotifier
    notifier = EmailNotifier()
    sent = 0

    for job in new_jobs:
        approval_id = notifier.send_stage1_email(job)
        if approval_id:
            _update_job(
                job["id"],
                status="pending_stage1",
                approval_id=approval_id,
                notified_at=datetime.utcnow().isoformat(),
            )
            sent += 1
            logger.info(f"  ✉️  Stage 1 email sent: {job['title']} @ {job['company']}")
        else:
            logger.warning(f"  Failed to send Stage 1 email for {job['id']}")

    logger.info(f"Step 2 complete. Sent {sent} Stage 1 email(s).")


def step_tailor_and_notify_stage2():
    """Step 3: For Stage 1 approved jobs, tailor resume then send Stage 2 email."""
    logger.info("=" * 60)
    logger.info("STEP 3 — Resume Tailoring + Stage 2 Notifications (Approve to apply?)")
    logger.info("=" * 60)

    jobs = load_json(JOBS_FILE)
    approved1 = [j for j in jobs if j.get("status") == "approved_stage1"]

    if not approved1:
        logger.info("No Stage 1 approved jobs. Skipping.")
        return

    from resume_tailor import ResumeTailor
    from email_notifier import EmailNotifier
    tailor = ResumeTailor()
    notifier = EmailNotifier()

    for job in approved1:
        logger.info(f"  ✍️  Tailoring resume: {job['title']} @ {job['company']}")
        resume_path = tailor.tailor_for_job(job)

        if not resume_path:
            logger.error(f"  Resume tailoring failed for job {job['id']}")
            continue

        approval2_id = notifier.send_stage2_email(job, str(resume_path))
        if approval2_id:
            _update_job(
                job["id"],
                status="pending_stage2",
                tailored_resume=str(resume_path),
                approval2_id=approval2_id,
                notified2_at=datetime.utcnow().isoformat(),
            )
            logger.info(f"  ✉️  Stage 2 email sent: {job['title']} @ {job['company']}")

    logger.info("Step 3 complete.")


def step_apply():
    """Step 4: Apply to all Stage 2 approved jobs."""
    logger.info("=" * 60)
    logger.info("STEP 4 — Apply to Approved Jobs")
    logger.info("=" * 60)

    jobs = load_json(JOBS_FILE)
    approved2 = [j for j in jobs if j.get("status") == "approved_stage2"]

    if not approved2:
        logger.info("No Stage 2 approved jobs to apply to.")
        return

    from application_agent import ApplicationAgent
    agent = ApplicationAgent()

    for job in approved2:
        # If tailored via web UI (text stored but no .docx), build the .docx now
        if job.get("tailored_resume_text") and not job.get("tailored_resume"):
            docx_path = _build_docx_from_text(job)
            if docx_path:
                _update_job(job["id"], tailored_resume=str(docx_path))
                job = {**job, "tailored_resume": str(docx_path)}

        logger.info(f"  🚀 Applying: {job['title']} @ {job['company']}")
        ok = agent.apply(job)
        _update_job(
            job["id"],
            status="applied" if ok else "apply_failed",
        )

    applied = sum(1 for j in approved2 if True)  # logged per-job above
    logger.info(f"Step 4 complete. Processed {len(approved2)} application(s).")


# ── Main ───────────────────────────────────────────────────────────────────────

def check_env():
    """Warn about missing credentials but don't exit — they may be set in Neon config."""
    optional_warn = {
        "ANTHROPIC_API_KEY": "Claude AI key (resume tailoring will be disabled)",
        "SMTP_USER":         "Gmail address (email notifications will be disabled)",
        "SMTP_PASSWORD":     "Gmail App Password (email notifications will be disabled)",
    }
    for k, hint in optional_warn.items():
        if not os.getenv(k):
            logger.warning(f"{k} not set — {hint}. Add it in the web app Configuration page.")
    if not os.getenv("LI_AT"):
        logger.warning("LI_AT not set — LinkedIn Easy Apply disabled.")


def _build_docx_from_text(job: dict) -> Path | None:
    """Convert AI-tailored resume text (from web UI) into a .docx for application."""
    try:
        from resume_tailor import TAILORED_DIR, write_tailored_docx
        import re
        safe_co    = re.sub(r"[^\w\-]", "_", job.get("company", "Co"))
        safe_title = re.sub(r"[^\w\-]", "_", job.get("title", "Role"))[:30]
        path = TAILORED_DIR / f"{safe_title}_{safe_co}_{job['id'][:8]}.docx"
        if not path.exists():
            write_tailored_docx(job["tailored_resume_text"], job, path)
        return path
    except Exception as e:
        logger.warning(f"Could not build .docx from tailored text: {e}")
        return None


def _sync_resume_from_db():
    """If a resume was uploaded via the web UI, download it to local disk for tailoring."""
    from storage import load_resume, use_db
    if not use_db():
        return
    resume = load_resume()
    if not resume.get("base64"):
        return
    import base64
    dest = ROOT / "data" / "resumes" / "base_resume.docx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(resume["base64"]))
    logger.info(f"Resume synced from Neon: {resume.get('filename','')}")


def _apply_credentials():
    """Load credentials from Neon config and inject into env vars so all modules pick them up."""
    from storage import load_config, use_db
    if not use_db():
        return
    creds = load_config().get("credentials", {})
    mapping = {
        "smtp_host":       "SMTP_HOST",
        "smtp_port":       "SMTP_PORT",
        "smtp_user":       "SMTP_USER",
        "smtp_password":   "SMTP_PASSWORD",
        "approval_base_url": "APPROVAL_BASE_URL",
        "li_at":           "LI_AT",
        "li_user_email":   "LI_USER_EMAIL",
        "li_user_phone":   "LI_USER_PHONE",
    }
    for field, env_key in mapping.items():
        val = creds.get(field)
        if val:
            os.environ[env_key] = str(val)


def run_once():
    logger.info("=" * 60)
    logger.info(f"🤖 Pipeline run starting — {datetime.utcnow().isoformat()} UTC")
    logger.info("=" * 60)
    try:
        _apply_credentials()
        _sync_resume_from_db()
        _sync_db_to_local()

        new_jobs = step_search()
        step_notify_stage1(new_jobs)
        step_tailor_and_notify_stage2()
        step_apply()

        from storage import save_status, load_status
        st = load_status()
        save_status({
            "last_run":  datetime.utcnow().isoformat(),
            "run_count": st.get("run_count", 0) + 1,
        })
        logger.info("✅ Pipeline run complete.")
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.exception(f"Pipeline run failed: {e}")
        try:
            from email_notifier import EmailNotifier
            EmailNotifier().notify_error(f"Job Agent crashed: {e}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Job Agent Orchestrator")
    parser.add_argument("--once", action="store_true", help="Run pipeline once and exit")
    args = parser.parse_args()

    # Load credentials from Neon first so check_env sees them
    _apply_credentials()
    check_env()
    run_once()  # always run immediately on start

    if not args.once:
        from storage import load_config, get_trigger, clear_trigger
        interval = load_config().get("schedule_minutes", 10)
        schedule.every(interval).minutes.do(run_once)
        logger.info(f"⏰ Scheduler active — running every {interval} minute(s). Ctrl+C to stop.")
        try:
            while True:
                schedule.run_pending()
                if get_trigger():
                    logger.info("🔔 Manual trigger received from dashboard.")
                    clear_trigger()
                    run_once()
                time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Agent stopped by user.")


if __name__ == "__main__":
    main()
