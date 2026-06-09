from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

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
