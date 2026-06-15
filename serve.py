"""
Application tracker server.
Run: python serve.py
  / — results page (regenerate with python scrape.py first)
  /applications — application tracker
"""

import json
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from io import BytesIO
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from playwright.sync_api import sync_playwright

from src.db import get_db, init_db
from src.analyzer import analyze_job
from src.flowcv_automation import (
    DOWNLOAD_DIR,
    FlowCVError,
    FlowCVLoginRequired,
    replace_cv_content_and_download,
    validate_about_text,
)
from src.job_importer import import_job_from_url
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


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _dump_json_list(value: list[str]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dump_model(value) -> str:
    return value.model_dump_json()


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


def _job_from_application_row(row: dict) -> tuple[JobListing, JobAnalysis] | None:
    if not row.get('job_payload') or not row.get('analysis_payload'):
        return None
    try:
        return (
            JobListing.model_validate_json(row['job_payload']),
            JobAnalysis.model_validate_json(row['analysis_payload']),
        )
    except Exception:
        return None


def _find_job(job_url: str) -> tuple[JobListing, JobAnalysis] | None:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM applications WHERE job_url = ?', (job_url,)).fetchone()
        if row:
            stored = _job_from_application_row(dict(row))
            if stored:
                return stored

    for entry in _load_results():
        if entry['job']['url'] == job_url:
            return (
                JobListing.model_validate(entry['job']),
                JobAnalysis.model_validate(entry['analysis']),
            )
    return None


def _find_result_entry(job_url: str) -> dict | None:
    for entry in _load_results():
        if entry['job']['url'] == job_url:
            return entry
    return None


def _set_materials_status(app_id: int, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            'UPDATE applications SET materials_status = ? WHERE id = ?',
            (status, app_id),
        )


def _generate_materials_for_app(
    app_id: int,
    *,
    force_regenerate: bool = False,
) -> tuple[dict, int]:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
        if not row:
            return {'error': 'Not found'}, 404
        row = dict(row)

    result = _job_from_application_row(row) or _find_job(row['job_url'])
    if not result:
        _set_materials_status(app_id, 'failed')
        return {'error': 'Job not found in stored application data or results.json — re-run scrape.py?'}, 404

    job, analysis = result
    _set_materials_status(app_id, 'generating')
    try:
        opt = optimize_resume(
            job,
            analysis,
            force_regenerate=force_regenerate,
            guidance=row.get('generation_guidance') or '',
            language=row.get('language') or 'en',
        )
    except Exception:
        _set_materials_status(app_id, 'failed')
        raise
    if not opt:
        _set_materials_status(app_id, 'failed')
        return {'error': 'Generation failed'}, 500

    with get_db() as conn:
        conn.execute(
            (
                'UPDATE applications '
                'SET about_text = ?, technical_skills = ?, project_order = ?, cover_letter = ?, '
                'materials_status = ? '
                'WHERE id = ?'
            ),
            (
                opt.about,
                _dump_json_list(opt.technical_skills),
                _dump_json_list(opt.project_order),
                opt.cover_opener,
                'ready',
                app_id,
            ),
        )
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Generated tailored CV content and cover letter'),
        )

    return {
        'about': opt.about,
        'technical_skills': opt.technical_skills,
        'project_order': opt.project_order,
        'cover_letter': opt.cover_opener,
        'key_bullets': opt.key_bullets,
        'materials_status': 'ready',
    }, 200


def _start_background_generation(app_id: int, *, force_regenerate: bool = False) -> None:
    def run() -> None:
        payload, status = _generate_materials_for_app(app_id, force_regenerate=force_regenerate)
        if status >= 400:
            with get_db() as conn:
                conn.execute(
                    'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
                    (app_id, _now(), f'Background generation failed: {payload.get("error", "unknown error")}'),
                )

    _set_materials_status(app_id, 'generating')
    threading.Thread(target=run, daemon=True).start()


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

        job_payload = data.get('job_payload')
        analysis_payload = data.get('analysis_payload')
        if not job_payload or not analysis_payload:
            result_entry = _find_result_entry(job_url)
            if result_entry:
                job_payload = job_payload or json.dumps(result_entry['job'], ensure_ascii=False)
                analysis_payload = analysis_payload or json.dumps(result_entry['analysis'], ensure_ascii=False)

        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, listing_url, apply_url, location, salary, status,
                created_at, job_payload, analysis_payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)""",
            (
                job_url,
                data.get('job_title', ''),
                data.get('company', ''),
                data.get('listing_url', job_url),
                data.get('apply_url', ''),
                data.get('location', ''),
                data.get('salary', ''),
                _now(),
                job_payload,
                analysis_payload,
            ),
        )
        app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Application started'),
        )
        return jsonify({'id': app_id, 'existing': False}), 201


@app.route('/api/applications/import-url', methods=['POST'])
def import_application_url():
    data = request.get_json()
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400

    try:
        job, imported_page = import_job_from_url(url)
    except Exception as exc:
        return jsonify({'error': f'Job import failed: {exc}'}), 500

    analysis = analyze_job(job)
    if not analysis:
        return jsonify({'error': 'Job analysis failed'}), 500

    with get_db() as conn:
        existing = conn.execute('SELECT id FROM applications WHERE job_url = ?', (job.url,)).fetchone()
        if existing:
            app_id = existing['id']
            conn.execute(
                (
                    'UPDATE applications SET job_title = ?, company = ?, listing_url = ?, apply_url = ?, '
                    'location = ?, salary = ?, job_payload = ?, analysis_payload = ? WHERE id = ?'
                ),
                (
                    job.title,
                    job.company,
                    job.url,
                    job.apply_url or '',
                    job.location,
                    job.salary or '',
                    _dump_model(job),
                    _dump_model(analysis),
                    app_id,
                ),
            )
            existing_flag = True
        else:
            conn.execute(
                """INSERT INTO applications
                   (job_url, job_title, company, listing_url, apply_url, location, salary, status,
                    created_at, job_payload, analysis_payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)""",
                (
                    job.url,
                    job.title,
                    job.company,
                    job.url,
                    job.apply_url or '',
                    job.location,
                    job.salary or '',
                    _now(),
                    _dump_model(job),
                    _dump_model(analysis),
                ),
            )
            app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute(
                'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
                (app_id, _now(), f'Imported job URL via Playwright Markdown: {imported_page.final_url}'),
            )
            existing_flag = False

    _start_background_generation(app_id)
    return jsonify(
        {
            'id': app_id,
            'existing': existing_flag,
            'job': job.model_dump(),
            'analysis': analysis.model_dump(),
        }
    ), 200 if existing_flag else 201


@app.route('/api/applications/<int:app_id>/generate', methods=['POST'])
def generate_materials(app_id: int):
    force_regenerate = request.args.get('force_regenerate', 'false').lower() == 'true'
    payload, status = _generate_materials_for_app(app_id, force_regenerate=force_regenerate)
    return jsonify(payload), status

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
            (
                'UPDATE applications '
                'SET about_text = ?, technical_skills = ?, project_order = ?, cover_letter = ? '
                'WHERE id = ?'
            ),
            (
                opt.about,
                _dump_json_list(opt.technical_skills),
                _dump_json_list(opt.project_order),
                opt.cover_opener,
                app_id,
            ),
        )
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Generated tailored CV content and cover letter'),
        )
        return jsonify(
            {
                'about': opt.about,
                'technical_skills': opt.technical_skills,
                'project_order': opt.project_order,
                'cover_letter': opt.cover_opener,
                'key_bullets': opt.key_bullets,
            }
        )


@app.route('/api/applications/<int:app_id>/generate-background', methods=['POST'])
def generate_materials_background(app_id: int):
    force_regenerate = request.args.get('force_regenerate', 'false').lower() == 'true'
    with get_db() as conn:
        row = conn.execute('SELECT id FROM applications WHERE id = ?', (app_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        conn.execute(
            'INSERT INTO events (application_id, created_at, content) VALUES (?, ?, ?)',
            (app_id, _now(), 'Queued tailored CV and cover letter generation'),
        )
        conn.execute(
            'UPDATE applications SET materials_status = ? WHERE id = ?',
            ('generating', app_id),
        )
    _start_background_generation(app_id, force_regenerate=force_regenerate)
    return jsonify({'ok': True, 'id': app_id}), 202


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
    technical_skills = _json_list(row.get('technical_skills'))
    project_order = _json_list(row.get('project_order'))

    try:
        pdf_path = replace_cv_content_and_download(
            about_text=about_text,
            technical_skills=technical_skills or None,
            project_order=project_order or None,
            target_path=target_path,
        )
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
        'technical_skills',
        'project_order',
    }
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'No valid fields'}), 400
    for list_field in ('technical_skills', 'project_order'):
        if isinstance(fields.get(list_field), list):
            fields[list_field] = _dump_json_list([str(item) for item in fields[list_field]])

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
