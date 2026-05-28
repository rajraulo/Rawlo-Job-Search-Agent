"""
email_notifier.py
──────────────────
Sends two kinds of approval emails:

  Stage 1 — New job found: "Want to apply to this job?"
            Links: /approve1/<id>  /skip/<id>

  Stage 2 — Resume tailored: "Here's your tailored resume. Approve to apply?"
            Links: /approve2/<id>  /decline2/<id>

Environment vars needed:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
  APPROVAL_BASE_URL  — public URL of the approval server (e.g. https://agent-rawlo.vercel.app)
"""

import logging
import os
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
with open(ROOT / "settings.yaml") as f:
    SETTINGS = yaml.safe_load(f)

APPROVAL_EMAIL = SETTINGS["agent"]["approval_email"]


def _base_url() -> str:
    return os.getenv("APPROVAL_BASE_URL", "http://localhost:8080").rstrip("/")


def _read_docx_text(path: str) -> str:
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


# ── Stage 1 email ─────────────────────────────────────────────────────────────

def _stage1_html(job: dict, approval_id: str) -> str:
    base = _base_url()
    approve_url = f"{base}/approve1/{approval_id}"
    skip_url    = f"{base}/skip/{approval_id}"
    score_color = "#22c55e" if job["relevance_score"] >= 80 else "#f59e0b" if job["relevance_score"] >= 60 else "#ef4444"
    desc = (job.get("description") or "")[:800].replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:20px; }}
  .card {{ max-width:680px; margin:0 auto; background:#1e293b; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.4); }}
  .header {{ background:linear-gradient(135deg,#0ea5e9,#6366f1); padding:28px 32px; }}
  .header h1 {{ margin:0; font-size:22px; color:#fff; }}
  .header p  {{ margin:6px 0 0; color:rgba(255,255,255,.8); font-size:14px; }}
  .body {{ padding:28px 32px; }}
  .badge {{ background:#334155; padding:6px 12px; border-radius:20px; font-size:13px; margin-right:8px; display:inline-block; }}
  .score {{ background:{score_color}22; color:{score_color}; border:1px solid {score_color}44; padding:6px 14px; border-radius:20px; font-size:13px; font-weight:700; display:inline-block; }}
  .label {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px; color:#64748b; margin:20px 0 8px; }}
  .desc {{ background:#0f172a; border-radius:8px; padding:16px; font-size:13px; line-height:1.7; color:#94a3b8; }}
  .actions {{ display:flex; gap:16px; margin-top:28px; }}
  .btn {{ flex:1; padding:14px; border-radius:8px; font-size:15px; font-weight:700; text-align:center; text-decoration:none; display:block; }}
  .btn-approve {{ background:#22c55e; color:#fff; }}
  .btn-skip    {{ background:#334155; color:#94a3b8; }}
  .footer {{ padding:16px 32px; border-top:1px solid #334155; font-size:12px; color:#475569; }}
</style></head>
<body><div class="card">
  <div class="header">
    <h1>🤖 New Job Match</h1>
    <p>Your agent found a job that matches your profile. Approve to proceed.</p>
  </div>
  <div class="body">
    <h2 style="margin:0 0 4px;color:#f1f5f9;font-size:20px;">{job['title']}</h2>
    <p style="margin:0 0 16px;color:#0ea5e9;font-size:15px;">{job['company']}</p>
    <div style="margin-bottom:16px;">
      <span class="badge">📍 {job['location']}</span>
      <span class="badge">🗓️ {job.get('date_posted','N/A')}</span>
      <span class="score">⭐ {job['relevance_score']}% match</span>
    </div>
    <div class="label">Job Description Preview</div>
    <div class="desc">{desc}…</div>
    <div style="margin-top:12px;">
      <a href="{job.get('apply_url','#')}" style="color:#0ea5e9;font-size:13px;">🔗 View on LinkedIn →</a>
    </div>
    <div class="actions">
      <a href="{approve_url}" class="btn btn-approve">✅ Yes, I want to apply</a>
      <a href="{skip_url}"   class="btn btn-skip">⏭️ Skip this job</a>
    </div>
  </div>
  <div class="footer">Approval ID: {approval_id} &nbsp;|&nbsp; Sent by your Job Agent 🤖</div>
</div></body></html>"""


def _stage1_plain(job: dict) -> str:
    return f"""🤖 NEW JOB MATCH: {job['title']} at {job['company']}

Location : {job['location']}
Posted   : {job.get('date_posted','N/A')}
Match    : {job['relevance_score']}%
URL      : {job.get('apply_url','N/A')}

--- Description Preview ---
{(job.get('description') or '')[:500]}
...

Click the approve link in the HTML email above to proceed.
— Your Job Agent 🤖""".strip()


# ── Stage 2 email ─────────────────────────────────────────────────────────────

def _stage2_html(job: dict, approval2_id: str, resume_text: str) -> str:
    base = _base_url()
    approve_url  = f"{base}/approve2/{approval2_id}"
    decline_url  = f"{base}/decline2/{approval2_id}"
    resume_html  = resume_text.replace("\n", "<br>")[:6000]

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family:'Segoe UI',Arial,sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:20px; }}
  .card {{ max-width:700px; margin:0 auto; background:#1e293b; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.4); }}
  .header {{ background:linear-gradient(135deg,#7c3aed,#0ea5e9); padding:28px 32px; }}
  .header h1 {{ margin:0; font-size:22px; color:#fff; }}
  .header p  {{ margin:6px 0 0; color:rgba(255,255,255,.8); font-size:14px; }}
  .body {{ padding:28px 32px; }}
  .label {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px; color:#64748b; margin:20px 0 8px; }}
  .resume-box {{ background:#0f172a; border:1px solid #334155; border-radius:8px; padding:20px; font-size:13px; line-height:1.8; color:#cbd5e1; max-height:400px; overflow-y:auto; white-space:pre-wrap; font-family:monospace; }}
  .actions {{ display:flex; gap:16px; margin-top:28px; }}
  .btn {{ flex:1; padding:14px; border-radius:8px; font-size:15px; font-weight:700; text-align:center; text-decoration:none; display:block; }}
  .btn-apply   {{ background:#6366f1; color:#fff; }}
  .btn-decline {{ background:#334155; color:#94a3b8; }}
  .footer {{ padding:16px 32px; border-top:1px solid #334155; font-size:12px; color:#475569; }}
</style></head>
<body><div class="card">
  <div class="header">
    <h1>📄 Tailored Resume Ready</h1>
    <p>Review your tailored resume below. Give final approval to apply.</p>
  </div>
  <div class="body">
    <h2 style="margin:0 0 4px;color:#f1f5f9;font-size:20px;">{job['title']}</h2>
    <p style="margin:0 0 16px;color:#0ea5e9;font-size:15px;">{job['company']} &nbsp;·&nbsp; {job['location']}</p>
    <a href="{job.get('apply_url','#')}" style="color:#0ea5e9;font-size:13px;">🔗 View on LinkedIn →</a>
    <div class="label">Your Tailored Resume</div>
    <div class="resume-box">{resume_html}</div>
    <div class="actions">
      <a href="{approve_url}"  class="btn btn-apply">🚀 Apply with this resume</a>
      <a href="{decline_url}" class="btn btn-decline">❌ Don't apply</a>
    </div>
  </div>
  <div class="footer">Approval ID: {approval2_id} &nbsp;|&nbsp; Sent by your Job Agent 🤖</div>
</div></body></html>"""


def _stage2_plain(job: dict, resume_text: str) -> str:
    return f"""📄 TAILORED RESUME READY — {job['title']} at {job['company']}

Review the resume below and click Approve in the HTML email to apply.

--- Tailored Resume ---
{resume_text[:1000]}
...

— Your Job Agent 🤖""".strip()


# ── Notifier class ─────────────────────────────────────────────────────────────

class EmailNotifier:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASSWORD", "")

    def _send(self, to: str, subject: str, html: str, plain: str) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Job Agent Bot <{self.smtp_user}>"
        msg["To"] = to
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as srv:
                srv.ehlo()
                srv.starttls()
                srv.login(self.smtp_user, self.smtp_pass)
                srv.sendmail(self.smtp_user, to, msg.as_string())
            logger.info(f"📧 Email sent to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_stage1_email(self, job: dict) -> Optional[str]:
        """Send Stage 1 'Want to apply?' email. Returns approval_id on success."""
        approval_id = str(uuid.uuid4())
        subject = f"🤖 Job Match: {job['title']} at {job['company']} — Apply?"
        if self._send(APPROVAL_EMAIL, subject, _stage1_html(job, approval_id), _stage1_plain(job)):
            return approval_id
        return None

    def send_stage2_email(self, job: dict, resume_path: str) -> Optional[str]:
        """Send Stage 2 'Review resume + final approval' email. Returns approval2_id."""
        approval2_id = str(uuid.uuid4())
        resume_text = _read_docx_text(resume_path) or "(Could not read resume)"
        subject = f"📄 Resume Ready: {job['title']} at {job['company']} — Final Approval?"
        if self._send(APPROVAL_EMAIL, subject, _stage2_html(job, approval2_id, resume_text), _stage2_plain(job, resume_text)):
            return approval2_id
        return None

    def notify_applied(self, job: dict):
        subject = f"✅ Applied: {job['title']} at {job['company']}"
        plain = f"Your agent applied to {job['title']} at {job['company']}.\nURL: {job.get('apply_url','N/A')}"
        self._send(APPROVAL_EMAIL, subject, f"<p>{plain.replace(chr(10),'<br>')}</p>", plain)

    def notify_error(self, message: str):
        self._send(APPROVAL_EMAIL, "⚠️ Job Agent Error", f"<p>{message}</p>", message)
