from __future__ import annotations

import src.resume_optimizer as resume_optimizer
from src.models import CandidateFit, JobAnalysis, JobListing, LocationFit, TeamAssessment, WorkImpact


def _job() -> JobListing:
    return JobListing(title='ML Engineer', company='Example GmbH', url='https://example.com/job')


def _analysis() -> JobAnalysis:
    return JobAnalysis(
        job_summary='Build ML systems.',
        team_assessment=TeamAssessment(reasoning='Senior ML team.', score=8),
        work_impact=WorkImpact(reasoning='Substantive ML.', score=8),
        location_fit=LocationFit(reasoning='Remote works.', works=True, score=8),
        candidate_fit=CandidateFit(reasoning='Good fit.', score=7, strengths=['RL'], gaps=[]),
        salary_note='',
        recommendation='apply',
        key_concerns=[],
        overall_score=8,
    )


def test_resume_cache_key_includes_generation_guidance(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_optimizer, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(resume_optimizer, '_get_resume', lambda: 'resume text')
    job, analysis = _job(), _analysis()

    no_guidance = resume_optimizer._cache_path(job=job, analysis=analysis)
    with_guidance = resume_optimizer._cache_path(
        job=job,
        analysis=analysis,
        guidance='Emphasize AlphaZero self-play and adversarial learning.',
    )

    assert no_guidance != with_guidance
    assert no_guidance.parent == tmp_path
    assert with_guidance.parent == tmp_path


def test_cover_letter_prompt_requires_grounded_public_framing():
    system_prompt = resume_optimizer._SYSTEM

    assert 'From the role description' in system_prompt
    assert 'What stood out to me' in system_prompt
    assert 'do not pretend company-specific knowledge' in system_prompt


def test_optimizer_prompt_prioritizes_specific_project_fit_over_jax_default():
    system_prompt = resume_optimizer._SYSTEM

    assert 'GNN traffic signal control' in system_prompt
    assert 'agentic LLM systems' in system_prompt
    assert 'JAX GPU-resident RL project' in system_prompt
    assert 'supporting evidence' in system_prompt
