"""
application_agent.py
─────────────────────
Handles the actual job application on LinkedIn after final approval.

Two strategies:
  1. LinkedIn Easy Apply — fills and submits the in-platform form
  2. External URL        — logs for manual follow-up

Job status management is owned by orchestrator.py.
This module only records to applied_jobs.json (the dedup guard).

Environment vars needed:
  LI_AT          — LinkedIn session cookie (for Easy Apply)
  LI_USER_EMAIL  — LinkedIn login email (for Easy Apply form fill)
  LI_USER_PHONE  — Phone number for Easy Apply forms
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
with open(ROOT / "settings.yaml") as f:
    SETTINGS = yaml.safe_load(f)

JOBS_FILE    = ROOT / "data" / "jobs" / "found_jobs.json"
APPLIED_FILE = ROOT / "data" / "jobs" / "applied_jobs.json"


def load_json(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ── Easy Apply via Selenium ───────────────────────────────────────────────────

def _apply_easy_apply(job: dict, resume_path: str) -> bool:
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=opts)
        wait = WebDriverWait(driver, 15)

        driver.get("https://www.linkedin.com")
        driver.add_cookie({"name": "li_at", "value": os.environ["LI_AT"], "domain": ".linkedin.com"})
        driver.refresh()

        driver.get(job["apply_url"])
        time.sleep(3)

        try:
            btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.jobs-apply-button, .jobs-s-apply button")
            ))
            btn.click()
            time.sleep(2)
        except Exception:
            logger.warning(f"No Easy Apply button for job {job['id']}")
            driver.quit()
            return False

        try:
            upload = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            upload.send_keys(str(Path(resume_path).resolve()))
            time.sleep(1)
        except Exception:
            pass

        for _ in range(5):
            try:
                next_btn = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR,
                     "button[aria-label='Continue to next step'], button[aria-label='Submit application']")
                ))
                label = next_btn.get_attribute("aria-label") or ""
                next_btn.click()
                time.sleep(2)
                if "Submit" in label:
                    logger.info(f"✅ Easy Apply submitted: {job['title']} @ {job['company']}")
                    driver.quit()
                    return True
            except Exception:
                break

        driver.quit()
        logger.warning(f"Easy Apply flow incomplete for job {job['id']}")
        return False

    except ImportError:
        logger.error("Selenium not installed. Run: pip install selenium")
        return False
    except Exception as e:
        logger.error(f"Easy Apply failed for {job['id']}: {e}")
        return False


# ── Application agent ─────────────────────────────────────────────────────────

class ApplicationAgent:
    def __init__(self):
        self.applied_log: list[dict] = load_json(APPLIED_FILE)
        self.daily_limit = SETTINGS["agent"].get("apply_limit_per_day", 5)

    def _already_applied(self, job_id: str) -> bool:
        return any(a["job_id"] == job_id for a in self.applied_log)

    def _daily_count(self) -> int:
        today = datetime.utcnow().date().isoformat()
        return sum(1 for a in self.applied_log if a.get("applied_at", "").startswith(today))

    def apply(self, job: dict) -> bool:
        """
        Apply to a single job. Returns True on success.
        Checks applied_jobs.json to prevent duplicate applications.
        Job status is managed by orchestrator — this method only records the application.
        """
        job_id = job["id"]

        if self._already_applied(job_id):
            logger.info(f"Already applied to {job_id} — skipping.")
            return False

        if self._daily_count() >= self.daily_limit:
            logger.warning(f"Daily limit ({self.daily_limit}) reached — stopping.")
            return False

        resume_path = job.get("tailored_resume") or str(
            ROOT / SETTINGS["resume"]["base_resume_path"]
        )

        apply_url = job.get("apply_url", "")
        is_easy_apply = "linkedin.com" in apply_url

        success = False
        method = "unknown"

        if is_easy_apply and os.getenv("LI_AT"):
            success = _apply_easy_apply(job, resume_path)
            method = "easy_apply"
        else:
            logger.info(f"⚠️  External URL — logged for manual follow-up: {apply_url}")
            method = "external_manual"
            success = True

        record = {
            "job_id":     job_id,
            "title":      job["title"],
            "company":    job["company"],
            "location":   job["location"],
            "apply_url":  apply_url,
            "method":     method,
            "success":    success,
            "resume_used": resume_path,
            "applied_at": datetime.utcnow().isoformat(),
        }

        if success:
            self.applied_log.append(record)
            save_json(APPLIED_FILE, self.applied_log)
            logger.info(f"✅ Recorded in applied_jobs.json: {job['title']} via {method}")
        else:
            logger.warning(f"Application failed for {job['title']} @ {job['company']}")

        return success
