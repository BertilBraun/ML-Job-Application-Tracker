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

    # Drop tech tags (teal) — not shown per UX decision
    # Drop industry tags that are just "AI" noise
    _industry_noise = {"AI", "Artificial Intelligence", "Machine Learning", "Machine Learning Engineer", "Deep Learning"}
    industries = [t for t in job.get("industries", []) if not any(n in t for n in _industry_noise)]
    industry_html = render_tags(industries, "tag tag-industry")
    # Consolidate seniority: junior+mid → "Junior / Mid", mid+senior → "Mid / Senior"
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

    apply_btn = ""
    url = job.get("apply_url") or job.get("url", "")
    if url:
        apply_btn = f'<a href="{escape(url)}" target="_blank" class="apply-btn">Apply →</a>'

    detail_url = job.get("url", "")
    detail_link = f'<a href="{escape(detail_url)}" target="_blank" class="detail-link">View listing</a>' if detail_url else ""

    return f"""
<div class="card {sc}" data-score="{a['overall_score']}" data-rec="{escape(a['recommendation'])}">
  <div class="card-header" onclick="toggleCard(this)">
    <div class="rank">#{rank}</div>
    <div class="score-badge {sc}">{a['overall_score']:.1f}</div>
    <div class="card-title-block">
      <div class="job-title">{escape(job['title'])}</div>
      <div class="company">{escape(job['company'])}</div>
    </div>
    <div class="rec-badge {rc}">{escape(a['recommendation'].upper())}</div>
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
        <div class="section-label">Location {'<span class="loc-ok">✓ works</span>' if a['location_fit']['works'] else '<span class="loc-no">✗ problem</span>'}</div>
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

    <div class="card-actions">{detail_link}{apply_btn}</div>
  </div>
</div>"""


def build(data: list[dict]) -> str:
    total = len(data)
    strong = sum(1 for d in data if "strong" in d["analysis"]["recommendation"].lower())
    apply_ = sum(1 for d in data if d["analysis"]["recommendation"].lower() == "apply")
    consider = sum(1 for d in data if d["analysis"]["recommendation"].lower() == "consider")
    skip = sum(1 for d in data if d["analysis"]["recommendation"].lower() == "skip")
    avg = sum(d["analysis"]["overall_score"] for d in data) / total if total else 0

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
    background: #0f1117;
    color: #e2e8f0;
    min-height: 100vh;
    padding: 24px 16px 60px;
  }}

  h1 {{ font-size: 1.5rem; font-weight: 700; color: #f8fafc; }}
  h1 span {{ color: #64748b; font-weight: 400; font-size: 1rem; margin-left: 8px; }}

  .stats {{
    display: flex; flex-wrap: wrap; gap: 12px;
    margin: 20px 0 28px;
  }}
  .stat {{
    background: #1e2333; border-radius: 10px; padding: 10px 18px;
    font-size: 0.85rem; color: #94a3b8;
  }}
  .stat strong {{ color: #f1f5f9; font-size: 1.1rem; display: block; }}

  .controls {{
    display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; align-items: center;
  }}
  .controls select, .controls button {{
    background: #1e2333; border: 1px solid #2d3748; color: #e2e8f0;
    border-radius: 8px; padding: 7px 14px; font-size: 0.875rem; cursor: pointer;
  }}
  .controls select:focus, .controls button:focus {{ outline: 2px solid #3b82f6; }}
  .controls button:hover {{ background: #2d3748; }}
  .controls label {{ color: #94a3b8; font-size: 0.875rem; }}

  .cards {{ display: flex; flex-direction: column; gap: 12px; max-width: 900px; margin: 0 auto; }}

  .card {{
    background: #1a1f2e; border-radius: 14px;
    border-left: 4px solid transparent; overflow: hidden;
    transition: box-shadow 0.15s;
  }}
  .card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.4); }}
  .card.good {{ border-left-color: #22c55e; }}
  .card.mid  {{ border-left-color: #f59e0b; }}
  .card.bad  {{ border-left-color: #ef4444; }}

  .card-header {{
    display: flex; align-items: center; gap: 12px;
    padding: 14px 16px; cursor: pointer; user-select: none;
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

  .rec-badge {{
    font-size: 0.7rem; font-weight: 700; padding: 3px 8px;
    border-radius: 6px; white-space: nowrap; letter-spacing: 0.04em;
  }}
  .rec-strong  {{ background: #14532d; color: #4ade80; }}
  .rec-apply   {{ background: #1e3a5f; color: #60a5fa; }}
  .rec-consider{{ background: #451a03; color: #fbbf24; }}
  .rec-skip    {{ background: #1c1c1c; color: #6b7280; }}

  .toggle-btn {{
    background: none; border: none; color: #475569;
    font-size: 0.85rem; cursor: pointer; padding: 4px; transition: transform 0.2s;
  }}
  .toggle-btn.open {{ transform: rotate(180deg); }}

  .meta-row {{
    display: flex; flex-wrap: wrap; gap: 8px;
    padding: 0 16px 10px; font-size: 0.8rem; color: #94a3b8;
  }}
  .meta-item {{ display: flex; align-items: center; gap: 4px; }}

  .tags-row {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 12px; }}

  .tag {{
    font-size: 0.72rem; padding: 2px 8px; border-radius: 20px;
    font-weight: 500; white-space: nowrap;
  }}
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

  .sub-score {{
    font-size: 0.85rem; font-weight: 700; padding: 1px 6px; border-radius: 5px;
    text-transform: none; letter-spacing: 0;
  }}
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

  .card-actions {{
    display: flex; gap: 10px; margin-top: 14px; padding-top: 12px;
    border-top: 1px solid #2d3748;
  }}
  .apply-btn, .detail-link {{
    padding: 7px 18px; border-radius: 8px; font-size: 0.85rem;
    font-weight: 600; text-decoration: none; cursor: pointer;
  }}
  .apply-btn   {{ background: #2563eb; color: #fff; }}
  .apply-btn:hover {{ background: #1d4ed8; }}
  .detail-link {{ background: #1e2333; color: #94a3b8; border: 1px solid #2d3748; }}
  .detail-link:hover {{ background: #2d3748; }}

  .loc-ok  {{ color: #4ade80; font-weight: 600; font-size: 0.78rem; }}
  .loc-no  {{ color: #f87171; font-weight: 600; font-size: 0.78rem; }}
  .salary-note {{ color: #94a3b8; font-size: 0.875rem; line-height: 1.6; margin-top: 4px; }}
  .hidden {{ display: none !important; }}
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
  </div>

  <div class="cards" id="cards">
{cards_html}
  </div>
</div>

<script>
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
    const cardRec = card.dataset.rec.toLowerCase();
    card.classList.toggle('hidden', rec && cardRec !== rec);
  }});
}}
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
