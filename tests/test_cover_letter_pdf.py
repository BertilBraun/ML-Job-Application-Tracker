from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

import serve
import src.db as db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'applications.db'
    monkeypatch.setattr(db, 'DB_PATH', db_path)
    db.init_db()
    serve.app.config.update(TESTING=True)
    return serve.app.test_client()


PLAUSIBLE_ABOUT = (
    'AI engineer with a research background, building end-to-end ML systems across '
    'reinforcement learning, computer vision, and LLM pipelines. MSc from KIT with '
    'an AI specialization, completed in half the standard time, and 3+ years of '
    'industry experience across startups and large organizations including '
    'Mercedes-Benz. I like hard problems. Whether that means designing a distributed '
    'self-play training system, building a multi-object tracking pipeline for video '
    'analysis, or developing automated LLM evaluation frameworks, I work across the '
    'full stack from research and algorithm design through to production deployment. '
    'Seeking applied ML or research engineering roles with experienced teams and '
    'challenging problems.'
)


def _insert_application(
    cover_letter: str | None,
    generation_guidance: str = '',
    about_text: str | None = None,
    technical_skills: str | None = None,
    project_order: str | None = None,
) -> int:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, created_at, cover_letter, generation_guidance,
                about_text, technical_skills, project_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                'https://example.com/job',
                'ML Engineer',
                'Example GmbH',
                datetime.now(timezone.utc).isoformat(),
                cover_letter,
                generation_guidance,
                about_text,
                technical_skills,
                project_order,
            ),
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def test_cover_letter_pdf_downloads_generated_letter(client, monkeypatch):
    app_id = _insert_application('Dear team,\n\nThis is a complete letter.')

    monkeypatch.setattr(serve, '_render_cover_letter_pdf', lambda *_args: b'%PDF-1.4\n')

    response = client.get(f'/api/applications/{app_id}/cover-letter.pdf')

    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.data.startswith(b'%PDF')
    assert 'attachment' in response.headers['Content-Disposition']
    assert 'Example-GmbH-ML-Engineer-cover-letter.pdf' in response.headers['Content-Disposition']


@pytest.mark.parametrize('cover_letter', [None, '', '   \n\t  '])
def test_cover_letter_pdf_errors_when_letter_missing(client, cover_letter):
    app_id = _insert_application(cover_letter)

    response = client.get(f'/api/applications/{app_id}/cover-letter.pdf')

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Cover letter has not been generated yet'


def test_generation_guidance_can_be_saved(client):
    app_id = _insert_application('Dear team')

    response = client.patch(
        f'/api/applications/{app_id}',
        json={'generation_guidance': 'Emphasize AlphaZero self-play.'},
    )

    assert response.status_code == 200
    with sqlite3.connect(db.DB_PATH) as conn:
        saved = conn.execute('SELECT generation_guidance FROM applications WHERE id = ?', (app_id,)).fetchone()[0]
    assert saved == 'Emphasize AlphaZero self-play.'


def test_cover_letter_html_uses_compact_letter_structure():
    html = serve._cover_letter_html(
        {
            'job_title': 'Machine Learning Engineer',
            'company': 'Blackwall',
            'cover_letter': 'Dear team,\n\nA short letter.',
        }
    )

    assert '<section class="subject">Application for Machine Learning Engineer</section>' in html
    assert '<h1>' not in html
    assert 'font-size: 10.5pt' in html
    assert 'font-size: 16pt' not in html


@pytest.mark.parametrize('about_text', [None, '', '   \n\t  ', 'Too short.'])
def test_tailored_cv_pdf_errors_when_about_missing_or_invalid(client, about_text):
    app_id = _insert_application('Dear team', about_text=about_text)

    response = client.post(f'/api/applications/{app_id}/cv.pdf')

    assert response.status_code == 400
    assert response.get_json()['error']


def test_tailored_cv_pdf_downloads_flowcv_result(client, monkeypatch, tmp_path):
    app_id = _insert_application(
        'Dear team',
        about_text=PLAUSIBLE_ABOUT,
        technical_skills='["Programming: Python, C++", "ML: PyTorch, JAX"]',
        project_order='["GybeLock - Multi-Object Tracking & Video Intelligence System"]',
    )
    pdf_path = tmp_path / 'generated-cv.pdf'
    pdf_path.write_bytes(b'%PDF-1.4\n')
    captured = {}

    def fake_replace_cv_content_and_download(
        *,
        about_text: str,
        technical_skills: list[str] | None,
        project_order: list[str] | None,
        target_path: Path,
    ) -> Path:
        captured['about_text'] = about_text
        captured['technical_skills'] = technical_skills
        captured['project_order'] = project_order
        captured['target_path'] = target_path
        target_path.write_bytes(pdf_path.read_bytes())
        return target_path

    monkeypatch.setattr(serve, 'replace_cv_content_and_download', fake_replace_cv_content_and_download)

    response = client.post(f'/api/applications/{app_id}/cv.pdf')

    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.data.startswith(b'%PDF')
    assert captured['about_text'] == PLAUSIBLE_ABOUT
    assert captured['technical_skills'] == ['Programming: Python, C++', 'ML: PyTorch, JAX']
    assert captured['project_order'] == ['GybeLock - Multi-Object Tracking & Video Intelligence System']
    assert captured['target_path'].name == 'Example-GmbH-ML-Engineer-cv.pdf'
    assert 'attachment' in response.headers['Content-Disposition']
    assert 'Example-GmbH-ML-Engineer-cv.pdf' in response.headers['Content-Disposition']


def test_tailored_cv_pdf_falls_back_when_cv_fields_empty(client, monkeypatch, tmp_path):
    app_id = _insert_application('Dear team', about_text=PLAUSIBLE_ABOUT)
    captured = {}

    def fake_replace_cv_content_and_download(
        *,
        about_text: str,
        technical_skills: list[str] | None,
        project_order: list[str] | None,
        target_path: Path,
    ) -> Path:
        captured['technical_skills'] = technical_skills
        captured['project_order'] = project_order
        target_path.write_bytes(b'%PDF-1.4\n')
        return target_path

    monkeypatch.setattr(serve, 'replace_cv_content_and_download', fake_replace_cv_content_and_download)

    response = client.post(f'/api/applications/{app_id}/cv.pdf')

    assert response.status_code == 200
    assert captured == {'technical_skills': None, 'project_order': None}
