from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

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


def _insert_application(cover_letter: str | None, generation_guidance: str = '') -> int:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, created_at, cover_letter, generation_guidance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                'https://example.com/job',
                'ML Engineer',
                'Example GmbH',
                datetime.now(timezone.utc).isoformat(),
                cover_letter,
                generation_guidance,
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
        saved = conn.execute(
            'SELECT generation_guidance FROM applications WHERE id = ?', (app_id,)
        ).fetchone()[0]
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
