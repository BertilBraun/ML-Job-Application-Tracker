"""Generate results.html from results.json. Run: python build_ui.py"""
import json
import sys
from pathlib import Path

RESULTS_PATH = Path("results.json")
OUTPUT_PATH = Path("results.html")


def score_class(score: float) -> str:
    if score >= 7:
        return "good"
    if score >= 5:
        return "mid"
    return "bad"


def rec_class(rec: str) -> str:
    r = rec.lower()
    if "strong" in r:
        return "rec-strong"
    if r == "apply":
        return "rec-apply"
    if r == "consider":
        return "rec-consider"
    return "rec-skip"


def escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_tags(items: list[str], cls: str = "tag") -> str:
    return "".join(f'<span class="{cls}">{escape(t)}</span>' for t in items)


def render_card(entry: dict, rank: int) -> str:
    job = entry["job"]
    a = entry["analysis"]
    sc = score_class(a["overall_score"])
    rc = rec_class(a["recommendation"])

    meta = []
    if job.get("location"):
        meta.append(f'<span class="meta-item">📍 {escape(job["location"])}</span>')
    if job.get("salary"):
        meta.append(f'<span class="meta-item">💰 {escape(job["salary"])}</span>')
    if job.get("company_size"):
        meta.append(f'<span class="meta-item">👥 {escape(job["company_size"])}</span>')
    if job.get("date_added"):
        meta.append(f'<span class="meta-item">🕒 {escape(job["date_added"])}</span>')

    _industry_noise = {"AI", "Artificial Intelligence", "Machine Learning", "Machine Learning Engineer", "Deep Learning"}
    industries = [t for t in job.get("industries", []) if not any(n in t for n in _industry_noise)]
    industry_html = render_tags(industries, "tag tag-industry")

    raw_sen = [s.lower() for s in job.get("seniority", [])]
    has_junior = any("junior" in s for s in raw_sen)
    has_mid    = any("mid" in s for s in raw_sen)
    has_senior = any("senior" in s for s in raw_sen)
    sen_tags: list[str] = []
    if has_junior and has_mid:
        sen_tags.append("🟢 Junior / Mid")
    elif has_junior:
        sen_tags.append("🟢 Junior")
    if has_mid and has_senior:
        sen_tags.append("🟡 Mid / Senior")
    elif has_mid and not has_junior:
        sen_tags.append("🟢 Mid")
    if has_senior and not has_mid:
        sen_tags.append("🟡 Senior")
    seniority_html = render_tags(sen_tags, "tag tag-seniority")

    strengths_html = "".join(
        f'<li class="strength">✓ {escape(s)}</li>'
        for s in a["candidate_fit"].get("strengths", [])
    )
    gaps_html = "".join(
        f'<li class="gap">✗ {escape(g)}</li>'
        for g in a["candidate_fit"].get("gaps", [])
    )
    concerns_html = "".join(
        f'<li class="concern">⚠ {escape(c)}</li>'
        for c in a.get("key_concerns", [])
    )

    team_s = a['team_assessment']['score']
    work_s = a['work_impact']['score']
    loc_s  = a['location_fit']['score']
    cand_s = a['candidate_fit']['score']
    loc_works = str(a['location_fit']['works']).lower()

    job_url     = escape(job.get('url', ''))
    listing_url = escape(job.get('url', ''))
    apply_url   = escape(job.get('apply_url') or job.get('url', ''))

    return f"""
<div class="card {sc}"
     data-score="{a['overall_score']}"
     data-rec="{escape(a['recommendation'])}"
     data-team="{team_s}"
     data-work="{work_s}"
     data-location="{loc_s}"
     data-candidate="{cand_s}"
     data-loc-works="{loc_works}">
  <div class="card-header" onclick="toggleCard(this)">
    <div class="rank">#{rank}</div>
    <div class="score-badge {sc}">{a['overall_score']:.1f}</div>
    <div class="card-title-block">
      <div class="job-title">{escape(job['title'])}</div>
      <div class="company">{escape(job['company'])}</div>
    </div>
    <div class="rec-badge {rc}">{escape(a['recommendation'].upper())}</div>
    <div class="header-actions" onclick="event.stopPropagation()">
      <a href="{listing_url}" target="_blank" class="hdr-btn hdr-view">View</a>
      <button class="hdr-btn hdr-apply"
              data-job-url="{job_url}"
              data-job-title="{escape(job['title'])}"
              data-job-company="{escape(job['company'])}"
              data-listing-url="{listing_url}"
              data-apply-url="{apply_url}"
              data-job-location="{escape(job.get('location', ''))}"
              data-job-salary="{escape(job.get('salary') or '')}"
              onclick="startApplication(this)">Track</button>
    </div>
    <div class="toggle-btn">▼</div>
  </div>

  <div class="meta-row">{''.join(meta)}</div>

  <div class="tags-row">{seniority_html}{industry_html}</div>

  <div class="card-body" style="display:none">
    <div class="section">
      <div class="section-label">What it is</div>
      <p>{escape(a['job_summary'])}</p>
    </div>

    <div class="two-col">
      <div class="section">
        <div class="section-label">Team <span class="sub-score {score_class(a['team_assessment']['score'])}">{a['team_assessment']['score']:.1f}</span></div>
        <p>{escape(a['team_assessment']['reasoning'])}</p>
      </div>
      <div class="section">
        <div class="section-label">Work impact <span class="sub-score {score_class(a['work_impact']['score'])}">{a['work_impact']['score']:.1f}</span></div>
        <p>{escape(a['work_impact']['reasoning'])}</p>
      </div>
    </div>

    <div class="two-col">
      <div class="section">
        <div class="section-label">Location {'<span class="loc-ok">✓ works</span>' if a['location_fit']['works'] else '<span class="loc-no">✗ problem</span>'} <span class="sub-score {score_class(a['location_fit']['score'])}">{a['location_fit']['score']:.1f}</span></div>
        <p>{escape(a['location_fit']['reasoning'])}</p>
      </div>
      <div class="section">
        <div class="section-label">Candidate fit <span class="sub-score {score_class(a['candidate_fit']['score'])}">{a['candidate_fit']['score']:.1f}</span></div>
        <p>{escape(a['candidate_fit']['reasoning'])}</p>
      </div>
    </div>

    <div class="two-col">
      <div class="section">
        <div class="section-label">Strengths</div>
        <ul class="fit-list">{strengths_html or '<li class="muted">None noted</li>'}</ul>
      </div>
      <div class="section">
        <div class="section-label">Gaps</div>
        <ul class="fit-list">{gaps_html or '<li class="muted">None noted</li>'}</ul>
      </div>
    </div>

    {'<div class="section"><div class="section-label">Salary</div><p class="salary-note">' + escape(a['salary_note']) + '</p></div>' if a.get('salary_note') else ''}

    {'<div class="section"><div class="section-label">Concerns</div><ul class="fit-list">' + concerns_html + '</ul></div>' if concerns_html else ''}
  </div>
</div>"""


def build(data: list[dict]) -> str:
    total   = len(data)
    strong  = sum(1 for d in data if "strong" in d["analysis"]["recommendation"].lower())
    apply_  = sum(1 for d in data if d["analysis"]["recommendation"].lower() == "apply")
    consider= sum(1 for d in data if d["analysis"]["recommendation"].lower() == "consider")
    skip    = sum(1 for d in data if d["analysis"]["recommendation"].lower() == "skip")
    avg     = sum(d["analysis"]["overall_score"] for d in data) / total if total else 0

    cards_html = "\n".join(render_card(entry, i + 1) for i, entry in enumerate(data))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Results</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 24px 16px 60px;
  }}

  h1 {{ font-size: 1.5rem; font-weight: 700; color: #f8fafc; }}
  h1 span {{ color: #64748b; font-weight: 400; font-size: 1rem; margin-left: 8px; }}

  .stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 28px; }}
  .stat {{ background: #1e2333; border-radius: 10px; padding: 10px 18px; font-size: 0.85rem; color: #94a3b8; }}
  .stat strong {{ color: #f1f5f9; font-size: 1.1rem; display: block; }}

  .controls {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }}
  .controls select, .controls button {{
    background: #1e2333; border: 1px solid #2d3748; color: #e2e8f0;
    border-radius: 8px; padding: 7px 14px; font-size: 0.875rem; cursor: pointer;
  }}
  .controls select:focus, .controls button:focus {{ outline: 2px solid #3b82f6; }}
  .controls button:hover {{ background: #2d3748; }}
  .controls label {{ color: #94a3b8; font-size: 0.875rem; }}

  .tracker-link {{
    margin-left: auto; font-size: 0.85rem; font-weight: 600;
    color: #60a5fa; text-decoration: none; padding: 7px 14px;
    background: #1e3a5f; border-radius: 8px;
  }}
  .tracker-link:hover {{ background: #1e4a7f; }}

  .weight-controls {{
    background: #1e2333; border-radius: 10px; padding: 12px 16px;
    margin-bottom: 20px; display: flex; flex-direction: column; gap: 8px;
  }}
  .weight-label {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #475569; margin-bottom: 2px; }}
  .weight-row {{ display: flex; align-items: center; gap: 10px; }}
  .weight-name {{ font-size: 0.8rem; color: #94a3b8; min-width: 100px; }}
  .weight-row input[type=range] {{ flex: 1; accent-color: #3b82f6; }}
  .weight-pct {{ font-size: 0.8rem; font-weight: 600; color: #60a5fa; min-width: 36px; text-align: right; }}

  .cards {{ display: flex; flex-direction: column; gap: 12px; max-width: 900px; margin: 0 auto; }}

  .card {{
    background: #1a1f2e; border-radius: 14px;
    border-left: 4px solid transparent; overflow: hidden; transition: box-shadow 0.15s;
  }}
  .card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.4); }}
  .card.good {{ border-left-color: #22c55e; }}
  .card.mid  {{ border-left-color: #f59e0b; }}
  .card.bad  {{ border-left-color: #ef4444; }}

  .card-header {{
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; cursor: pointer; user-select: none;
  }}
  .rank {{ color: #475569; font-size: 0.8rem; font-weight: 600; min-width: 28px; }}

  .score-badge {{
    font-size: 1.1rem; font-weight: 700; min-width: 42px; text-align: center;
    padding: 4px 8px; border-radius: 8px;
  }}
  .score-badge.good {{ background: #14532d; color: #4ade80; }}
  .score-badge.mid  {{ background: #451a03; color: #fbbf24; }}
  .score-badge.bad  {{ background: #450a0a; color: #f87171; }}

  .card-title-block {{ flex: 1; min-width: 0; }}
  .job-title {{ font-weight: 600; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .company {{ color: #64748b; font-size: 0.82rem; margin-top: 2px; }}

  .rec-badge {{ font-size: 0.7rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; white-space: nowrap; letter-spacing: 0.04em; }}
  .rec-strong  {{ background: #14532d; color: #4ade80; }}
  .rec-apply   {{ background: #1e3a5f; color: #60a5fa; }}
  .rec-consider{{ background: #451a03; color: #fbbf24; }}
  .rec-skip    {{ background: #1c1c1c; color: #6b7280; }}

  .header-actions {{ display: flex; gap: 5px; }}
  .hdr-btn {{
    font-size: 0.72rem; font-weight: 600; padding: 3px 9px; border-radius: 6px;
    border: 1px solid #2d3748; cursor: pointer; white-space: nowrap; text-decoration: none;
    display: inline-flex; align-items: center;
  }}
  .hdr-view {{ background: #1e2333; color: #94a3b8; }}
  .hdr-view:hover {{ background: #2d3748; color: #e2e8f0; }}
  .hdr-apply {{ background: #1e3a5f; color: #60a5fa; }}
  .hdr-apply:hover {{ background: #1e4a7f; }}
  .hdr-tracked {{ background: #14532d !important; color: #4ade80 !important; border-color: #166534 !important; cursor: default; }}

  .toggle-btn {{ color: #475569; font-size: 0.85rem; padding: 4px; transition: transform 0.2s; flex-shrink: 0; }}
  .toggle-btn.open {{ transform: rotate(180deg); }}

  .meta-row {{ display: flex; flex-wrap: wrap; gap: 8px; padding: 0 16px 10px; font-size: 0.8rem; color: #94a3b8; }}
  .meta-item {{ display: flex; align-items: center; gap: 4px; }}

  .tags-row {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 12px; }}
  .tag {{ font-size: 0.72rem; padding: 2px 8px; border-radius: 20px; font-weight: 500; white-space: nowrap; }}
  .tag-tech     {{ background: #1e293b; color: #7dd3fc; border: 1px solid #1e3a5f; }}
  .tag-industry {{ background: #1e1b33; color: #a78bfa; border: 1px solid #2e1b4e; }}
  .tag-seniority{{ background: #1a2e1a; color: #86efac; border: 1px solid #14532d; }}

  .card-body {{ padding: 0 16px 16px; border-top: 1px solid #2d3748; padding-top: 14px; }}
  .section {{ margin-bottom: 14px; }}
  .section p {{ color: #94a3b8; font-size: 0.875rem; line-height: 1.6; margin-top: 4px; }}
  .section-label {{
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: #475569; margin-bottom: 4px;
    display: flex; align-items: center; gap: 8px;
  }}
  .sub-score {{ font-size: 0.85rem; font-weight: 700; padding: 1px 6px; border-radius: 5px; text-transform: none; letter-spacing: 0; }}
  .sub-score.good {{ background: #14532d; color: #4ade80; }}
  .sub-score.mid  {{ background: #451a03; color: #fbbf24; }}
  .sub-score.bad  {{ background: #450a0a; color: #f87171; }}

  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 600px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

  .fit-list {{ list-style: none; font-size: 0.85rem; line-height: 1.7; margin-top: 4px; }}
  .strength {{ color: #4ade80; }}
  .gap      {{ color: #fbbf24; }}
  .concern  {{ color: #f87171; }}
  .muted    {{ color: #475569; }}

  .loc-ok {{ color: #4ade80; font-weight: 600; font-size: 0.78rem; }}
  .loc-no {{ color: #f87171; font-weight: 600; font-size: 0.78rem; }}
  .salary-note {{ color: #94a3b8; font-size: 0.875rem; line-height: 1.6; margin-top: 4px; }}
  .hidden {{ display: none !important; }}

  /* ── Modal ──────────────────────────────── */
  .modal-overlay {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center; z-index: 100; padding: 16px;
  }}
  .modal {{
    background: #1a1f2e; border-radius: 16px; width: 100%; max-width: 560px;
    max-height: 90vh; overflow-y: auto; padding: 24px;
    border: 1px solid #2d3748; box-shadow: 0 20px 60px rgba(0,0,0,0.6);
  }}
  .modal-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }}
  .modal-job-title {{ font-size: 1rem; font-weight: 700; color: #f1f5f9; }}
  .modal-company {{ font-size: 0.85rem; color: #64748b; margin-top: 3px; }}
  .modal-close {{
    background: none; border: none; color: #475569; font-size: 1.2rem;
    cursor: pointer; padding: 0 4px; flex-shrink: 0;
  }}
  .modal-close:hover {{ color: #e2e8f0; }}
  .modal-status {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 12px; min-height: 20px; }}
  .modal-label {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #475569; margin-bottom: 5px; }}
  .modal-textarea {{
    width: 100%; background: #0f1117; color: #e2e8f0; border: 1px solid #2d3748;
    border-radius: 8px; padding: 10px; font-size: 0.85rem; line-height: 1.6;
    font-family: inherit; resize: vertical; min-height: 90px; cursor: pointer; margin-bottom: 12px;
  }}
  .modal-textarea:focus {{ outline: 2px solid #3b82f6; }}
  .modal-actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; padding-top: 14px; border-top: 1px solid #2d3748; }}
  .modal-btn {{
    padding: 7px 16px; border-radius: 8px; font-size: 0.85rem; font-weight: 600;
    cursor: pointer; border: none; text-decoration: none; display: inline-flex; align-items: center;
  }}
  .modal-btn.primary {{ background: #2563eb; color: #fff; }}
  .modal-btn.primary:hover {{ background: #1d4ed8; }}
  .modal-btn.primary:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .modal-btn.secondary {{ background: #1e2333; color: #94a3b8; border: 1px solid #2d3748; }}
  .modal-btn.secondary:hover {{ background: #2d3748; color: #e2e8f0; }}
</style>
</head>
<body>

<div style="max-width:900px;margin:0 auto">
  <h1>Job Results <span>{total} listings</span></h1>

  <div class="stats">
    <div class="stat"><strong style="color:#4ade80">{strong}</strong> Strong Apply</div>
    <div class="stat"><strong style="color:#60a5fa">{apply_}</strong> Apply</div>
    <div class="stat"><strong style="color:#fbbf24">{consider}</strong> Consider</div>
    <div class="stat"><strong style="color:#6b7280">{skip}</strong> Skip</div>
    <div class="stat"><strong>{avg:.1f}/10</strong> Avg Score</div>
  </div>

  <div class="controls">
    <label>Filter:</label>
    <select id="filter-rec" onchange="applyFilters()">
      <option value="">All recommendations</option>
      <option value="strong apply">Strong Apply</option>
      <option value="apply">Apply</option>
      <option value="consider">Consider</option>
      <option value="skip">Skip</option>
    </select>
    <button onclick="expandAll()">Expand all</button>
    <button onclick="collapseAll()">Collapse all</button>
    <a href="/applications" class="tracker-link">Applications tracker →</a>
  </div>

  <div class="weight-controls">
    <div class="weight-label">Score weights</div>
    <div class="weight-row">
      <span class="weight-name">Team</span>
      <input type="range" id="w-team" min="0" max="100" value="40" oninput="reweight()">
      <span class="weight-pct" id="pct-team">40%</span>
    </div>
    <div class="weight-row">
      <span class="weight-name">Work impact</span>
      <input type="range" id="w-work" min="0" max="100" value="25" oninput="reweight()">
      <span class="weight-pct" id="pct-work">25%</span>
    </div>
    <div class="weight-row">
      <span class="weight-name">Location</span>
      <input type="range" id="w-location" min="0" max="100" value="20" oninput="reweight()">
      <span class="weight-pct" id="pct-location">20%</span>
    </div>
    <div class="weight-row">
      <span class="weight-name">Candidate fit</span>
      <input type="range" id="w-candidate" min="0" max="100" value="15" oninput="reweight()">
      <span class="weight-pct" id="pct-candidate">15%</span>
    </div>
  </div>

  <div class="cards" id="cards">
{cards_html}
  </div>
</div>

<!-- Apply modal -->
<div id="apply-modal" class="modal-overlay" style="display:none" onclick="closeModal()">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-header">
      <div>
        <div class="modal-job-title" id="m-title"></div>
        <div class="modal-company" id="m-company"></div>
      </div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-status" id="m-status"></div>
    <div id="m-materials" style="display:none">
      <div class="modal-label">Tailored About</div>
      <textarea class="modal-textarea" id="m-about" readonly onclick="this.select()"></textarea>
      <div class="modal-label">Cover letter opener</div>
      <textarea class="modal-textarea" id="m-cover" readonly onclick="this.select()"></textarea>
    </div>
    <div class="modal-actions">
      <button id="m-gen-btn" class="modal-btn primary" onclick="generateInModal()">Generate materials</button>
      <a href="/applications" class="modal-btn secondary">Tracker →</a>
      <button class="modal-btn secondary" onclick="closeModal()">Done</button>
    </div>
  </div>
</div>

<script>
let _currentAppId = null;
let _currentJobUrl = null;

// ── Card controls ──────────────────────────────────────────────────────────────

function toggleCard(header) {{
  const card = header.closest('.card');
  const body = card.querySelector('.card-body');
  const btn  = card.querySelector('.toggle-btn');
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  btn.classList.toggle('open', !open);
}}

function expandAll() {{
  document.querySelectorAll('.card:not(.hidden) .card-body').forEach(b => b.style.display = 'block');
  document.querySelectorAll('.card:not(.hidden) .toggle-btn').forEach(b => b.classList.add('open'));
}}

function collapseAll() {{
  document.querySelectorAll('.card-body').forEach(b => b.style.display = 'none');
  document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('open'));
}}

function applyFilters() {{
  const rec = document.getElementById('filter-rec').value.toLowerCase();
  document.querySelectorAll('.card').forEach(card => {{
    card.classList.toggle('hidden', rec && card.dataset.rec.toLowerCase() !== rec);
  }});
}}

function scoreClass(s) {{ return s >= 7 ? 'good' : s >= 5 ? 'mid' : 'bad'; }}

function reweight() {{
  const wTeam = +document.getElementById('w-team').value;
  const wWork = +document.getElementById('w-work').value;
  const wLoc  = +document.getElementById('w-location').value;
  const wCand = +document.getElementById('w-candidate').value;
  const total = wTeam + wWork + wLoc + wCand || 1;

  document.getElementById('pct-team').textContent      = Math.round(wTeam / total * 100) + '%';
  document.getElementById('pct-work').textContent      = Math.round(wWork / total * 100) + '%';
  document.getElementById('pct-location').textContent  = Math.round(wLoc  / total * 100) + '%';
  document.getElementById('pct-candidate').textContent = Math.round(wCand / total * 100) + '%';

  document.querySelectorAll('.card').forEach(card => {{
    const score0 = (wTeam * +card.dataset.team + wWork * +card.dataset.work +
                    wLoc  * +card.dataset.location + wCand * +card.dataset.candidate) / total;
    const score  = card.dataset.locWorks === 'true' ? score0 : -Math.abs(score0);
    const s      = Math.round(score * 10) / 10;
    card.dataset.score = s;
    const cls = scoreClass(s);
    const badge = card.querySelector('.score-badge');
    badge.textContent = s.toFixed(1);
    badge.className = 'score-badge ' + cls;
    card.className = card.className.replace(/\b(good|mid|bad)\b/g, cls);
  }});

  const container = document.getElementById('cards');
  Array.from(container.querySelectorAll('.card'))
    .sort((a, b) => +b.dataset.score - +a.dataset.score)
    .forEach((c, i) => {{ c.querySelector('.rank').textContent = '#' + (i + 1); container.appendChild(c); }});
}}

// ── Application tracking ───────────────────────────────────────────────────────

function _markTracked(jobUrl) {{
  document.querySelectorAll('.hdr-apply').forEach(btn => {{
    if (btn.dataset.jobUrl === jobUrl) {{
      btn.textContent = 'Tracked ✓';
      btn.classList.add('hdr-tracked');
      btn.onclick = () => window.location.href = '/applications';
    }}
  }});
}}

async function startApplication(btn) {{
  const d = btn.dataset;
  _currentJobUrl = d.jobUrl;

  document.getElementById('m-title').textContent   = d.jobTitle;
  document.getElementById('m-company').textContent = d.jobCompany;
  document.getElementById('m-status').textContent  = '';
  document.getElementById('m-materials').style.display = 'none';
  document.getElementById('m-gen-btn').disabled    = false;
  document.getElementById('m-gen-btn').textContent = 'Generate materials';

  document.getElementById('apply-modal').style.display = 'flex';

  const res  = await fetch('/api/applications', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      job_url:      d.jobUrl,
      job_title:    d.jobTitle,
      company:      d.jobCompany,
      listing_url:  d.listingUrl,
      apply_url:    d.applyUrl,
      location:     d.jobLocation,
      salary:       d.jobSalary,
    }}),
  }});
  const data = await res.json();
  _currentAppId = data.id;

  if (data.existing) {{
    document.getElementById('m-status').textContent = 'Already in tracker.';
    document.getElementById('m-gen-btn').textContent = 'Regenerate materials';
  }}
  _markTracked(_currentJobUrl);
}}

async function generateInModal() {{
  const btn = document.getElementById('m-gen-btn');
  btn.disabled = true;
  btn.textContent = 'Generating…';
  document.getElementById('m-status').textContent = 'Calling Gemini…';

  try {{
    const res  = await fetch(`/api/applications/${{_currentAppId}}/generate`, {{method: 'POST'}});
    const data = await res.json();
    if (!res.ok) {{
      document.getElementById('m-status').textContent = data.error || 'Generation failed.';
      btn.disabled = false;
      btn.textContent = 'Retry';
      return;
    }}
    document.getElementById('m-about').value = data.about;
    document.getElementById('m-cover').value = data.cover_letter;
    document.getElementById('m-materials').style.display = 'block';
    document.getElementById('m-status').textContent = 'Done — click a field to select all.';
    btn.textContent = 'Regenerate';
    btn.disabled = false;
  }} catch(e) {{
    document.getElementById('m-status').textContent = 'Error: ' + e.message;
    btn.disabled = false;
    btn.textContent = 'Retry';
  }}
}}

function closeModal() {{
  document.getElementById('apply-modal').style.display = 'none';
}}

// On load: mark already-tracked jobs
fetch('/api/applications')
  .then(r => r.json())
  .then(apps => apps.forEach(a => _markTracked(a.job_url)))
  .catch(() => {{}}); // server not running — graceful no-op
</script>
</body>
</html>"""


def main() -> None:
    if not RESULTS_PATH.exists():
        print("results.json not found — run main.py first.")
        sys.exit(1)

    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    html = build(data)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Written {OUTPUT_PATH} ({len(data)} jobs)")


if __name__ == "__main__":
    main()
