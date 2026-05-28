"""
approval_server.py
──────────────────
Flask web app serving:
  /              — Dashboard: job stats + recent jobs
  /jobs          — Full jobs list
  /config        — Search configuration (tech stack, locations, schedule)
  /approve1/<id> — Stage 1: user approves job → triggers resume tailoring
  /skip/<id>     — Stage 1: skip this job
  /approve2/<id> — Stage 2: final approval → agent will apply
  /decline2/<id> — Stage 2: decline after seeing resume
  /status        — JSON status summary
  /health        — JSON health check
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

load_dotenv()

from storage import load_config, load_jobs, save_config, save_jobs

logger = logging.getLogger(__name__)
app = Flask(__name__)

# ── Shared layout ─────────────────────────────────────────────────────────────

BASE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Agent — {{ page_title }}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',Arial,sans-serif;min-height:100vh}
a{color:#0ea5e9;text-decoration:none}
a:hover{text-decoration:underline}

/* Nav */
nav{background:#1e293b;border-bottom:1px solid #334155;padding:0 32px;display:flex;align-items:center;gap:32px;height:56px}
nav .brand{font-size:17px;font-weight:700;color:#f1f5f9;margin-right:auto}
nav a{color:#94a3b8;font-size:14px;font-weight:500;padding:6px 0;border-bottom:2px solid transparent}
nav a.active,nav a:hover{color:#e2e8f0;border-bottom-color:#0ea5e9;text-decoration:none}

/* Page wrapper */
.page{max-width:1100px;margin:0 auto;padding:32px 24px}
h2{font-size:20px;font-weight:700;margin-bottom:20px;color:#f1f5f9}

/* Stat cards */
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:16px;margin-bottom:32px}
.stat{background:#1e293b;border-radius:12px;padding:20px;text-align:center;border:1px solid #334155}
.stat .num{font-size:32px;font-weight:800;line-height:1}
.stat .lbl{font-size:12px;color:#64748b;margin-top:6px;text-transform:uppercase;letter-spacing:.5px}

/* Table */
.table-wrap{background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#0f172a;color:#64748b;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.5px;padding:12px 16px;text-align:left}
td{padding:12px 16px;border-top:1px solid #1e3a5f22;vertical-align:middle}
tr:hover td{background:#1e3a5f22}

/* Badges */
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700}
.b-new{background:#334155;color:#94a3b8}
.b-pending{background:#f59e0b22;color:#f59e0b}
.b-approved{background:#0ea5e922;color:#0ea5e9}
.b-applied{background:#22c55e22;color:#22c55e}
.b-skipped,.b-declined{background:#ef444422;color:#ef4444}
.b-failed{background:#ef444422;color:#ef4444}

/* Buttons */
.btn{display:inline-block;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:700;cursor:pointer;border:none;text-decoration:none}
.btn-green{background:#22c55e;color:#fff}
.btn-red{background:#ef4444;color:#fff}
.btn-gray{background:#334155;color:#94a3b8}
.btn-blue{background:#0ea5e9;color:#fff}
.btn:hover{opacity:.85;text-decoration:none}

/* Forms */
.form-card{background:#1e293b;border-radius:12px;padding:28px;border:1px solid #334155;margin-bottom:24px}
.form-card h3{font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:16px}
label{display:block;font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
textarea,input[type=number],input[type=text],select{
  width:100%;background:#0f172a;border:1px solid #334155;border-radius:8px;
  color:#e2e8f0;padding:10px 14px;font-size:14px;font-family:inherit;
  outline:none;transition:border-color .2s}
textarea:focus,input:focus{border-color:#0ea5e9}
textarea{resize:vertical;min-height:120px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.hint{font-size:11px;color:#475569;margin-top:4px}
.save-btn{margin-top:20px;padding:12px 32px;background:#0ea5e9;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;width:100%}
.save-btn:hover{background:#0284c7}
.flash{padding:12px 16px;border-radius:8px;margin-bottom:20px;font-size:14px}
.flash-ok{background:#22c55e22;color:#22c55e;border:1px solid #22c55e44}
.flash-err{background:#ef444422;color:#ef4444;border:1px solid #ef444444}
</style>
</head>
<body>
<nav>
  <span class="brand">🤖 Job Agent</span>
  <a href="/" class="{{ 'active' if active=='dashboard' }}">Dashboard</a>
  <a href="/jobs" class="{{ 'active' if active=='jobs' }}">Jobs</a>
  <a href="/config" class="{{ 'active' if active=='config' }}">Configuration</a>
</nav>
<div class="page">
{% block content %}{% endblock %}
</div>
</body></html>"""


def _render(template, **ctx):
    full = BASE.replace("{% block content %}{% endblock %}", template)
    return render_template_string(full, **ctx)


# ── Helpers ───────────────────────────────────────────────────────────────────

STATUS_CLASS = {
    "new":            "b-new",
    "pending_stage1": "b-pending",
    "approved_stage1":"b-approved",
    "pending_stage2": "b-pending",
    "approved_stage2":"b-approved",
    "applied":        "b-applied",
    "skipped":        "b-skipped",
    "declined_stage2":"b-declined",
    "apply_failed":   "b-failed",
}

STATUS_LABEL = {
    "new":            "New",
    "pending_stage1": "⏳ Awaiting Stage 1",
    "approved_stage1":"✅ Stage 1 OK",
    "pending_stage2": "⏳ Awaiting Final OK",
    "approved_stage2":"✅ Final OK",
    "applied":        "🚀 Applied",
    "skipped":        "⏭️ Skipped",
    "declined_stage2":"❌ Declined",
    "apply_failed":   "❌ Apply Failed",
}


def _badge(status):
    cls = STATUS_CLASS.get(status, "b-new")
    lbl = STATUS_LABEL.get(status, status)
    return f'<span class="badge {cls}">{lbl}</span>'


def _time_ago(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (datetime.now(timezone.utc) - dt).total_seconds()
        if diff < 60:    return "just now"
        if diff < 3600:  return f"{int(diff/60)}m ago"
        if diff < 86400: return f"{int(diff/3600)}h ago"
        return f"{int(diff/86400)}d ago"
    except Exception:
        return "—"


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


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    jobs = load_jobs()
    cfg  = load_config()
    counts = {}
    for j in jobs:
        s = j.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1

    recent = sorted(jobs, key=lambda j: j.get("scraped_at", ""), reverse=True)[:10]

    return _render("""
<h2>Dashboard</h2>

<div class="stats">
  <div class="stat"><div class="num">{{ total }}</div><div class="lbl">Total</div></div>
  <div class="stat"><div class="num" style="color:#f59e0b">{{ pending }}</div><div class="lbl">Pending</div></div>
  <div class="stat"><div class="num" style="color:#22c55e">{{ applied }}</div><div class="lbl">Applied</div></div>
  <div class="stat"><div class="num" style="color:#0ea5e9">{{ approved }}</div><div class="lbl">Approved</div></div>
  <div class="stat"><div class="num" style="color:#64748b">{{ skipped }}</div><div class="lbl">Skipped</div></div>
  <div class="stat"><div class="num" style="color:#6366f1">{{ schedule }}m</div><div class="lbl">Schedule</div></div>
</div>

<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
  <h2 style="margin:0">Recent Jobs</h2>
  <a href="/jobs" class="btn btn-gray">View all →</a>
</div>

<div class="table-wrap">
<table>
<thead><tr>
  <th>Job</th><th>Location</th><th>Score</th><th>Status</th><th>Found</th><th>Action</th>
</tr></thead>
<tbody>
{% for job in recent %}
<tr>
  <td>
    <div style="font-weight:600;color:#f1f5f9">{{ job.title }}</div>
    <div style="color:#64748b;font-size:12px">{{ job.company }}</div>
  </td>
  <td style="color:#94a3b8">{{ job.location }}</td>
  <td><span style="color:#0ea5e9;font-weight:700">{{ job.relevance_score }}%</span></td>
  <td>{{ badge(job.status) }}</td>
  <td style="color:#64748b">{{ time_ago(job.get('scraped_at','')) }}</td>
  <td>
    {% if job.status == 'pending_stage1' %}
      <a href="/approve1/{{ job.approval_id }}" class="btn btn-green" style="margin-right:4px">✅ Approve</a>
      <a href="/skip/{{ job.approval_id }}" class="btn btn-gray">Skip</a>
    {% elif job.status == 'pending_stage2' %}
      <a href="/approve2/{{ job.approval2_id }}" class="btn btn-blue" style="margin-right:4px">🚀 Apply</a>
      <a href="/decline2/{{ job.approval2_id }}" class="btn btn-red">Decline</a>
    {% elif job.apply_url %}
      <a href="{{ job.apply_url }}" target="_blank" class="btn btn-gray">View →</a>
    {% endif %}
  </td>
</tr>
{% else %}
<tr><td colspan="6" style="text-align:center;color:#475569;padding:32px">
  No jobs yet. Start the orchestrator to begin searching.
</td></tr>
{% endfor %}
</tbody>
</table>
</div>
""",
        page_title="Dashboard", active="dashboard",
        total=len(jobs),
        pending=sum(1 for j in jobs if "pending" in j.get("status", "")),
        applied=counts.get("applied", 0),
        approved=sum(1 for j in jobs if "approved" in j.get("status", "")),
        skipped=counts.get("skipped", 0),
        schedule=cfg.get("schedule_minutes", 10),
        recent=recent, badge=_badge, time_ago=_time_ago,
    )


# ── Jobs list ─────────────────────────────────────────────────────────────────

@app.route("/jobs")
def jobs_page():
    jobs = load_jobs()
    status_filter = request.args.get("status", "")
    if status_filter:
        jobs = [j for j in jobs if j.get("status") == status_filter]
    jobs = sorted(jobs, key=lambda j: j.get("scraped_at", ""), reverse=True)

    all_statuses = sorted({j.get("status", "") for j in load_jobs()})

    return _render("""
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px">
  <h2 style="margin:0">All Jobs ({{ jobs|length }})</h2>
  <div>
    <a href="/jobs" class="btn {{ 'btn-blue' if not status_filter else 'btn-gray' }}">All</a>
    {% for s in all_statuses %}
    <a href="/jobs?status={{ s }}" class="btn {{ 'btn-blue' if status_filter==s else 'btn-gray' }}" style="margin-left:4px">{{ s }}</a>
    {% endfor %}
  </div>
</div>

<div class="table-wrap">
<table>
<thead><tr>
  <th>Job</th><th>Location</th><th>Score</th><th>Status</th><th>Resume</th><th>Found</th><th>Action</th>
</tr></thead>
<tbody>
{% for job in jobs %}
<tr>
  <td>
    <div style="font-weight:600;color:#f1f5f9">
      {% if job.apply_url %}<a href="{{ job.apply_url }}" target="_blank" style="color:#f1f5f9">{{ job.title }}</a>{% else %}{{ job.title }}{% endif %}
    </div>
    <div style="color:#64748b;font-size:12px">{{ job.company }}</div>
  </td>
  <td style="color:#94a3b8;font-size:12px">{{ job.location }}</td>
  <td><span style="color:#0ea5e9;font-weight:700">{{ job.relevance_score }}%</span></td>
  <td>{{ badge(job.status) }}</td>
  <td style="color:#64748b;font-size:12px">{{ '✅' if job.tailored_resume else '—' }}</td>
  <td style="color:#64748b;font-size:12px">{{ time_ago(job.get('scraped_at','')) }}</td>
  <td>
    {% if job.status == 'pending_stage1' %}
      <a href="/approve1/{{ job.approval_id }}" class="btn btn-green" style="margin-right:4px">✅</a>
      <a href="/skip/{{ job.approval_id }}" class="btn btn-gray">Skip</a>
    {% elif job.status == 'pending_stage2' %}
      <a href="/approve2/{{ job.approval2_id }}" class="btn btn-blue" style="margin-right:4px">🚀</a>
      <a href="/decline2/{{ job.approval2_id }}" class="btn btn-red">✗</a>
    {% elif job.apply_url %}
      <a href="{{ job.apply_url }}" target="_blank" class="btn btn-gray">View</a>
    {% endif %}
  </td>
</tr>
{% else %}
<tr><td colspan="7" style="text-align:center;color:#475569;padding:32px">No jobs found.</td></tr>
{% endfor %}
</tbody>
</table>
</div>
""",
        page_title="Jobs", active="jobs",
        jobs=jobs, status_filter=status_filter,
        all_statuses=all_statuses, badge=_badge, time_ago=_time_ago,
    )


# ── Configuration ─────────────────────────────────────────────────────────────

@app.route("/config", methods=["GET", "POST"])
def config_page():
    flash = ""
    cfg = load_config()

    if request.method == "POST":
        try:
            def _lines(field):
                return [l.strip() for l in request.form.get(field, "").splitlines() if l.strip()]

            cfg["primary_keywords"]   = _lines("primary_keywords")
            cfg["secondary_keywords"] = _lines("secondary_keywords")
            cfg["exclude_keywords"]   = _lines("exclude_keywords")
            cfg["locations"]          = _lines("locations")
            cfg["min_relevance_score"] = int(request.form.get("min_relevance_score", 60))
            cfg["schedule_minutes"]   = int(request.form.get("schedule_minutes", 10))
            cfg["max_jobs_per_run"]   = int(request.form.get("max_jobs_per_run", 20))
            save_config(cfg)
            flash = "ok"
        except Exception as e:
            flash = f"err:{e}"

    def _nl(lst):
        return "\n".join(lst) if lst else ""

    return _render("""
{% if flash == 'ok' %}
<div class="flash flash-ok">✅ Configuration saved. The agent will use these settings on the next run.</div>
{% elif flash %}
<div class="flash flash-err">❌ {{ flash }}</div>
{% endif %}

<h2>Configuration</h2>
<form method="POST" action="/config">

<div class="form-card">
  <h3>🔍 Technology Stack — Primary Keywords</h3>
  <label>Job titles / roles to search for (one per line)</label>
  <textarea name="primary_keywords" placeholder="Python Developer&#10;DevOps Engineer&#10;Cloud Architect">{{ primary_keywords }}</textarea>
  <p class="hint">These are used as the main search query on LinkedIn.</p>
</div>

<div class="form-card">
  <h3>⭐ Secondary Keywords (Skill Matching)</h3>
  <label>Skills to match in the job description (one per line)</label>
  <textarea name="secondary_keywords" placeholder="Kubernetes&#10;Terraform&#10;AWS&#10;CI/CD&#10;Docker">{{ secondary_keywords }}</textarea>
  <p class="hint">Used to calculate the match score. More hits = higher score.</p>
</div>

<div class="form-card">
  <h3>🚫 Exclude Keywords</h3>
  <label>Skip any job containing these words in the title or description (one per line)</label>
  <textarea name="exclude_keywords" placeholder="Intern&#10;Junior&#10;Manager" style="min-height:80px">{{ exclude_keywords }}</textarea>
</div>

<div class="form-card">
  <h3>📍 Locations</h3>
  <label>Locations to search in (one per line)</label>
  <textarea name="locations" placeholder="Dubai, UAE&#10;Abu Dhabi, UAE&#10;Remote&#10;United Kingdom&#10;Germany">{{ locations }}</textarea>
  <p class="hint">Each location is searched separately for every keyword.</p>
</div>

<div class="form-card">
  <h3>⚙️ Agent Settings</h3>
  <div class="form-row">
    <div>
      <label>Minimum Match Score (%)</label>
      <input type="number" name="min_relevance_score" value="{{ min_score }}" min="0" max="100">
      <p class="hint">Jobs below this score are ignored.</p>
    </div>
    <div>
      <label>Search Interval (minutes)</label>
      <input type="number" name="schedule_minutes" value="{{ schedule }}" min="5" max="1440">
      <p class="hint">How often the local orchestrator polls LinkedIn.</p>
    </div>
  </div>
  <div style="margin-top:16px">
    <label>Max Jobs Per Run</label>
    <input type="number" name="max_jobs_per_run" value="{{ max_jobs }}" min="1" max="100" style="max-width:200px">
    <p class="hint">Stop searching after finding this many new jobs in one run.</p>
  </div>
</div>

<button type="submit" class="save-btn">💾 Save Configuration</button>
</form>
""",
        page_title="Configuration", active="config",
        flash=flash,
        primary_keywords=_nl(cfg.get("primary_keywords", [])),
        secondary_keywords=_nl(cfg.get("secondary_keywords", [])),
        exclude_keywords=_nl(cfg.get("exclude_keywords", [])),
        locations=_nl(cfg.get("locations", [])),
        min_score=cfg.get("min_relevance_score", 60),
        schedule=cfg.get("schedule_minutes", 10),
        max_jobs=cfg.get("max_jobs_per_run", 20),
    )


# ── Approval email routes ─────────────────────────────────────────────────────

RESP_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Job Agent</title>
<style>body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#1e293b;border-radius:16px;padding:48px;max-width:480px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.icon{font-size:64px;margin-bottom:16px}h1{margin:0 0 8px;font-size:24px}p{color:#94a3b8;line-height:1.6}
.co{color:#0ea5e9;font-weight:600}.back{margin-top:24px;display:inline-block;color:#0ea5e9;font-size:14px}</style>
</head><body><div class="card">
<div class="icon">{{ icon }}</div><h1>{{ title }}</h1><p>{{ message }}</p>
{% if job %}<p><span class="co">{{ job.title }} @ {{ job.company }}</span></p>{% endif %}
<a href="/" class="back">← Back to Dashboard</a>
</div></body></html>"""

def _resp(icon, title, message, job=None, status=200):
    return render_template_string(RESP_HTML, icon=icon, title=title, message=message, job=job), status


@app.route("/approve1/<approval_id>")
def approve1(approval_id):
    job = _find_by("approval_id", approval_id)
    if not job:
        return _resp("❌", "Not Found", "This link is invalid or already used.", status=404)
    if job.get("status") != "pending_stage1":
        return _resp("ℹ️", "Already Decided", f"This job is already: {job.get('status')}", job=job)
    _update("approval_id", approval_id, "approved_stage1")
    return _resp("✅", "Approved!", "Your agent will tailor your resume and send it for final review.", job=job)


@app.route("/skip/<approval_id>")
def skip(approval_id):
    job = _find_by("approval_id", approval_id)
    if not job:
        return _resp("❌", "Not Found", "This link is invalid or already used.", status=404)
    _update("approval_id", approval_id, "skipped")
    return _resp("⏭️", "Job Skipped", "Got it! This job has been removed from your queue.", job=job)


@app.route("/approve2/<approval2_id>")
def approve2(approval2_id):
    job = _find_by("approval2_id", approval2_id)
    if not job:
        return _resp("❌", "Not Found", "This link is invalid or already used.", status=404)
    if job.get("status") != "pending_stage2":
        return _resp("ℹ️", "Already Decided", f"This job is already: {job.get('status')}", job=job)
    _update("approval2_id", approval2_id, "approved_stage2")
    return _resp("🚀", "Final Approval Received!", "Your agent will apply within the next 10 minutes.", job=job)


@app.route("/decline2/<approval2_id>")
def decline2(approval2_id):
    job = _find_by("approval2_id", approval2_id)
    if not job:
        return _resp("❌", "Not Found", "This link is invalid or already used.", status=404)
    _update("approval2_id", approval2_id, "declined_stage2")
    return _resp("❌", "Application Declined", "Understood. This job has been removed from your queue.", job=job)


# ── Utility ───────────────────────────────────────────────────────────────────

@app.route("/status")
def status():
    jobs = load_jobs()
    counts = {}
    for j in jobs:
        s = j.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
    return jsonify({"total": len(jobs), "by_status": counts})


@app.route("/health")
def health():
    from storage import use_db
    return jsonify({"status": "ok", "storage": "neon" if use_db() else "local"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🌐 Approval server running at http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
