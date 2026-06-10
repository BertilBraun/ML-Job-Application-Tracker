from __future__ import annotations

import inspect

import src.resume_optimizer as resume_optimizer
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
    monkeypatch.setattr(resume_optimizer, '_get_evidence_map', lambda: 'evidence text')
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


def test_resume_cache_key_includes_candidate_evidence_map(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_optimizer, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(resume_optimizer, '_get_resume', lambda: 'resume text')
    job, analysis = _job(), _analysis()

    monkeypatch.setattr(resume_optimizer, '_get_evidence_map', lambda: 'first evidence map')
    first = resume_optimizer._cache_path(job=job, analysis=analysis)

    monkeypatch.setattr(resume_optimizer, '_get_evidence_map', lambda: 'updated evidence map')
    second = resume_optimizer._cache_path(job=job, analysis=analysis)

    assert first != second


def test_resume_cache_key_includes_selected_provider_and_model(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_optimizer, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(resume_optimizer, '_get_resume', lambda: 'resume text')
    monkeypatch.setattr(resume_optimizer, '_get_evidence_map', lambda: 'evidence text')
    job, analysis = _job(), _analysis()

    monkeypatch.setenv('RESUME_OPTIMIZER_PROVIDER', 'gemini')
    gemini_path = resume_optimizer._cache_path(job=job, analysis=analysis)

    monkeypatch.setenv('RESUME_OPTIMIZER_PROVIDER', 'openai')
    openai_path = resume_optimizer._cache_path(job=job, analysis=analysis)

    assert gemini_path != openai_path


def test_resume_optimization_requires_application_plan():
    result = ResumeOptimization(
        application_plan=ApplicationPlan(
            role_type='rl_control',
            posting_type='specific_company',
            main_evidence_thread='GNN traffic signal control',
            supporting_evidence=['AlphaZero/self-play'],
            evidence_to_avoid_or_downplay=['GybeLock'],
            claims_not_to_make=['Direct autonomous driving production experience'],
            tone_strategy='Factual and technically specific.',
            cover_letter_angle='Anchor on traffic control RL and simulation evidence.',
        ),
        about='Tailored about',
        key_bullets=['Relevant bullet'],
        cover_opener='Dear team,\n\nCover letter.',
    )

    assert result.application_plan.posting_type == 'specific_company'
    assert result.application_plan.main_evidence_thread == 'GNN traffic signal control'


def test_optimizer_defines_provider_models_without_temperature():
    assert resume_optimizer.GEMINI_MODEL_NAME == 'gemini-3.1-pro-preview'
    assert resume_optimizer.OPENAI_MODEL_NAME == 'gpt-5.5'
    assert 'temperature=' not in inspect.getsource(resume_optimizer.optimize_resume)


def test_generate_resume_optimization_uses_openai_responses_parse(monkeypatch):
    result = ResumeOptimization(
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
    captured = {}

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)

            class ParsedResponse:
                output_parsed = result

            return ParsedResponse()

    class FakeOpenAIClient:
        responses = FakeResponses()

    monkeypatch.setenv('RESUME_OPTIMIZER_PROVIDER', 'openai')
    monkeypatch.setattr(resume_optimizer, '_get_openai_client', lambda: FakeOpenAIClient())

    assert resume_optimizer._generate_resume_optimization('Prompt content') is result
    assert captured['model'] == 'gpt-5.5'
    assert captured['input'] == [
        {'role': 'system', 'content': resume_optimizer._SYSTEM},
        {'role': 'user', 'content': 'Prompt content'},
    ]
    assert captured['text_format'] is ResumeOptimization
    assert captured['reasoning'] == {'effort': 'medium'}


def test_cover_letter_prompt_requires_grounded_public_framing():
    system_prompt = resume_optimizer._SYSTEM

    assert 'From the role description' in system_prompt
    assert 'What stood out to me' in system_prompt
    assert 'do not pretend company-specific knowledge' in system_prompt


def test_optimizer_prompt_prioritizes_specific_project_fit_over_jax_default():
    system_prompt = resume_optimizer._SYSTEM

    assert 'GNN traffic control' in system_prompt
    assert 'agentic LLM systems' in system_prompt
    assert 'JAX GPU-resident RL' in system_prompt
    assert 'Support with' in system_prompt


def test_optimizer_prompt_requires_inspectable_application_plan():
    system_prompt = resume_optimizer._SYSTEM

    assert 'First create the `application_plan` field' in system_prompt
    assert 'The plan is part of the JSON output' in system_prompt
    assert 'Do not use the phrase' in system_prompt
    assert 'I like hard problems' in system_prompt
