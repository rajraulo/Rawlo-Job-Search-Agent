"""
approval_server.py
──────────────────
Flask app handling approve/skip/decline clicks from approval emails.
Deploy to Vercel for a permanent public URL (no ngrok needed).

Endpoints:
  GET /approve1/<id>  — Stage 1: user wants to apply (triggers resume tailoring)
  GET /skip/<id>      — Stage 1: user skips this job
  GET /approve2/<id>  — Stage 2: user approves the tailored resume → agent will apply
  GET /decline2/<id>  — Stage 2: user declines after seeing the resume
  GET /status         — JSON summary of all job statuses
  GET /health         — health check
"""

import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string

load_dotenv()

from storage import load_jobs, save_jobs

logger = logging.getLogger(__name__)
app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_by(field: str, value: str) -> dict | None:
    return next((j for j in load_jobs() if j.get(field) == value), None)


def _update(field: str, value: str, status: str):
    jobs = load_jobs()
    for job in jobs:
        if job.get(field) == value:
            job["status"] = status
            job["decision_at"] = datetime.utcnow().isoformat()
            break
    save_jobs(jobs)


# ── Response template ─────────────────────────────────────────────────────────

RESPONSE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Job Agent — {{ title }}</title>
  <style>
    body { background:#0f172a; color:#e2e8f0; font-family:'Segoe UI',sans-serif;
           display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }
    .card { background:#1e293b; border-radius:16px; padding:48px; max-width:480px; text-align:center;
            box-shadow:0 8px 32px rgba(0,0,0,.4); }
    .icon { font-size:64px; margin-bottom:16px; }
    h1   { margin:0 0 8px; font-size:24px; }
    p    { color:#94a3b8; line-height:1.6; }
    .co  { color:#0ea5e9; font-weight:600; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{{ icon }}</div>
    <h1>{{ title }}</h1>
    <p>{{ message }}</p>
    {% if job %}
    <p><span class="co">{{ job.title }} @ {{ job.company }}</span></p>
    {% endif %}
  </div>
</body>
</html>
"""

def _render(icon, title, message, job=None, status=200):
    return render_template_string(RESPONSE_HTML, icon=icon, title=title,
                                  message=message, job=job), status


# ── Stage 1 routes ─────────────────────────────────────────────────────────────

@app.route("/approve1/<approval_id>")
def approve1(approval_id: str):
    job = _find_by("approval_id", approval_id)
    if not job:
        return _render("❌", "Not Found", "This link is invalid or already used.", status=404)
    if job.get("status") not in ("pending_stage1",):
        return _render("ℹ️", "Already Decided", f"This job is already: {job.get('status')}", job=job)

    _update("approval_id", approval_id, "approved_stage1")
    logger.info(f"✅ Stage 1 approved: {job['title']} @ {job['company']}")
    return _render("✅", "Application Approved!", "Your agent will tailor your resume and send it to you for final review.", job=job)


@app.route("/skip/<approval_id>")
def skip(approval_id: str):
    job = _find_by("approval_id", approval_id)
    if not job:
        return _render("❌", "Not Found", "This link is invalid or already used.", status=404)
    if job.get("status") == "skipped":
        return _render("ℹ️", "Already Skipped", "This job was already skipped.", job=job)

    _update("approval_id", approval_id, "skipped")
    logger.info(f"⏭️  Skipped: {job.get('title')} @ {job.get('company')}")
    return _render("⏭️", "Job Skipped", "Got it! This job has been removed from your queue.", job=job)


# ── Stage 2 routes ─────────────────────────────────────────────────────────────

@app.route("/approve2/<approval2_id>")
def approve2(approval2_id: str):
    job = _find_by("approval2_id", approval2_id)
    if not job:
        return _render("❌", "Not Found", "This link is invalid or already used.", status=404)
    if job.get("status") not in ("pending_stage2",):
        return _render("ℹ️", "Already Decided", f"This job is already: {job.get('status')}", job=job)

    _update("approval2_id", approval2_id, "approved_stage2")
    logger.info(f"🚀 Stage 2 approved — will apply: {job['title']} @ {job['company']}")
    return _render("🚀", "Final Approval Received!", "Your agent will apply to this job in the next run (within 10 minutes).", job=job)


@app.route("/decline2/<approval2_id>")
def decline2(approval2_id: str):
    job = _find_by("approval2_id", approval2_id)
    if not job:
        return _render("❌", "Not Found", "This link is invalid or already used.", status=404)

    _update("approval2_id", approval2_id, "declined_stage2")
    logger.info(f"❌ Stage 2 declined: {job.get('title')} @ {job.get('company')}")
    return _render("❌", "Application Declined", "Understood. This job has been removed from your queue.", job=job)


# ── Utility routes ─────────────────────────────────────────────────────────────

@app.route("/status")
def status():
    jobs = load_jobs()
    counts = {}
    for j in jobs:
        s = j.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
    return jsonify({"total": len(jobs), "by_status": counts})


@app.route("/")
def index():
    jobs = load_jobs()
    counts = {}
    for j in jobs:
        s = j.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
    from storage import use_db
    storage = "neon" if use_db() else "local"
    return render_template_string("""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Job Agent</title>
<style>
  body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
  .card{background:#1e293b;border-radius:16px;padding:48px;max-width:480px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,.4)}
  h1{margin:0 0 8px;font-size:26px}
  p{color:#94a3b8;margin:4px 0}
  .badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:13px;margin:3px;background:#334155}
  .green{background:#22c55e22;color:#22c55e}
  .blue{background:#0ea5e922;color:#0ea5e9}
  .row{margin-top:24px}
</style></head>
<body><div class="card">
  <h1>🤖 Job Agent</h1>
  <p style="color:#0ea5e9">Approval server is running &nbsp;·&nbsp; Storage: {{ storage }}</p>
  <div class="row">
    {% for status, count in counts.items() %}
    <span class="badge">{{ status }}: {{ count }}</span>
    {% endfor %}
    {% if not counts %}<span class="badge">No jobs yet</span>{% endif %}
  </div>
  <div class="row" style="font-size:13px;color:#475569">
    <p>Endpoints: /approve1/&lt;id&gt; &nbsp; /skip/&lt;id&gt; &nbsp; /approve2/&lt;id&gt; &nbsp; /decline2/&lt;id&gt;</p>
    <p><a href="/status" style="color:#0ea5e9">/status</a> &nbsp; <a href="/health" style="color:#0ea5e9">/health</a></p>
  </div>
</div></body></html>
""", counts=counts, storage=storage)


@app.route("/health")
def health():
    from storage import use_db
    return jsonify({"status": "ok", "storage": "neon" if use_db() else "local"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🌐 Approval server running at http://localhost:8080")
    print("   Set APPROVAL_BASE_URL=http://localhost:8080 in .env for local testing.")
    app.run(host="0.0.0.0", port=8080, debug=False)
