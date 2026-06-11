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


def _insert_application(
    *,
    job_url: str,
    job_title: str,
    company: str,
    status: str = 'draft',
) -> int:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                job_url,
                job_title,
                company,
                status,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def test_list_applications_marks_draft_with_same_company_and_similar_title_as_duplicate(client):
    first_id = _insert_application(
        job_url='https://linkedin.com/jobs/view/123',
        job_title='Machine Learning Engineer (m/f/d)',
        company='Example GmbH',
        status='applied',
    )
    second_id = _insert_application(
        job_url='https://linkedin.com/jobs/view/124',
        job_title='Machine Learning Engineer',
        company='Example GmbH',
        status='draft',
    )

    response = client.get('/api/applications')

    assert response.status_code == 200
    apps = {app['id']: app for app in response.get_json()}
    assert apps[second_id]['possible_duplicates'] == [
        {
            'id': first_id,
            'job_title': 'Machine Learning Engineer (m/f/d)',
            'company': 'Example GmbH',
            'status': 'applied',
            'applied_at': None,
            'reasons': ['same company', 'similar title'],
        }
    ]
    assert apps[first_id]['possible_duplicates'] == []


def test_list_applications_marks_duplicate_drafts_against_each_other(client):
    first_id = _insert_application(
        job_url='https://linkedin.com/jobs/view/abc',
        job_title='AI Engineer',
        company='Acme AG',
    )
    second_id = _insert_application(
        job_url='https://linkedin.com/jobs/view/abd',
        job_title='AI Engineer - Applied ML',
        company='Acme AG',
    )

    response = client.get('/api/applications')

    assert response.status_code == 200
    apps = {app['id']: app for app in response.get_json()}
    assert apps[first_id]['possible_duplicates'][0]['id'] == second_id
    assert apps[second_id]['possible_duplicates'][0]['id'] == first_id


def test_list_applications_does_not_mark_non_draft_cards_as_duplicates(client):
    first_id = _insert_application(
        job_url='https://example.com/jobs/1',
        job_title='ML Engineer',
        company='Example GmbH',
        status='applied',
    )
    second_id = _insert_application(
        job_url='https://example.com/jobs/2',
        job_title='ML Engineer',
        company='Example GmbH',
        status='responded',
    )

    response = client.get('/api/applications')

    assert response.status_code == 200
    apps = {app['id']: app for app in response.get_json()}
    assert apps[first_id]['possible_duplicates'] == []
    assert apps[second_id]['possible_duplicates'] == []
