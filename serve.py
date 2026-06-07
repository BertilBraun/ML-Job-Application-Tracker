"""
Application tracker server.
Run: python serve.py
  / — results page (regenerate with python scrape.py first)
  /applications — application tracker
"""

import json
import re
from io import BytesIO
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from playwright.sync_api import sync_playwright

from src.db import get_db, init_db
from src.models import JobAnalysis, JobListing
from src.resume_optimizer import optimize_resume

app = Flask(__name__)
RESULTS_PATH = Path('results.json')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        return []
    return json.loads(RESULTS_PATH.read_text(encoding='utf-8'))


def _slug(value: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9]+', '-', value).strip('-')
    return slug or 'application'


def _paragraphs(text: str) -> str:
    chunks = [chunk.strip() for chunk in re.split(r'\n\s*\n', text.strip()) if chunk.strip()]
    return '\n'.join(f'<p>{escape(chunk).replace(chr(10), "<br>")}</p>' for chunk in chunks)


def _cover_letter_html(row: dict) -> str:
    title = escape(row['job_title'] or 'Application')
    company = escape(row['company'] or '')
    location_line = f'<div>{company}</div>' if company else ''
    letter = _paragraphs(row['cover_letter'])
    today = datetime.now()
    generated = f'{today:%B} {today.day}, {today.year}'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 22mm 23mm 24mm; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: #111827;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 11pt;
      line-height: 1.48;
    }}
    .sender {{
      border-bottom: 1px solid #d1d5db;
      padding-bottom: 12px;
      margin-bottom: 28px;
    }}
    .sender-name {{ font-size: 16pt; font-weight: 700; margin-bottom: 3px; }}
    .sender-meta {{ color: #4b5563; font-size: 9.5pt; }}
    .recipient {{ margin-bottom: 22px; color: #374151; }}
    .date {{ margin-bottom: 24px; color: #374151; }}
    h1 {{ font-size: 13pt; line-height: 1.35; margin: 0 0 18px; }}
    p {{ margin: 0 0 12px; }}
  </style>
</head>
<body>
  <section class="sender">
    <div class="sender-name">Bertil Braun</div>
    <div class="sender-meta">hi@bertil-braun.de | +49 1525 3810140 | Karlsruhe, Germany | linkedin.com/in/bertil-braun</div>
  </section>
  <section class="recipient">
    {location_line}
  </section>
  <section class="date">{generated}</section>
  <h1>Application for {title}</h1>
  <main>{letter}</main>
</body>
</html>"""


def _render_cover_letter_pdf(row: dict) -> bytes:
    html = _cover_letter_html(row)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until='load')
        pdf = page.pdf(format='A4', print_background=True)
        browser.close()
        return pdf


def _find_job(job_url: str) -> tuple[JobListing, JobAnalysis] | None:
    for entry in _load_results():
        if entry['job']['url'] == job_url:
            return (
                JobListing.model_validate(entry['job']),
                JobAnalysis.model_validate(entry['analysis']),
            )
    return None


# ── Pages ──────────────────────────────────────────────────────────────────────


@app.route('/')
def results_page():
    path = Path('results.html')
    if not path.exists():
        return 'Run python scrape.py first to generate results.', 404
    return send_file(path)


@app.route('/applications')
def applications_page():
    return render_template('applications.html')


# ── Applications API ───────────────────────────────────────────────────────────


@app.route('/api/applications', methods=['GET'])
def list_applications():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM applications ORDER BY created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/applications', methods=['POST'])
def create_application():
    data = request.get_json()
    job_url = (data.get('job_url') or '').strip()
    if not job_url:
        return jsonify({'error': 'job_url required'}), 400

    with get_db() as conn:
        existing = conn.execute(
            'SELECT id FROM applications WHERE job_url = ?', (job_url,)
        ).fetchone()
        if existing:
            return jsonify({'id': existing['id'], 'existing': True})

        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, listing_url, apply_url, location, salary, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
            (
                job_url,
                data.get('job_title', ''),
                data.get('company', ''),
                data.get('listing_url', job_url),
                data.get('apply_url', ''),
                data.get('location', ''),
                data.get('salary', ''),
                _now(),
            ),
        )
        app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Application started'),
        )
        return jsonify({'id': app_id, 'existing': False}), 201


@app.route('/api/applications/<int:app_id>/generate', methods=['POST'])
def generate_materials(app_id: int):
    # get the force_regenerate flag from the request query parameters, defaulting to False if not provided
    force_regenerate = request.args.get('force_regenerate', 'false').lower() == 'true'
    with get_db() as conn:
        row = conn.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404

        result = _find_job(row['job_url'])
        if not result:
            return jsonify({'error': 'Job not found in results.json — re-run scrape.py?'}), 404

        job, analysis = result
        opt = optimize_resume(job, analysis, force_regenerate=force_regenerate)
        if not opt:
            return jsonify({'error': 'Generation failed'}), 500

        conn.execute(
            'UPDATE applications SET about_text = ?, cover_letter = ? WHERE id = ?',
            (opt.about, opt.cover_opener, app_id),
        )
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Generated tailored About and cover letter'),
        )
        return jsonify(
            {
                'about': opt.about,
                'cover_letter': opt.cover_opener,
                'key_bullets': opt.key_bullets,
            }
        )


@app.route('/api/applications/<int:app_id>/cover-letter.pdf', methods=['GET'])
def download_cover_letter_pdf(app_id: int):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        row = dict(row)

    if not (row.get('cover_letter') or '').strip():
        return jsonify({'error': 'Cover letter has not been generated yet'}), 400

    pdf = _render_cover_letter_pdf(row)
    filename = f'{_slug(row.get("company") or "")}-{_slug(row.get("job_title") or "")}-cover-letter.pdf'
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


@app.route('/api/applications/<int:app_id>', methods=['PATCH'])
def update_application(app_id: int):
    data = request.get_json()
    allowed = {
        'status',
        'notes',
        'next_step_date',
        'next_step_label',
        'applied_at',
        'about_text',
        'cover_letter',
    }
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'No valid fields'}), 400

    set_clause = ', '.join(f'{k} = ?' for k in fields)
    with get_db() as conn:
        conn.execute(
            f'UPDATE applications SET {set_clause} WHERE id = ?',
            (*fields.values(), app_id),
        )
        if 'status' in fields:
            conn.execute(
                'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
                (app_id, _now(), f'Status → {fields["status"]}'),
            )
    return jsonify({'ok': True})


@app.route('/api/applications/<int:app_id>/events', methods=['GET'])
def get_events(app_id: int):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM events WHERE application_id = ? ORDER BY created_at',
            (app_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/applications/<int:app_id>/events', methods=['POST'])
def add_event(app_id: int):
    content = (request.get_json().get('content') or '').strip()
    if not content:
        return jsonify({'error': 'content required'}), 400
    with get_db() as conn:
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), content),
        )
    return jsonify({'ok': True}), 201


@app.route('/api/applications/<int:app_id>', methods=['DELETE'])
def delete_application(app_id: int):
    with get_db() as conn:
        conn.execute('DELETE FROM applications WHERE id = ?', (app_id,))
    return jsonify({'ok': True})


def main() -> None:
    init_db()
    app.run(debug=True, port=5000, use_reloader=False)


if __name__ == '__main__':
    main()
