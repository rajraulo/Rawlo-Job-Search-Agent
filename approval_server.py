"""
approval_server.py — Flask web app (runs on Vercel)

Pages:
  /          Dashboard: stats, recent jobs, Search Now button, schedule info
  /jobs      Full jobs list with filters
  /config    Search config (keywords, locations, schedule, credentials)
  /trigger   POST — triggers an immediate search on the local orchestrator

Approval email endpoints:
  /approve1/<id>   Stage 1: proceed with this job
  /skip/<id>       Stage 1: skip
  /approve2/<id>   Stage 2: apply with this resume
  /decline2/<id>   Stage 2: decline
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

load_dotenv()

from storage import (
    clear_trigger, get_trigger, load_config, load_jobs, load_status,
    save_config, save_jobs, set_trigger, use_db,
)

logger = logging.getLogger(__name__)
app = Flask(__name__)

# ── Layout ────────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',Arial,sans-serif;min-height:100vh}
a{color:#0ea5e9;text-decoration:none}a:hover{text-decoration:underline}
nav{background:#1e293b;border-bottom:1px solid #334155;padding:0 32px;display:flex;align-items:center;gap:0;height:56px}
.brand{font-size:17px;font-weight:700;color:#f1f5f9;margin-right:auto}
nav a{color:#94a3b8;font-size:14px;font-weight:500;padding:0 16px;height:56px;display:flex;align-items:center;border-bottom:2px solid transparent}
nav a.active,nav a:hover{color:#e2e8f0;border-bottom-color:#0ea5e9;text-decoration:none}
.page{max-width:1140px;margin:0 auto;padding:32px 24px}
h2{font-size:20px;font-weight:700;color:#f1f5f9;margin-bottom:20px}
.row{display:flex;gap:16px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:14px;margin-bottom:28px}
.stat{background:#1e293b;border-radius:12px;padding:18px 14px;text-align:center;border:1px solid #334155}
.stat .num{font-size:30px;font-weight:800;line-height:1}
.stat .lbl{font-size:11px;color:#64748b;margin-top:5px;text-transform:uppercase;letter-spacing:.5px}
.info-bar{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 20px;margin-bottom:24px;display:flex;gap:32px;flex-wrap:wrap;align-items:center;font-size:13px}
.info-bar .item{display:flex;flex-direction:column;gap:2px}
.info-bar .item .key{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#64748b;font-weight:600}
.info-bar .item .val{color:#e2e8f0;font-weight:600}
.wrap{background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#0f172a;color:#64748b;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.5px;padding:11px 16px;text-align:left}
td{padding:11px 16px;border-top:1px solid #1e3a5f18;vertical-align:middle}
tr:hover td{background:#1e3a5f20}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700}
.b-new{background:#334155;color:#94a3b8}
.b-p1{background:#f59e0b22;color:#f59e0b}.b-p2{background:#f59e0b22;color:#f59e0b}
.b-a1{background:#0ea5e922;color:#0ea5e9}.b-a2{background:#6366f122;color:#6366f1}
.b-applied{background:#22c55e22;color:#22c55e}
.b-skip{background:#ef444422;color:#ef4444}.b-dec{background:#ef444422;color:#ef4444}
.b-fail{background:#ef444422;color:#ef4444}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 16px;border-radius:7px;font-size:13px;font-weight:700;cursor:pointer;border:none;text-decoration:none;transition:opacity .15s}
.btn:hover{opacity:.82;text-decoration:none}
.btn-green{background:#22c55e;color:#fff}.btn-red{background:#ef4444;color:#fff}
.btn-gray{background:#334155;color:#94a3b8}.btn-blue{background:#0ea5e9;color:#fff}
.btn-purple{background:#6366f1;color:#fff}.btn-orange{background:#f59e0b;color:#0f172a}
.btn-sm{padding:5px 11px;font-size:12px}
.card{background:#1e293b;border-radius:12px;padding:24px;border:1px solid #334155;margin-bottom:20px}
.card h3{font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #334155}
label{display:block;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;margin-top:14px}
label:first-child{margin-top:0}
input[type=text],input[type=email],input[type=password],input[type=number],textarea,select{
  width:100%;background:#0f172a;border:1px solid #334155;border-radius:7px;color:#e2e8f0;
  padding:9px 13px;font-size:13px;font-family:inherit;outline:none;transition:border-color .2s}
input:focus,textarea:focus{border-color:#0ea5e9}
textarea{resize:vertical;min-height:110px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:600px){.form-grid{grid-template-columns:1fr}}
.hint{font-size:11px;color:#475569;margin-top:3px}
.set-indicator{font-size:11px;font-weight:700;margin-left:6px}
.is-set{color:#22c55e}.not-set{color:#ef4444}
.save-btn{width:100%;margin-top:20px;padding:13px;background:#0ea5e9;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer}
.save-btn:hover{background:#0284c7}
.flash{padding:12px 16px;border-radius:8px;margin-bottom:20px;font-size:14px;font-weight:600}
.flash-ok{background:#22c55e22;color:#22c55e;border:1px solid #22c55e44}
.flash-err{background:#ef444422;color:#ef4444;border:1px solid #ef444444}
.empty{text-align:center;color:#475569;padding:40px;font-size:14px}
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
details[open] summary span{transform:rotate(90deg);display:inline-block}
details summary::-webkit-details-marker{display:none}
kbd{font-family:monospace}
.upload-zone{border:2px dashed #334155;border-radius:12px;padding:32px;text-align:center;cursor:pointer;transition:border-color .2s;background:#0f172a}
.upload-zone:hover,.upload-zone.drag{border-color:#0ea5e9;background:#0ea5e908}
.upload-zone input{display:none}
.ats-bar{height:8px;border-radius:4px;background:#1e293b;overflow:hidden;margin-top:4px}
.ats-fill{height:100%;border-radius:4px;transition:width .4s}
.ats-green{background:#22c55e}.ats-yellow{background:#f59e0b}.ats-red{background:#ef4444}
.score-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700}
.pill-green{background:#22c55e22;color:#22c55e}.pill-yellow{background:#f59e0b22;color:#f59e0b}.pill-red{background:#ef444422;color:#ef4444}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.two-col{grid-template-columns:1fr}}
.schedule-panel{background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:20px;margin-top:12px;display:none}
.schedule-panel.open{display:block}
.active-tab{color:#e2e8f0 !important;border-bottom-color:#6366f1 !important}
"""

NAV = """<nav>
  <span class="brand">🤖 Job Agent</span>
  <a href="/" class="{d}">Dashboard</a>
  <a href="/search" class="{s}">Search &amp; Results</a>
  <a href="/jobs" class="{j}">All Jobs</a>
  <a href="/config" class="{c}">Configuration</a>
</nav>"""

def _page(active, content, title="Job Agent", extra_head=""):
    nav = NAV.format(
        d="active" if active == "d" else "",
        s="active" if active == "s" else "",
        j="active" if active == "j" else "",
        c="active" if active == "c" else "",
    )
    return render_template_string(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style>{extra_head}</head>
<body>{nav}<div class="page">{content}</div></body></html>""")


# ── Helpers ───────────────────────────────────────────────────────────────────

BADGE = {
    "new":            ("b-new",    "New"),
    "pending_stage1": ("b-p1",     "⏳ Awaiting Approval"),
    "approved_stage1":("b-a1",     "✅ Proceed"),
    "pending_stage2": ("b-p2",     "⏳ Awaiting Final OK"),
    "approved_stage2":("b-a2",     "✅ Apply"),
    "applied":        ("b-applied","🚀 Applied"),
    "skipped":        ("b-skip",   "⏭️ Skipped"),
    "declined_stage2":("b-dec",    "❌ Declined"),
    "apply_failed":   ("b-fail",   "❌ Failed"),
}

def _badge(status):
    cls, lbl = BADGE.get(status, ("b-new", status))
    return f'<span class="badge {cls}">{lbl}</span>'

def _ago(iso):
    if not iso: return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
        s = (datetime.now(timezone.utc) - dt).total_seconds()
        if s < 60:    return "just now"
        if s < 3600:  return f"{int(s/60)}m ago"
        if s < 86400: return f"{int(s/3600)}h ago"
        return f"{int(s/86400)}d ago"
    except: return "—"

def _find(field, val):
    return next((j for j in load_jobs() if j.get(field) == val), None)

def _update(field, val, status):
    jobs = load_jobs()
    for j in jobs:
        if j.get(field) == val:
            j["status"] = status
            j["decision_at"] = datetime.utcnow().isoformat()
            break
    save_jobs(jobs)

_TERMINAL = {"applied", "skipped", "declined_stage2", "apply_failed"}

def _action_btns(job):
    s    = job.get("status", "")
    aid  = job.get("approval_id", "")
    aid2 = job.get("approval2_id", "")
    url  = job.get("apply_url", "")
    jid  = job.get("id", "")

    apply_btn = f'<a href="/apply/{jid}" class="btn btn-purple btn-sm">✏️ Apply</a>'

    if s in _TERMINAL:
        if url: return f'<a href="{url}" target="_blank" class="btn btn-gray btn-sm">View ↗</a>'
        return ""
    if s == "pending_stage1":
        return (f'<a href="/approve1/{aid}" class="btn btn-green btn-sm">✅</a> '
                f'<a href="/skip/{aid}" class="btn btn-gray btn-sm">Skip</a> '
                f'{apply_btn}')
    if s == "pending_stage2":
        return (f'<a href="/approve2/{aid2}" class="btn btn-blue btn-sm">🚀</a> '
                f'<a href="/decline2/{aid2}" class="btn btn-red btn-sm">✗</a> '
                f'{apply_btn}')
    return apply_btn


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    jobs   = load_jobs()
    cfg    = load_config()
    status = load_status()

    counts = {}
    for j in jobs:
        k = j.get("status", "unknown")
        counts[k] = counts.get(k, 0) + 1

    recent = sorted(jobs, key=lambda j: j.get("scraped_at", ""), reverse=True)[:12]

    schedule_min = cfg.get("schedule_minutes", 10)
    last_run     = status.get("last_run", "")
    run_count    = status.get("run_count", 0)
    triggered    = get_trigger()

    rows = ""
    for job in recent:
        rows += f"""<tr>
          <td><div style="font-weight:600;color:#f1f5f9">{job.get('title','')}</div>
              <div style="color:#64748b;font-size:12px">{job.get('company','')}</div></td>
          <td style="color:#94a3b8;font-size:12px">{job.get('location','')}</td>
          <td><span style="color:#0ea5e9;font-weight:700">{job.get('relevance_score',0)}%</span></td>
          <td>{_badge(job.get('status',''))}</td>
          <td style="color:#64748b;font-size:12px">{_ago(job.get('scraped_at',''))}</td>
          <td>{_action_btns(job)}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" class="empty">No jobs yet — click <b>Search Now</b> or start the orchestrator locally.</td></tr>'

    trigger_notice = ""
    if triggered:
        trigger_notice = '<div class="flash flash-ok" style="margin-bottom:16px">⏳ Search triggered — the local orchestrator will pick this up within 30 seconds.</div>'

    html = f"""
{trigger_notice}
<div class="row" style="margin-bottom:24px">
  <h2 style="margin:0;flex:1">Dashboard</h2>
  <form method="POST" action="/trigger">
    <button type="submit" class="btn btn-orange" {'disabled style="opacity:.5;cursor:not-allowed"' if triggered else ''}>
      {'⏳ Search Pending…' if triggered else '🔍 Search Now'}
    </button>
  </form>
</div>

<div class="info-bar">
  <div class="item"><span class="key">Schedule</span><span class="val">Every {schedule_min} min</span></div>
  <div class="item"><span class="key">Last Run</span><span class="val">{_ago(last_run) if last_run else 'Never'}</span></div>
  <div class="item"><span class="key">Total Runs</span><span class="val">{run_count}</span></div>
  <div class="item"><span class="key">Storage</span><span class="val">{'🟢 Neon' if use_db() else '🟡 Local'}</span></div>
  <div class="item"><span class="key">Keywords</span><span class="val">{len(cfg.get('primary_keywords',[]))} configured</span></div>
  <div class="item"><span class="key">Locations</span><span class="val">{len(cfg.get('locations',[]))} configured</span></div>
</div>

<div class="stats">
  <div class="stat"><div class="num">{len(jobs)}</div><div class="lbl">Total</div></div>
  <div class="stat"><div class="num" style="color:#f59e0b">{sum(1 for j in jobs if 'pending' in j.get('status',''))}</div><div class="lbl">Pending</div></div>
  <div class="stat"><div class="num" style="color:#22c55e">{counts.get('applied',0)}</div><div class="lbl">Applied</div></div>
  <div class="stat"><div class="num" style="color:#0ea5e9">{sum(1 for j in jobs if 'approved' in j.get('status',''))}</div><div class="lbl">Approved</div></div>
  <div class="stat"><div class="num" style="color:#64748b">{counts.get('skipped',0)+counts.get('declined_stage2',0)}</div><div class="lbl">Skipped</div></div>
  <div class="stat"><div class="num" style="color:#ef4444">{counts.get('apply_failed',0)}</div><div class="lbl">Failed</div></div>
</div>

<div class="row"><h2 style="margin:0;flex:1">Recent Jobs</h2>
  <a href="/jobs" class="btn btn-gray btn-sm">View all →</a>
</div>
<div class="wrap"><table>
<thead><tr><th>Job</th><th>Location</th><th>Score</th><th>Status</th><th>Found</th><th>Action</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""

    return _page("d", html, "Dashboard")


# ── Trigger ───────────────────────────────────────────────────────────────────

@app.route("/trigger", methods=["POST"])
def trigger():
    if use_db():
        set_trigger()
    return redirect("/")


# ── Jobs list ─────────────────────────────────────────────────────────────────

@app.route("/jobs")
def jobs_page():
    all_jobs = load_jobs()
    sf = request.args.get("status", "")
    jobs = [j for j in all_jobs if j.get("status") == sf] if sf else all_jobs
    jobs = sorted(jobs, key=lambda j: j.get("scraped_at", ""), reverse=True)

    statuses = sorted({j.get("status","") for j in all_jobs})
    filters = f'<a href="/jobs" class="btn btn-sm {"btn-blue" if not sf else "btn-gray"}">All ({len(all_jobs)})</a> '
    for s in statuses:
        n = sum(1 for j in all_jobs if j.get("status") == s)
        filters += f'<a href="/jobs?status={s}" class="btn btn-sm {"btn-blue" if sf==s else "btn-gray"}">{s} ({n})</a> '

    rows = ""
    for job in jobs:
        rows += f"""<tr>
          <td><div style="font-weight:600;color:#f1f5f9">
            {'<a href="'+job.get('apply_url','')+ '" target="_blank" style="color:#f1f5f9">'+job.get('title','')+'</a>' if job.get('apply_url') else job.get('title','')}
          </div><div style="color:#64748b;font-size:12px">{job.get('company','')}</div></td>
          <td style="color:#94a3b8;font-size:12px">{job.get('location','')}</td>
          <td><span style="color:#0ea5e9;font-weight:700">{job.get('relevance_score',0)}%</span></td>
          <td>{_badge(job.get('status',''))}</td>
          <td style="color:#64748b;font-size:11px">{'✅' if job.get('tailored_resume') else '—'}</td>
          <td style="color:#64748b;font-size:12px">{_ago(job.get('scraped_at',''))}</td>
          <td>{_action_btns(job)}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="7" class="empty">No jobs found.</td></tr>'

    html = f"""
<div class="row"><h2 style="margin:0;flex:1">Jobs ({len(jobs)})</h2></div>
<div class="filter-bar">{filters}</div>
<div class="wrap"><table>
<thead><tr><th>Job</th><th>Location</th><th>Score</th><th>Status</th><th>Resume</th><th>Found</th><th>Action</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""

    return _page("j", html, "Jobs")


# ── Search & Results ──────────────────────────────────────────────────────────

def _ats_pill(score: int) -> str:
    if score >= 70:
        return f'<span class="score-pill pill-green">🟢 {score}%</span>'
    if score >= 40:
        return f'<span class="score-pill pill-yellow">🟡 {score}%</span>'
    return f'<span class="score-pill pill-red">🔴 {score}%</span>'

def _ats_bar(score: int) -> str:
    cls = "ats-green" if score >= 70 else "ats-yellow" if score >= 40 else "ats-red"
    return f'<div class="ats-bar"><div class="ats-fill {cls}" style="width:{score}%"></div></div>'

def _extract_text(file_bytes: bytes, filename: str) -> str:
    import io
    if filename.lower().endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            raise ValueError(f"Could not read PDF: {e}")
    elif filename.lower().endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise ValueError(f"Could not read DOCX: {e}")
    raise ValueError("Only PDF and DOCX files are supported.")


@app.route("/search")
def search_page():
    from storage import ats_score, load_resume, get_trigger
    cfg      = load_config()
    resume   = load_resume()
    jobs     = load_jobs()
    status   = load_status()
    pending  = get_trigger()

    resume_text = resume.get("text", "")
    resume_name = resume.get("filename", "")
    resume_time = resume.get("uploaded_at", "")

    schedule_min = cfg.get("schedule_minutes", 10)
    last_run     = status.get("last_run", "")

    # Sort jobs by ATS score if resume available, else by relevance
    def _job_sort(j):
        s = ats_score(resume_text, j) if resume_text else j.get("relevance_score", 0)
        return -s
    jobs_sorted = sorted(jobs, key=_job_sort)

    # Build rows
    rows = ""
    for job in jobs_sorted:
        ats = ats_score(resume_text, job) if resume_text else None
        jsc = job.get("relevance_score", 0)
        jsc_cls = "pill-green" if jsc >= 70 else "pill-yellow" if jsc >= 40 else "pill-red"
        ats_col = (
            f'{_ats_pill(ats)}{_ats_bar(ats)}'
            if ats is not None else
            '<span style="color:#475569;font-size:12px">Upload resume</span>'
        )
        rows += f"""<tr>
          <td>
            <div style="font-weight:600;color:#f1f5f9">
              {'<a href="'+job.get('apply_url','')+ '" target="_blank" style="color:#f1f5f9">'+job.get('title','')+'</a>' if job.get('apply_url') else job.get('title','')}
            </div>
            <div style="color:#64748b;font-size:12px">{job.get('company','')}</div>
          </td>
          <td style="color:#94a3b8;font-size:12px">{job.get('location','')}</td>
          <td style="color:#64748b;font-size:12px">{job.get('date_posted','—')}</td>
          <td><span class="score-pill {jsc_cls}">{jsc}%</span></td>
          <td style="min-width:110px">{ats_col}</td>
          <td>{_badge(job.get('status',''))}</td>
          <td>{_action_btns(job)}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="7" class="empty">No jobs yet — click <b>Search Now</b> to start.</td></tr>'

    applied_flash = ""
    if request.args.get("applied"):
        applied_flash = """<div class="flash flash-ok" style="margin-bottom:20px">
          🚀 Job queued for application! The local orchestrator will apply within the next scheduled run.
        </div>"""

    pending_banner = applied_flash
    auto_refresh   = ""
    if pending:
        pending_banner = """<div style="background:#f59e0b22;border:1px solid #f59e0b44;border-radius:10px;
            padding:14px 18px;margin-bottom:20px;display:flex;gap:10px;align-items:center">
          <span style="font-size:20px">⏳</span>
          <div>
            <strong style="color:#f59e0b">Search in progress…</strong>
            <span style="color:#94a3b8;font-size:13px;margin-left:8px">
              The local orchestrator is running. This page will refresh automatically.
            </span>
          </div>
        </div>"""
        auto_refresh = '<script>setTimeout(()=>location.reload(),15000)</script>'

    resume_section = f"""
<div class="card" style="margin-bottom:24px">
  <h3 style="margin-bottom:16px">📄 Your Resume
    {'<span style="font-size:12px;color:#22c55e;font-weight:500;margin-left:8px">✅ '+resume_name+' &nbsp;·&nbsp; uploaded '+_ago(resume_time)+'</span>' if resume_name else
     '<span style="font-size:12px;color:#64748b;font-weight:500;margin-left:8px">Not uploaded yet</span>'}
  </h3>
  <form method="POST" action="/upload-resume" enctype="multipart/form-data" id="upload-form">
    <label for="resume-file" class="upload-zone" id="drop-zone">
      <input type="file" name="resume" id="resume-file" accept=".pdf,.docx"
             onchange="document.getElementById('upload-form').submit()">
      <div style="font-size:36px;margin-bottom:10px">{'📄' if resume_name else '📁'}</div>
      <div style="color:#e2e8f0;font-weight:600;margin-bottom:4px">
        {'Replace resume — drag & drop or click to browse' if resume_name else 'Upload your resume — drag & drop or click to browse'}
      </div>
      <div style="color:#64748b;font-size:13px">Supports PDF and DOCX · Auto-uploads on selection</div>
    </label>
  </form>
  {('<div style="margin-top:12px;padding:12px 16px;background:#0f172a;border-radius:8px;font-size:13px;color:#94a3b8">'
   '📊 ATS scores in the table below compare your resume against each job description in real time.</div>') if resume_name else ''}
</div>"""

    html = f"""
{pending_banner}
<div class="two-col" style="margin-bottom:20px;align-items:flex-start">
  <div>
    <h2 style="margin-bottom:16px">Search &amp; Results</h2>
    <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
      <form method="POST" action="/trigger" style="margin:0">
        <button type="submit" class="btn btn-orange" style="font-size:14px;padding:10px 22px"
                {'disabled style="opacity:.5"' if pending else ''}>
          {'⏳ Searching…' if pending else '🔍 Search Now'}
        </button>
      </form>
      <button onclick="document.getElementById('sched-panel').classList.toggle('open')"
              class="btn btn-gray" style="font-size:14px;padding:10px 22px" type="button">
        📅 Schedule Search
      </button>
    </div>
    <div class="schedule-panel" id="sched-panel">
      <div style="font-weight:700;color:#e2e8f0;margin-bottom:12px">⚙️ Schedule Configuration</div>
      <form method="POST" action="/save-schedule" style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
        <div>
          <label style="display:block;font-size:11px;color:#64748b;font-weight:700;
                        text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">
            Run every
          </label>
          <div style="display:flex;align-items:center;gap:8px">
            <input type="number" name="minutes" value="{schedule_min}" min="5" max="1440"
                   style="width:90px;background:#1e293b;border:1px solid #334155;border-radius:7px;
                          color:#e2e8f0;padding:8px 12px;font-size:14px;outline:none">
            <span style="color:#94a3b8;font-size:14px">minutes</span>
          </div>
        </div>
        <button type="submit" class="btn btn-blue">Save Schedule</button>
      </form>
      <div style="margin-top:12px;font-size:12px;color:#475569">
        Last run: {_ago(last_run) if last_run else 'Never'} &nbsp;·&nbsp;
        Next run: within {schedule_min} min of orchestrator polling &nbsp;·&nbsp;
        Restart orchestrator to apply new interval.
      </div>
    </div>
  </div>
  <div>{resume_section}</div>
</div>

<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
  <div style="font-size:14px;color:#64748b">{len(jobs)} job(s) found
    {' · sorted by ATS match' if resume_text else ' · upload resume for ATS comparison'}
  </div>
</div>

<div class="wrap"><table>
<thead><tr>
  <th>Job</th><th>Location</th><th>Posted</th>
  <th>Job Score</th>
  <th>{'📄 ATS Match' if resume_text else 'ATS Match'}</th>
  <th>Status</th><th>Action</th>
</tr></thead>
<tbody>{rows}</tbody>
</table></div>

<script>
const zone = document.getElementById('drop-zone');
if(zone){{
  zone.addEventListener('dragover', e=>{{e.preventDefault();zone.classList.add('drag')}});
  zone.addEventListener('dragleave', ()=>zone.classList.remove('drag'));
  zone.addEventListener('drop', e=>{{
    e.preventDefault(); zone.classList.remove('drag');
    const f = e.dataTransfer.files[0];
    if(f){{ const dt = new DataTransfer(); dt.items.add(f);
            document.getElementById('resume-file').files = dt.files;
            document.getElementById('upload-form').submit(); }}
  }});
}}
</script>
{auto_refresh}"""

    return _page("s", html, "Search & Results")


@app.route("/upload-resume", methods=["POST"])
def upload_resume():
    import base64
    from storage import save_resume
    f = request.files.get("resume")
    if not f or not f.filename:
        return redirect("/search")
    raw  = f.read()
    name = f.filename
    try:
        text = _extract_text(raw, name)
        b64  = base64.b64encode(raw).decode()
        save_resume(text, name, b64)
    except ValueError as e:
        pass  # silently continue — could show flash
    return redirect("/search")


@app.route("/save-schedule", methods=["POST"])
def save_schedule():
    try:
        minutes = max(5, int(request.form.get("minutes", 10)))
        cfg = load_config()
        cfg["schedule_minutes"] = minutes
        save_config(cfg)
    except Exception:
        pass
    return redirect("/search")


# ── Configuration ─────────────────────────────────────────────────────────────

@app.route("/config", methods=["GET", "POST"])
def config_page():
    flash = ""
    cfg = load_config()
    creds = cfg.get("credentials", {})

    if request.method == "POST":
        try:
            def lines(f): return [l.strip() for l in request.form.get(f,"").splitlines() if l.strip()]
            def keep(field, existing):
                val = request.form.get(field, "").strip()
                return val if val else existing  # keep existing if field left blank

            cfg["primary_keywords"]    = lines("primary_keywords")
            cfg["secondary_keywords"]  = lines("secondary_keywords")
            cfg["exclude_keywords"]    = lines("exclude_keywords")
            cfg["locations"]           = lines("locations")
            cfg["min_relevance_score"] = int(request.form.get("min_relevance_score", 60))
            cfg["schedule_minutes"]    = int(request.form.get("schedule_minutes", 10))
            cfg["max_jobs_per_run"]    = int(request.form.get("max_jobs_per_run", 20))

            cfg["credentials"] = {
                "approval_email":    keep("approval_email",    creds.get("approval_email","")),
                "approval_base_url": keep("approval_base_url", creds.get("approval_base_url","")),
                "smtp_host":         keep("smtp_host",         creds.get("smtp_host","smtp.gmail.com")),
                "smtp_port":         int(request.form.get("smtp_port") or creds.get("smtp_port", 587)),
                "smtp_user":         keep("smtp_user",         creds.get("smtp_user","")),
                "smtp_password":     keep("smtp_password",     creds.get("smtp_password","")),
                "li_at":             keep("li_at",             creds.get("li_at","")),
                "li_user_email":     keep("li_user_email",     creds.get("li_user_email","")),
                "li_user_phone":     keep("li_user_phone",     creds.get("li_user_phone","")),
                "anthropic_api_key": keep("anthropic_api_key", creds.get("anthropic_api_key","")),
            }
            save_config(cfg)
            creds = cfg["credentials"]
            flash = "ok"
        except Exception as e:
            flash = f"err:{e}"

    def nl(lst): return "\n".join(lst) if lst else ""
    def dot(field): return '<span class="set-indicator is-set">✅ Set</span>' if creds.get(field) else '<span class="set-indicator not-set">Not set</span>'

    flash_html = ""
    if flash == "ok":
        flash_html = '<div class="flash flash-ok">✅ Configuration saved. The agent will use these settings on the next run.</div>'
    elif flash:
        flash_html = f'<div class="flash flash-err">❌ {flash}</div>'

    html = f"""
{flash_html}
<h2>Configuration</h2>
<form method="POST" action="/config">

<div class="card">
  <h3>🔍 Job Search — Technology Stack</h3>
  <label>Primary Keywords — job titles to search on LinkedIn (one per line)</label>
  <textarea name="primary_keywords" placeholder="Python Developer&#10;DevOps Engineer&#10;Cloud Architect&#10;Site Reliability Engineer">{nl(cfg.get('primary_keywords',[]))}</textarea>
  <div class="hint">Each keyword is searched separately across all locations.</div>

  <label>Secondary Keywords — skills for match scoring (one per line)</label>
  <textarea name="secondary_keywords" placeholder="Kubernetes&#10;Terraform&#10;AWS&#10;Docker&#10;CI/CD&#10;Python&#10;Ansible">{nl(cfg.get('secondary_keywords',[]))}</textarea>
  <div class="hint">More matches in the job description = higher relevance score.</div>

  <label>Exclude Keywords — skip jobs containing these (one per line)</label>
  <textarea name="exclude_keywords" placeholder="Intern&#10;Junior&#10;Manager&#10;Director" style="min-height:80px">{nl(cfg.get('exclude_keywords',[]))}</textarea>
</div>

<div class="card">
  <h3>📍 Locations</h3>
  <label>Locations to search in (one per line)</label>
  <textarea name="locations" placeholder="Dubai, UAE&#10;Abu Dhabi, UAE&#10;Remote&#10;United Kingdom&#10;Germany&#10;Singapore">{nl(cfg.get('locations',[]))}</textarea>
  <div class="hint">Each location is searched for every keyword above.</div>
</div>

<div class="card">
  <h3>⚙️ Agent Settings</h3>
  <div class="form-grid">
    <div>
      <label>Search Interval (minutes)</label>
      <input type="number" name="schedule_minutes" value="{cfg.get('schedule_minutes',10)}" min="5" max="1440">
      <div class="hint">How often the local orchestrator polls LinkedIn. Restart orchestrator to apply.</div>
    </div>
    <div>
      <label>Minimum Match Score (%)</label>
      <input type="number" name="min_relevance_score" value="{cfg.get('min_relevance_score',60)}" min="0" max="100">
      <div class="hint">Jobs below this threshold are ignored.</div>
    </div>
  </div>
  <label style="margin-top:16px">Max New Jobs Per Run</label>
  <input type="number" name="max_jobs_per_run" value="{cfg.get('max_jobs_per_run',20)}" min="1" max="100" style="max-width:160px">
</div>

<div class="card">
  <h3>📧 Email & Notifications</h3>
  <div class="form-grid">
    <div>
      <label>Notification Email {dot('approval_email')}</label>
      <input type="email" name="approval_email" value="{creds.get('approval_email','')}" placeholder="you@gmail.com">
      <div class="hint">Where approval emails are sent.</div>
    </div>
    <div>
      <label>Approval Server URL {dot('approval_base_url')}</label>
      <input type="text" name="approval_base_url" value="{creds.get('approval_base_url','')}" placeholder="https://agent-rawlo.vercel.app">
      <div class="hint">Base URL for approve/skip links in emails.</div>
    </div>
  </div>
  <div class="form-grid" style="margin-top:4px">
    <div>
      <label>SMTP Username (Gmail) {dot('smtp_user')}</label>
      <input type="email" name="smtp_user" value="{creds.get('smtp_user','')}" placeholder="sender@gmail.com">
    </div>
    <div>
      <label>SMTP App Password {dot('smtp_password')}</label>
      <input type="password" name="smtp_password" placeholder="{'Leave blank to keep existing' if creds.get('smtp_password') else 'xxxx xxxx xxxx xxxx'}">
      <div class="hint">Use a Gmail App Password, not your real password.</div>
    </div>
  </div>
  <div class="form-grid" style="margin-top:4px">
    <div>
      <label>SMTP Host</label>
      <input type="text" name="smtp_host" value="{creds.get('smtp_host','smtp.gmail.com')}">
    </div>
    <div>
      <label>SMTP Port</label>
      <input type="number" name="smtp_port" value="{creds.get('smtp_port',587)}">
    </div>
  </div>
</div>

<div class="card">
  <h3>🤖 AI Resume Tailoring</h3>
  <label>Anthropic API Key {dot('anthropic_api_key')}</label>
  <input type="password" name="anthropic_api_key"
         placeholder="{'Leave blank to keep existing' if creds.get('anthropic_api_key') else 'sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx'}">
  <div class="hint">
    Required for AI-powered resume tailoring. Get your key at
    <a href="https://console.anthropic.com" target="_blank" style="color:#0ea5e9">console.anthropic.com</a>.
    Used when you click "Tailor Resume with AI" on the Apply page.
  </div>
</div>

<div class="card">
  <h3>🔗 LinkedIn Credentials <span style="font-size:12px;font-weight:500;color:#64748b;margin-left:8px">— Optional</span></h3>

  <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:18px;margin-bottom:16px">
    <div style="font-weight:700;color:#e2e8f0;font-size:13px;margin-bottom:10px">❓ Why is li_at needed?</div>
    <div style="color:#94a3b8;font-size:13px;line-height:1.7;margin-bottom:14px">
      <code style="background:#1e293b;padding:1px 6px;border-radius:4px;color:#0ea5e9">li_at</code> is
      <strong style="color:#e2e8f0">only used for one thing</strong> — automatically clicking
      <strong style="color:#e2e8f0">Easy Apply</strong> on LinkedIn. LinkedIn has no public API for job applications,
      so the agent uses a headless browser (Selenium) to open the job page and submit the form as you.
      The <code style="background:#1e293b;padding:1px 6px;border-radius:4px;color:#0ea5e9">li_at</code> cookie
      is your LinkedIn login session — it proves to LinkedIn that the browser is you.
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
      <div style="background:#22c55e11;border:1px solid #22c55e33;border-radius:8px;padding:12px">
        <div style="color:#22c55e;font-weight:700;margin-bottom:6px">✅ Works without li_at</div>
        <div style="color:#94a3b8;line-height:1.7">Search LinkedIn for jobs<br>Score &amp; filter results<br>Tailor resume with AI<br>Send approval emails</div>
      </div>
      <div style="background:#0ea5e911;border:1px solid #0ea5e933;border-radius:8px;padding:12px">
        <div style="color:#0ea5e9;font-weight:700;margin-bottom:6px">🚀 Also works with li_at</div>
        <div style="color:#94a3b8;line-height:1.7">Auto-submit Easy Apply<br>Upload tailored resume<br>Fill application forms<br><span style="color:#64748b">(external URLs still manual)</span></div>
      </div>
    </div>
  </div>

  <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:14px 18px;margin-bottom:16px;display:flex;gap:10px;align-items:flex-start">
    <span style="font-size:18px;line-height:1.4">🔒</span>
    <div style="color:#94a3b8;font-size:13px;line-height:1.6">
      <strong style="color:#e2e8f0">Your credentials are safe.</strong>
      Stored in your own private Neon database over encrypted SSL —
      never logged, never shared, never visible after saving.
      Revoke anytime by logging out of LinkedIn in that browser.
    </div>
  </div>

  <label>LinkedIn Session Cookie (li_at) {dot('li_at')}</label>
  <input type="password" name="li_at" placeholder="{'Leave blank to keep existing' if creds.get('li_at') else 'AQEDATxxxxxxxxxxxx — see instructions below'}">

  <details style="margin-top:12px;cursor:pointer">
    <summary style="font-size:13px;color:#0ea5e9;font-weight:600;list-style:none;display:flex;align-items:center;gap:6px;user-select:none">
      <span>▶</span> How to get your li_at cookie (step-by-step)
    </summary>
    <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:20px;margin-top:12px;font-size:13px;line-height:1.8">

      <div style="color:#64748b;margin-bottom:16px">Takes about 60 seconds. No extensions needed.</div>

      <div style="display:flex;flex-direction:column;gap:12px">

        <div style="display:flex;gap:12px;align-items:flex-start">
          <span style="background:#0ea5e9;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0">1</span>
          <div>Open <strong style="color:#e2e8f0">Google Chrome</strong> and go to
            <a href="https://www.linkedin.com" target="_blank" style="color:#0ea5e9">linkedin.com</a>.
            Make sure you are <strong style="color:#e2e8f0">logged in</strong> to your account.
          </div>
        </div>

        <div style="display:flex;gap:12px;align-items:flex-start">
          <span style="background:#0ea5e9;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:function700;font-size:12px;flex-shrink:0;font-weight:700">2</span>
          <div>Press <kbd style="background:#1e293b;border:1px solid #334155;padding:2px 8px;border-radius:4px;font-family:monospace;color:#e2e8f0">F12</kbd> on your keyboard to open <strong style="color:#e2e8f0">Developer Tools</strong>.
          </div>
        </div>

        <div style="display:flex;gap:12px;align-items:flex-start">
          <span style="background:#0ea5e9;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0">3</span>
          <div>Click the <strong style="color:#e2e8f0">Application</strong> tab in the top menu of Developer Tools.
            <div style="margin-top:6px;background:#1e293b;border-radius:6px;padding:8px 12px;font-family:monospace;color:#94a3b8;font-size:12px">
              Elements &nbsp;|&nbsp; Console &nbsp;|&nbsp; Sources &nbsp;|&nbsp;
              <span style="background:#0ea5e922;color:#0ea5e9;padding:2px 8px;border-radius:4px;border:1px solid #0ea5e944">Application</span>
              &nbsp;|&nbsp; Network …
            </div>
          </div>
        </div>

        <div style="display:flex;gap:12px;align-items:flex-start">
          <span style="background:#0ea5e9;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0">4</span>
          <div>In the <strong style="color:#e2e8f0">left panel</strong>, look for
            <strong style="color:#e2e8f0">Storage → Cookies → https://www.linkedin.com</strong>
            and click on it.
            <div style="margin-top:6px;background:#1e293b;border-radius:6px;padding:8px 12px;font-family:monospace;color:#94a3b8;font-size:12px;line-height:2">
              📁 Storage<br>
              &nbsp;&nbsp;🍪 Cookies<br>
              &nbsp;&nbsp;&nbsp;&nbsp;<span style="background:#0ea5e922;color:#0ea5e9;padding:1px 6px;border-radius:3px">https://www.linkedin.com</span>
            </div>
          </div>
        </div>

        <div style="display:flex;gap:12px;align-items:flex-start">
          <span style="background:#0ea5e9;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0">5</span>
          <div>In the table on the right, find the row where <strong style="color:#e2e8f0">Name = li_at</strong>.
            Click that row, then <strong style="color:#e2e8f0">double-click the Value column</strong> to select it all, and copy it.
            <div style="margin-top:6px;background:#1e293b;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:12px;line-height:2">
              <span style="color:#64748b">Name &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Value</span><br>
              <span style="background:#0ea5e922;padding:1px 4px;border-radius:3px">li_at</span>
              <span style="color:#22c55e">&nbsp;&nbsp;&nbsp;&nbsp; AQEDATB3… ← copy this</span>
            </div>
          </div>
        </div>

        <div style="display:flex;gap:12px;align-items:flex-start">
          <span style="background:#22c55e;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0">✓</span>
          <div>Paste the copied value into the <strong style="color:#e2e8f0">li_at field above</strong> and save.
            The value starts with <code style="background:#1e293b;padding:1px 6px;border-radius:4px;color:#0ea5e9">AQEDAT</code> and is around 200–300 characters long.
          </div>
        </div>

      </div>

      <div style="margin-top:16px;padding-top:16px;border-top:1px solid #1e3a5f;color:#64748b;font-size:12px">
        ⚠️ <strong style="color:#94a3b8">If the cookie expires</strong> (LinkedIn logged you out), just repeat these steps to get a fresh one and update it here.
        LinkedIn session cookies typically last several weeks to months.
      </div>
    </div>
  </details>

  <div class="form-grid" style="margin-top:16px">
    <div>
      <label>LinkedIn Email {dot('li_user_email')}</label>
      <input type="email" name="li_user_email" value="{creds.get('li_user_email','')}" placeholder="you@linkedin.com">
      <div class="hint">Used to pre-fill Easy Apply forms.</div>
    </div>
    <div>
      <label>LinkedIn Phone {dot('li_user_phone')}</label>
      <input type="text" name="li_user_phone" value="{creds.get('li_user_phone','')}" placeholder="+971 50 123 4567">
      <div class="hint">Used to pre-fill Easy Apply phone fields.</div>
    </div>
  </div>
</div>

<button type="submit" class="save-btn">💾 Save All Configuration</button>
</form>"""

    return _page("c", html, "Configuration")


# ── Apply flow ────────────────────────────────────────────────────────────────

_TAILOR_SYSTEM = """You are an expert resume writer specializing in DevOps, Cloud, and Automation roles.
Tailor the candidate's resume to closely match the job description.

Rules:
1. ONLY modify: Professional Summary, Skills section, Experience bullet points.
2. NEVER change: name, contact info, education, certifications, company names, job titles, dates.
3. Mirror the language and keywords from the job description naturally — no keyword stuffing.
4. Keep bullet points concise, action-verb-led, and quantified where possible.
5. Return ONLY the complete tailored resume text, preserving the same section structure.
6. Do not add new sections that don't exist in the original."""


def _get_anthropic_key() -> str:
    creds = load_config().get("credentials", {})
    return (creds.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")).strip()


def _find_job_by_id(job_id: str) -> dict | None:
    return next((j for j in load_jobs() if j.get("id") == job_id), None)


def _update_job_by_id(job_id: str, **updates):
    jobs = load_jobs()
    for j in jobs:
        if j.get("id") == job_id:
            j.update(updates)
            j["status_updated_at"] = datetime.utcnow().isoformat()
            break
    save_jobs(jobs)


@app.route("/apply/<job_id>")
def apply_page(job_id):
    from storage import ats_score, load_resume
    job = _find_job_by_id(job_id)
    if not job:
        return redirect("/search")

    resume      = load_resume()
    orig_text   = resume.get("text", "")
    resume_name = resume.get("filename", "No resume uploaded")
    tailored    = job.get("tailored_resume_text", "")
    has_key     = bool(_get_anthropic_key())

    orig_ats    = ats_score(orig_text,  job) if orig_text  else 0
    tail_ats    = ats_score(tailored,   job) if tailored   else 0

    flash = request.args.get("flash", "")
    flash_html = ""
    if flash == "tailored":
        flash_html = '<div class="flash flash-ok" style="margin-bottom:20px">✅ Resume tailored with AI. Review below before applying.</div>'
    elif flash == "nokey":
        flash_html = '<div class="flash flash-err" style="margin-bottom:20px">❌ Anthropic API key not set. Add it in Configuration → Credentials.</div>'
    elif flash == "noresume":
        flash_html = '<div class="flash flash-err" style="margin-bottom:20px">❌ No resume found. Upload your resume on the Search page first.</div>'

    # Build resume tabs
    tab_js = """<script>
function showTab(t){
  document.querySelectorAll('.rtab').forEach(e=>e.classList.remove('active-tab'));
  document.querySelectorAll('.rcontent').forEach(e=>e.style.display='none');
  document.getElementById('tab-'+t).classList.add('active-tab');
  document.getElementById('rc-'+t).style.display='block';
}
</script>"""

    tabs = ""
    if tailored:
        tabs = f"""<div style="display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid #334155">
  <button id="tab-orig" class="rtab" onclick="showTab('orig')"
    style="background:none;border:none;border-bottom:2px solid transparent;padding:8px 18px;
           color:#94a3b8;font-weight:600;cursor:pointer;font-size:13px">
    Original <span style="font-size:11px;color:#64748b">({orig_ats}% ATS)</span>
  </button>
  <button id="tab-tail" class="rtab active-tab" onclick="showTab('tail')"
    style="background:none;border:none;border-bottom:2px solid #6366f1;padding:8px 18px;
           color:#e2e8f0;font-weight:600;cursor:pointer;font-size:13px">
    ✨ AI Tailored <span style="font-size:11px;color:#22c55e">(+{max(0,tail_ats-orig_ats)}% → {tail_ats}% ATS)</span>
  </button>
</div>
<div id="rc-orig" class="rcontent" style="display:none">
  <pre style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:16px;
              font-size:12px;line-height:1.8;color:#94a3b8;overflow-y:auto;max-height:420px;
              white-space:pre-wrap;font-family:'Segoe UI',sans-serif">{orig_text[:6000] if orig_text else 'No resume uploaded yet.'}</pre>
</div>
<div id="rc-tail" class="rcontent">
  <pre style="background:#0f172a;border:1px solid #6366f144;border-radius:8px;padding:16px;
              font-size:12px;line-height:1.8;color:#c4b5fd;overflow-y:auto;max-height:420px;
              white-space:pre-wrap;font-family:'Segoe UI',sans-serif">{tailored[:6000]}</pre>
</div>"""
    else:
        tabs = f"""<pre style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:16px;
             font-size:12px;line-height:1.8;color:#94a3b8;overflow-y:auto;max-height:420px;
             white-space:pre-wrap;font-family:'Segoe UI',sans-serif">{orig_text[:6000] if orig_text else 'No resume uploaded. Go to Search page to upload your resume.'}</pre>"""

    # ATS comparison bar
    ats_display = ""
    if orig_text:
        if tailored:
            ats_display = f"""<div style="display:flex;gap:24px;margin-bottom:16px;flex-wrap:wrap">
  <div><div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:4px">Original ATS</div>
    {_ats_pill(orig_ats)}{_ats_bar(orig_ats)}</div>
  <div style="display:flex;align-items:center;font-size:18px;color:#334155">→</div>
  <div><div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:4px">Tailored ATS</div>
    {_ats_pill(tail_ats)}{_ats_bar(tail_ats)}</div>
  <div style="display:flex;align-items:center;font-size:20px">
    {'🚀' if tail_ats > orig_ats else '↔️'}
  </div>
</div>"""
        else:
            ats_display = f"""<div style="margin-bottom:12px">
  <div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;margin-bottom:4px">Current ATS Match</div>
  {_ats_pill(orig_ats)}{_ats_bar(orig_ats)}
</div>"""

    # Tailor button or no-key warning
    tailor_section = ""
    if not has_key:
        tailor_section = """<div style="background:#f59e0b11;border:1px solid #f59e0b33;border-radius:8px;
             padding:12px 16px;font-size:13px;color:#f59e0b;margin-bottom:16px">
  ⚠️ Set your <strong>Anthropic API Key</strong> in Configuration → Credentials to enable AI tailoring.
</div>"""
    else:
        tailor_section = f"""<form method="POST" action="/apply/{job_id}/tailor" id="tailor-form">
  <button type="submit" class="btn btn-purple" style="width:100%;justify-content:center;padding:11px"
          onclick="this.disabled=true;this.innerHTML='🤖 Tailoring… (10–20s)';this.form.submit()">
    🤖 {'Re-tailor' if tailored else 'Tailor'} Resume with AI
  </button>
</form>"""

    # Confirm button
    confirm_section = f"""<form method="POST" action="/apply/{job_id}/confirm" style="margin-top:12px">
  <input type="hidden" name="use_tailored" value="{'1' if tailored else '0'}">
  <button type="submit" class="btn btn-green" style="width:100%;justify-content:center;padding:13px;font-size:14px"
          onclick="this.disabled=true;this.innerHTML='⏳ Queued…'">
    ✅ Confirm &amp; Apply {'with Tailored Resume' if tailored else '(original resume)'}
  </button>
</form>
<p style="text-align:center;font-size:12px;color:#475569;margin-top:8px">
  The local orchestrator will apply via LinkedIn Easy Apply within the next scheduled run.
</p>"""

    jsc = job.get("relevance_score", 0)
    desc = (job.get("description") or "")[:2000].replace("<","&lt;")

    html = f"""
{flash_html}
<div style="margin-bottom:20px">
  <a href="/search" style="color:#64748b;font-size:13px;text-decoration:none">← Back to Search</a>
</div>

<div style="margin-bottom:24px">
  <h2 style="margin-bottom:6px">{job.get('title','')}</h2>
  <div style="color:#0ea5e9;font-size:15px;font-weight:600;margin-bottom:12px">{job.get('company','')}</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:13px;color:#94a3b8;align-items:center">
    <span>📍 {job.get('location','')}</span>
    <span>🗓️ {job.get('date_posted','N/A')}</span>
    <span class="score-pill {'pill-green' if jsc>=70 else 'pill-yellow' if jsc>=40 else 'pill-red'}">⭐ {jsc}% job match</span>
    {_badge(job.get('status',''))}
    {'<a href="'+job.get('apply_url','')+ '" target="_blank" class="btn btn-gray btn-sm">View on LinkedIn ↗</a>' if job.get('apply_url') else ''}
  </div>
</div>

<div class="two-col" style="align-items:flex-start;gap:20px">

  <!-- Left: Job description -->
  <div class="card" style="margin-bottom:0">
    <h3>📋 Job Description</h3>
    <pre style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:16px;
               font-size:12px;line-height:1.8;color:#94a3b8;overflow-y:auto;max-height:480px;
               white-space:pre-wrap;font-family:'Segoe UI',sans-serif">{desc}</pre>
  </div>

  <!-- Right: Resume + actions -->
  <div>
    <div class="card" style="margin-bottom:16px">
      <h3>📄 Your Resume
        <span style="font-size:12px;color:#64748b;font-weight:500;margin-left:8px">{resume_name}</span>
      </h3>
      {ats_display}
      {tabs}
    </div>

    <div class="card" style="margin-bottom:0">
      <h3>⚡ Actions</h3>
      {tailor_section}
      {confirm_section}
    </div>
  </div>
</div>
{tab_js}"""

    return _page("s", html, f"Apply — {job.get('title','')}")


@app.route("/apply/<job_id>/tailor", methods=["POST"])
def tailor_for_job(job_id):
    from storage import load_resume, ats_score
    job = _find_job_by_id(job_id)
    if not job:
        return redirect("/search")

    api_key = _get_anthropic_key()
    if not api_key:
        return redirect(f"/apply/{job_id}?flash=nokey")

    resume = load_resume()
    resume_text = resume.get("text", "")
    if not resume_text:
        return redirect(f"/apply/{job_id}?flash=noresume")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=_TAILOR_SYSTEM,
            messages=[{"role": "user", "content":
                f"## Job Title: {job.get('title','')}\n"
                f"## Company: {job.get('company','')}\n"
                f"## Location: {job.get('location','')}\n\n"
                f"## Job Description:\n{(job.get('description') or '')[:4000]}\n\n"
                f"## Current Resume:\n{resume_text}"}],
        )
        tailored_text = msg.content[0].text
        _update_job_by_id(job_id, tailored_resume_text=tailored_text)
    except Exception as e:
        logger.error(f"AI tailoring failed: {e}")

    return redirect(f"/apply/{job_id}?flash=tailored")


@app.route("/apply/<job_id>/confirm", methods=["POST"])
def confirm_apply(job_id):
    job = _find_job_by_id(job_id)
    if not job:
        return redirect("/search")

    use_tailored = request.form.get("use_tailored") == "1"
    updates = {
        "status":           "approved_stage2",
        "apply_source":     "web_ui",
        "use_tailored":     use_tailored,
    }
    if not use_tailored:
        updates["tailored_resume_text"] = ""

    _update_job_by_id(job_id, **updates)
    return redirect("/search?applied=1")


# ── Approval email routes ─────────────────────────────────────────────────────

CARD = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Job Agent</title>
<style>body{{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.c{{background:#1e293b;border-radius:16px;padding:48px;max-width:480px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
.i{{font-size:64px;margin-bottom:16px}}h1{{margin:0 0 8px;font-size:24px}}p{{color:#94a3b8;line-height:1.6}}
.co{{color:#0ea5e9;font-weight:600}}.back{{margin-top:24px;display:inline-block;color:#0ea5e9;font-size:14px}}</style>
</head><body><div class="c"><div class="i">{icon}</div><h1>{title}</h1><p>{msg}</p>
{job_line}<a href="/" class="back">← Dashboard</a></div></body></html>"""

def _card(icon, title, msg, job=None, code=200):
    jl = f'<p><span class="co">{job["title"]} @ {job["company"]}</span></p>' if job else ""
    return CARD.format(icon=icon, title=title, msg=msg, job_line=jl), code


@app.route("/approve1/<aid>")
def approve1(aid):
    job = _find("approval_id", aid)
    if not job: return _card("❌","Not Found","This link is invalid or already used.", code=404)
    if job.get("status") != "pending_stage1": return _card("ℹ️","Already Decided",f"Status: {job.get('status')}", job=job)
    _update("approval_id", aid, "approved_stage1")
    return _card("✅","Approved!","Your agent will tailor your resume and send it for final review.", job=job)


@app.route("/skip/<aid>")
def skip(aid):
    job = _find("approval_id", aid)
    if not job: return _card("❌","Not Found","This link is invalid or already used.", code=404)
    _update("approval_id", aid, "skipped")
    return _card("⏭️","Skipped","This job has been removed from your queue.", job=job)


@app.route("/approve2/<aid2>")
def approve2(aid2):
    job = _find("approval2_id", aid2)
    if not job: return _card("❌","Not Found","This link is invalid or already used.", code=404)
    if job.get("status") != "pending_stage2": return _card("ℹ️","Already Decided",f"Status: {job.get('status')}", job=job)
    _update("approval2_id", aid2, "approved_stage2")
    return _card("🚀","Final Approval Received!","Your agent will apply within the next 10 minutes.", job=job)


@app.route("/decline2/<aid2>")
def decline2(aid2):
    job = _find("approval2_id", aid2)
    if not job: return _card("❌","Not Found","This link is invalid or already used.", code=404)
    _update("approval2_id", aid2, "declined_stage2")
    return _card("❌","Declined","This job has been removed from your queue.", job=job)


# ── Utility ───────────────────────────────────────────────────────────────────

@app.route("/status")
def status():
    jobs = load_jobs()
    counts = {}
    for j in jobs:
        k = j.get("status", "unknown")
        counts[k] = counts.get(k, 0) + 1
    return jsonify({"total": len(jobs), "by_status": counts, "agent_status": load_status()})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "storage": "neon" if use_db() else "local"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🌐 Running at http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
