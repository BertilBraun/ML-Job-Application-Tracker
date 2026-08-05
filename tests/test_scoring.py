from __future__ import annotations

import pytest

from src.models import (
    CandidateFit,
    JobListing,
    LocationFit,
    SeniorityBand,
    TeamAssessment,
    WorkImpact,
    _RawJobAnalysis,
    build_job_analysis,
    classify_seniority,
)


def _raw_analysis(
    *,
    technical_score: float = 8.0,
    screening_score: float | None = 6.0,
    location_works: bool = True,
    hard_blockers: list[str] | None = None,
) -> _RawJobAnalysis:
    screening_reasoning = 'The CV is a plausible match.' if screening_score is not None else None
    return _RawJobAnalysis(
        job_summary='Build technically substantive ML systems.',
        team_assessment=TeamAssessment(reasoning='Experienced ML team.', score=9.0),
        work_impact=WorkImpact(reasoning='Core model work.', score=9.0),
        location_fit=LocationFit(
            reasoning='South Germany.',
            works=location_works,
            score=9.0 if location_works else 2.0,
        ),
        candidate_fit=CandidateFit(
            reasoning='Strong technical foundations.',
            score=technical_score,
            screening_reasoning=screening_reasoning,
            screening_score=screening_score,
            strengths=['Relevant model-training project'],
            gaps=['Limited full-time tenure'],
            hard_blockers=hard_blockers or [],
        ),
        salary_note='',
        key_concerns=[],
    )


@pytest.mark.parametrize(
    ('title', 'expected'),
    [
        ('Machine Learning Engineer', SeniorityBand.STANDARD),
        ('Senior Machine Learning Engineer', SeniorityBand.SENIOR_STRETCH),
        ('Staff Research Engineer', SeniorityBand.EXCLUDED),
        ('Principal AI Scientist', SeniorityBand.EXCLUDED),
        ('Lead ML Engineer', SeniorityBand.EXCLUDED),
        ('Head of Machine Learning', SeniorityBand.EXCLUDED),
        ('Director of AI', SeniorityBand.EXCLUDED),
    ],
)
def test_classify_seniority(title: str, expected: SeniorityBand) -> None:
    assert classify_seniority(title) is expected


def test_standard_role_can_be_strong_apply() -> None:
    raw = _raw_analysis(screening_score=8.0)
    job = JobListing(title='Machine Learning Engineer', company='Example', url='https://example.com/job')

    analysis = build_job_analysis(raw, job)

    assert analysis.opportunity_score == 9.0
    assert analysis.recommendation == 'strong apply'
    assert analysis.overall_score == pytest.approx(8.49, abs=0.01)


def test_senior_role_with_high_technical_match_is_kept_as_stretch() -> None:
    raw = _raw_analysis(technical_score=9.0, screening_score=5.0)
    job = JobListing(title='Senior ML Research Engineer', company='Example', url='https://example.com/job')

    analysis = build_job_analysis(raw, job)

    assert analysis.seniority_band is SeniorityBand.SENIOR_STRETCH
    assert analysis.recommendation == 'stretch apply'
    assert analysis.opportunity_score == 9.0
    assert analysis.overall_score == pytest.approx(6.71, abs=0.01)


def test_senior_role_screening_is_capped_even_if_evaluator_is_optimistic() -> None:
    raw = _raw_analysis(technical_score=10.0, screening_score=9.0)
    job = JobListing(title='Senior ML Research Engineer', company='Example', url='https://example.com/job')

    analysis = build_job_analysis(raw, job)

    assert analysis.candidate_fit.screening_score == 9.0
    assert analysis.calibrated_screening_score == 5.5
    assert analysis.overall_score == pytest.approx(7.04, abs=0.01)
    assert analysis.recommendation == 'stretch apply'


def test_explicit_five_year_requirement_caps_screening_fit() -> None:
    raw = _raw_analysis(screening_score=8.0)
    job = JobListing(
        title='Machine Learning Engineer',
        company='Example',
        url='https://example.com/job',
        minimum_years_experience=5,
    )

    analysis = build_job_analysis(raw, job)

    assert analysis.calibrated_screening_score == 5.0
    assert analysis.recommendation == 'stretch apply'


@pytest.mark.parametrize('title', ['Staff ML Engineer', 'Principal Scientist', 'Lead AI Engineer'])
def test_excluded_titles_are_skipped_even_when_the_work_is_attractive(title: str) -> None:
    raw = _raw_analysis(technical_score=10.0, screening_score=9.0)
    job = JobListing(title=title, company='Example', url='https://example.com/job')

    analysis = build_job_analysis(raw, job)

    assert analysis.recommendation == 'skip'
    assert analysis.overall_score < 0
    assert analysis.opportunity_score == 9.0


def test_location_and_hard_requirements_remain_blockers() -> None:
    location_blocked = build_job_analysis(
        _raw_analysis(location_works=False),
        JobListing(title='ML Engineer', company='Example', url='https://example.com/location'),
    )
    requirement_blocked = build_job_analysis(
        _raw_analysis(hard_blockers=['Mandatory medical license']),
        JobListing(title='ML Engineer', company='Example', url='https://example.com/requirement'),
    )

    assert location_blocked.recommendation == 'skip'
    assert location_blocked.overall_score < 0
    assert requirement_blocked.recommendation == 'skip'
    assert requirement_blocked.overall_score < 0


def test_fresh_analysis_requires_explicit_screening_assessment() -> None:
    raw = _raw_analysis(screening_score=None)
    job = JobListing(title='ML Engineer', company='Example', url='https://example.com/job')

    with pytest.raises(ValueError, match='screening_score'):
        build_job_analysis(raw, job)
