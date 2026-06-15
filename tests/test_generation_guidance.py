from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import serve
import src.db as db
from src.models import (
    ApplicationPlan,
    CandidateFit,
    JobAnalysis,
    JobListing,
    LocationFit,
    ResumeOptimization,
    TeamAssessment,
    WorkImpact,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'applications.db'
    monkeypatch.setattr(db, 'DB_PATH', db_path)
    db.init_db()
    serve.app.config.update(TESTING=True)
    return serve.app.test_client()


def _analysis() -> JobAnalysis:
    return JobAnalysis(
        job_summary='Build ML systems.',
        team_assessment=TeamAssessment(reasoning='Senior ML team.', score=8),
        work_impact=WorkImpact(reasoning='Substantive ML.', score=8),
        location_fit=LocationFit(reasoning='Remote works.', works=True, score=8),
        candidate_fit=CandidateFit(
            reasoning='Good fit.',
            score=7,
            strengths=['RL'],
            gaps=[],
        ),
        salary_note='',
        recommendation='apply',
        key_concerns=[],
        overall_score=8,
    )


def test_generate_materials_passes_saved_guidance_to_optimizer(client, monkeypatch):
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, created_at, generation_guidance)
               VALUES (?, ?, ?, ?, ?)""",
            (
                'https://example.com/job',
                'ML Engineer',
                'Example GmbH',
                datetime.now(timezone.utc).isoformat(),
                'Emphasize AlphaZero self-play and adversarial learning.',
            ),
        )
        app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    job = JobListing(title='ML Engineer', company='Example GmbH', url='https://example.com/job')
    monkeypatch.setattr(serve, '_find_job', lambda _url: (job, _analysis()))
    captured = {}

    def fake_optimize_resume(job_arg, analysis_arg, force_regenerate=False, guidance='', language='en'):
        captured['guidance'] = guidance
        captured['force_regenerate'] = force_regenerate
        captured['language'] = language
        return ResumeOptimization(
            application_plan=ApplicationPlan(
                role_type='general_ml',
                posting_type='specific_company',
                main_evidence_thread='GybeLock',
                supporting_evidence=['LLM evaluation pipelines'],
                evidence_to_avoid_or_downplay=[],
                claims_not_to_make=[],
                tone_strategy='Factual and concise.',
                cover_letter_angle='Anchor on applied ML systems.',
            ),
            about='Tailored about',
            key_bullets=['Relevant bullet'],
            technical_skills=['Programming: Python, C++', 'ML: PyTorch, JAX'],
            project_order=['GybeLock - Multi-Object Tracking & Video Intelligence System'],
            cover_opener='Dear team,\n\nCover letter.',
        )

    monkeypatch.setattr(serve, 'optimize_resume', fake_optimize_resume)

    response = client.post(f'/api/applications/{app_id}/generate?force_regenerate=true')

    assert response.status_code == 200
    assert captured == {
        'guidance': 'Emphasize AlphaZero self-play and adversarial learning.',
        'force_regenerate': True,
        'language': 'en',
    }

    body = response.get_json()
    assert body['technical_skills'] == ['Programming: Python, C++', 'ML: PyTorch, JAX']
    assert body['project_order'] == ['GybeLock - Multi-Object Tracking & Video Intelligence System']
    with sqlite3.connect(db.DB_PATH) as conn:
        saved = conn.execute(
            'SELECT technical_skills, project_order, materials_status FROM applications WHERE id = ?',
            (app_id,),
        ).fetchone()
    assert saved[0] == '["Programming: Python, C++", "ML: PyTorch, JAX"]'
    assert saved[1] == '["GybeLock - Multi-Object Tracking & Video Intelligence System"]'
    assert saved[2] == 'ready'


def test_generate_materials_uses_stored_job_payload(client, monkeypatch):
    job = JobListing(title='Stored ML Engineer', company='Stored GmbH', url='https://stored.example/job')
    analysis = _analysis()
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, created_at, job_payload, analysis_payload)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                job.url,
                job.title,
                job.company,
                datetime.now(timezone.utc).isoformat(),
                job.model_dump_json(),
                analysis.model_dump_json(),
            ),
        )
        app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    captured = {}

    def fake_optimize_resume(job_arg, analysis_arg, force_regenerate=False, guidance='', language='en'):
        captured['job_title'] = job_arg.title
        captured['analysis_summary'] = analysis_arg.job_summary
        return ResumeOptimization(
            application_plan=ApplicationPlan(
                role_type='general_ml',
                posting_type='specific_company',
                main_evidence_thread='GybeLock',
                supporting_evidence=[],
                evidence_to_avoid_or_downplay=[],
                claims_not_to_make=[],
                tone_strategy='Factual and concise.',
                cover_letter_angle='Anchor on applied ML systems.',
            ),
            about='Tailored about',
            key_bullets=['Relevant bullet'],
            technical_skills=['Programming: Python, C++', 'ML: PyTorch, JAX'],
            project_order=['GybeLock - Multi-Object Tracking & Video Intelligence System'],
            cover_opener='Dear team,\n\nCover letter.',
        )

    monkeypatch.setattr(serve, 'optimize_resume', fake_optimize_resume)
    monkeypatch.setattr(serve, '_load_results', lambda: [])

    response = client.post(f'/api/applications/{app_id}/generate')

    assert response.status_code == 200
    assert captured == {'job_title': 'Stored ML Engineer', 'analysis_summary': 'Build ML systems.'}


def test_background_generation_endpoint_queues_work(client, monkeypatch):
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """INSERT INTO applications
               (job_url, job_title, company, created_at)
               VALUES (?, ?, ?, ?)""",
            ('https://example.com/job', 'ML Engineer', 'Example GmbH', datetime.now(timezone.utc).isoformat()),
        )
        app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    captured = {}
    monkeypatch.setattr(
        serve,
        '_start_background_generation',
        lambda app_id_arg, force_regenerate=False: captured.update(
            {'app_id': app_id_arg, 'force_regenerate': force_regenerate}
        ),
    )

    response = client.post(f'/api/applications/{app_id}/generate-background?force_regenerate=true')

    assert response.status_code == 202
    assert captured == {'app_id': app_id, 'force_regenerate': True}
    with sqlite3.connect(db.DB_PATH) as conn:
        saved = conn.execute(
            'SELECT materials_status FROM applications WHERE id = ?',
            (app_id,),
        ).fetchone()
    assert saved[0] == 'generating'


def test_import_application_url_tracks_analyzes_and_queues_generation(client, monkeypatch):
    job = JobListing(
        title='Imported ML Engineer',
        company='Imported GmbH',
        url='https://company.example/job',
        location='Remote',
        description='Build ML systems.',
    )
    analysis = _analysis()
    monkeypatch.setattr(
        serve,
        'import_job_from_url',
        lambda url: (job, SimpleNamespace(final_url=url, markdown='# Imported ML Engineer')),
    )
    monkeypatch.setattr(serve, 'analyze_job', lambda job_arg: analysis)
    captured = {}
    monkeypatch.setattr(
        serve,
        '_start_background_generation',
        lambda app_id_arg, force_regenerate=False: captured.update({'app_id': app_id_arg}),
    )

    response = client.post('/api/applications/import-url', json={'url': 'https://company.example/job'})

    assert response.status_code == 201
    body = response.get_json()
    assert body['job']['title'] == 'Imported ML Engineer'
    assert captured['app_id'] == body['id']
    with sqlite3.connect(db.DB_PATH) as conn:
        saved = conn.execute(
            'SELECT job_title, company, job_payload, analysis_payload FROM applications WHERE id = ?',
            (body['id'],),
        ).fetchone()
    assert saved[0] == 'Imported ML Engineer'
    assert saved[1] == 'Imported GmbH'
    assert 'Imported ML Engineer' in saved[2]
    assert 'Build ML systems.' in saved[3]
