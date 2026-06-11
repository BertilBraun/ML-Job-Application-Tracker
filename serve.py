"""
Application tracker server.
Run: python serve.py
  / — results page (regenerate with python scrape.py first)
  /applications — application tracker
"""

import json
import re
import unicodedata
from difflib import SequenceMatcher
from io import BytesIO
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from playwright.sync_api import sync_playwright

from src.db import get_db, init_db
from src.flowcv_automation import (
    DOWNLOAD_DIR,
    FlowCVError,
    FlowCVLoginRequired,
    replace_about_and_download_cv,
    validate_about_text,
)
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


SENDER_CITY = 'Karlsruhe/Stuttgart'
_MONTHS = {
    'en': [
        'January',
        'February',
        'March',
        'April',
        'May',
        'June',
        'July',
        'August',
        'September',
        'October',
        'November',
        'December',
    ],
    'de': [
        'Januar',
        'Februar',
        'März',
        'April',
        'Mai',
        'Juni',
        'Juli',
        'August',
        'September',
        'Oktober',
        'November',
        'Dezember',
    ],
}
_SUBJECT_PREFIX = {'en': 'Application for', 'de': 'Bewerbung als'}


def _clean_job_title(title: str) -> str:
    return re.sub(r'\s*\([^()]*(?:verifiziert|stellenanzeige)[^()]*\)', '', title, flags=re.I).strip()


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower()
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def _normalize_company_for_match(company: str) -> str:
    tokens = _normalize_match_text(company).split()
    suffixes = {
        'ag',
        'gmbh',
        'kg',
        'se',
        'ltd',
        'limited',
        'inc',
        'corp',
        'corporation',
        'llc',
        'co',
        'group',
    }
    meaningful = [token for token in tokens if token not in suffixes]
    return ' '.join(meaningful or tokens)


def _normalize_title_for_match(title: str) -> str:
    title = re.sub(r'\([^)]*\)', ' ', title or '')
    title = re.sub(r'\b[fmwd]{1,4}\b', ' ', title, flags=re.I)
    title = re.sub(r'\b(m|w|d|f|x)\s*/\s*(m|w|d|f|x)(?:\s*/\s*(m|w|d|f|x))*\b', ' ', title, flags=re.I)
    return _normalize_match_text(title)


def _titles_are_similar(first: str, second: str) -> bool:
    first_norm = _normalize_title_for_match(first)
    second_norm = _normalize_title_for_match(second)
    if not first_norm or not second_norm:
        return False
    if first_norm == second_norm:
        return True

    first_tokens = set(first_norm.split())
    second_tokens = set(second_norm.split())
    if len(first_tokens) >= 2 and first_tokens.issubset(second_tokens):
        return True
    if len(second_tokens) >= 2 and second_tokens.issubset(first_tokens):
        return True

    return SequenceMatcher(None, first_norm, second_norm).ratio() >= 0.82


def _possible_duplicates_for(row: dict, rows: list[dict]) -> list[dict]:
    if row.get('status') != 'draft':
        return []

    company = _normalize_company_for_match(row.get('company') or '')
    if not company:
        return []

    matches = []
    for other in rows:
        if other['id'] == row['id']:
            continue
        if other.get('status') in {'rejected', 'withdrawn'}:
            continue
        if _normalize_company_for_match(other.get('company') or '') != company:
            continue
        if not _titles_are_similar(row.get('job_title') or '', other.get('job_title') or ''):
            continue

        matches.append(
            {
                'id': other['id'],
                'job_title': other.get('job_title') or '',
                'company': other.get('company') or '',
                'status': other.get('status') or '',
                'applied_at': other.get('applied_at'),
                'reasons': ['same company', 'similar title'],
            }
        )

    return matches


def _with_possible_duplicates(rows: list[dict]) -> list[dict]:
    return [
        {
            **row,
            'possible_duplicates': _possible_duplicates_for(row, rows),
        }
        for row in rows
    ]


def _format_letter_date(today: datetime, language: str) -> str:
    month = _MONTHS.get(language, _MONTHS['en'])[today.month - 1]
    if language == 'de':
        return f'{SENDER_CITY}, {today.day}. {month} {today.year}'
    return f'{SENDER_CITY}, {today.day} {month} {today.year}'


def _cover_letter_html(row: dict) -> str:
    language = row.get('language') or 'en'
    template = app.jinja_env.get_template('cover_letter.html')
    return template.render(
        title=_clean_job_title(row['job_title'] or 'Application'),
        company=row['company'] or '',
        subject_prefix=_SUBJECT_PREFIX.get(language, _SUBJECT_PREFIX['en']),
        date_line=_format_letter_date(datetime.now(), language),
        letter_html=_paragraphs(row['cover_letter']),
    )


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
        return jsonify(_with_possible_duplicates([dict(r) for r in rows]))


@app.route('/api/applications', methods=['POST'])
def create_application():
    data = request.get_json()
    job_url = (data.get('job_url') or '').strip()
    if not job_url:
        return jsonify({'error': 'job_url required'}), 400

    with get_db() as conn:
        existing = conn.execute('SELECT id FROM applications WHERE job_url = ?', (job_url,)).fetchone()
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
        guidance = row['generation_guidance'] or ''
        opt = optimize_resume(
            job,
            analysis,
            force_regenerate=force_regenerate,
            guidance=guidance,
            language=row['language'] or 'en',
        )
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


@app.route('/api/applications/<int:app_id>/cv.pdf', methods=['POST'])
def download_tailored_cv_pdf(app_id: int):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        row = dict(row)

    try:
        about_text = validate_about_text(row.get('about_text') or '')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    filename = f'{_slug(row.get("company") or "")}-{_slug(row.get("job_title") or "")}-cv.pdf'
    target_path = DOWNLOAD_DIR / filename
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        pdf_path = replace_about_and_download_cv(about_text, target_path)
    except FlowCVLoginRequired as exc:
        return jsonify({'error': str(exc)}), 409
    except FlowCVError as exc:
        return jsonify({'error': str(exc)}), 500

    with get_db() as conn:
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Downloaded tailored CV from FlowCV'),
        )

    return send_file(
        pdf_path,
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
        'generation_guidance',
        'language',
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
