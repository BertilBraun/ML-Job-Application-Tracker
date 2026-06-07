"""
Application tracker server.
Run: python serve.py
  / — results page (regenerate with python scrape.py first)
  /applications — application tracker
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

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


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
