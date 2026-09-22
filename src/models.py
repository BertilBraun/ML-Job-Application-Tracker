from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _normalize_escaped_newlines(text: str) -> str:
    return text.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')


class JobListing(BaseModel):
    title: str
    company: str
    url: str
    apply_url: str | None = None
    location: str = ''
    salary: str | None = None
    seniority: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    company_size: str | None = None
    industries: list[str] = Field(default_factory=list)
    date_added: str | None = None
    summary: str = ''
    description: str = ''
    requirements: str = ''
    minimum_years_experience: int | None = Field(default=None, ge=0)

    def __str__(self) -> str:
        desc = self.description[:120] + '...' if self.description else ''
        return f'{self.title} at {self.company} in {self.location} — {desc}'


class TeamAssessment(BaseModel):
    reasoning: str = Field(
        description='Are there senior ML/AI colleagues to learn from? Would the candidate be the sole ML expert? Assess the technical strength and size of the ML team.'
    )
    score: float = Field(
        ge=0, le=10, description='0-10: 10=strong team of ML experts to learn from, 0=sole ML expert or no real ML team'
    )


class WorkImpact(BaseModel):
    reasoning: str = Field(
        description='Is the work meaningful and beneficial to humanity? Is the ML technically substantive (not shallow API wrappers or prompt engineering)? What does the day-to-day actually look like?'
    )
    score: float = Field(
        ge=0,
        le=10,
        description='0-10: 10=highly impactful and technically deep, 0=harmful/meaningless or trivial wrapper work',
    )


class LocationFit(BaseModel):
    reasoning: str = Field(
        description='Does the location/remote setup work for the candidate based on their stated preferences in the profile? For non-local remote roles explicitly assess whether remote-from-their-country is genuinely possible or just marketing.'
    )
    works: bool = Field(
        description="True only if the location/remote setup is genuinely compatible with the candidate's constraints"
    )
    score: float = Field(
        ge=0,
        le=10,
        description='0-10 numeric score for location fit. If works=False use 0-3. If works=True use 7-10 based on how ideal (10=perfect south Germany hybrid or fully remote, 7=technically works but not ideal).',
    )


class CandidateFit(BaseModel):
    reasoning: str = Field(
        description=(
            'Assessment of whether the candidate has the technical foundations and demonstrated learning ability '
            'to contribute to and grow into the work. Keep this separate from CV screening probability.'
        )
    )
    score: float = Field(ge=0, le=10, description='0-10 technical match and growth potential for the work')
    screening_reasoning: str | None = Field(
        default=None,
        description=(
            'Realistic assessment of whether the current CV would pass initial screening, accounting for '
            'full-time tenure, title level, explicit years, credentials, and how directly the evidence is visible.'
        ),
    )
    screening_score: float | None = Field(
        default=None,
        ge=0,
        le=10,
        description='0-10 probability-oriented CV screening fit, separate from technical potential.',
    )
    strengths: list[str] = Field(description='Specific candidate strengths relevant to this role')
    gaps: list[str] = Field(description='Key gaps: skills or experience the role expects but candidate lacks')
    hard_blockers: list[str] = Field(
        default_factory=list,
        description='Only explicit non-negotiable requirements the candidate clearly does not meet.',
    )


class ApplicationPlan(BaseModel):
    role_type: str = Field(
        description=(
            'Short classification of the role, e.g. rl_control, llm_infra, '
            'general_ml, ml_security, computer_vision, agentic_llm, research.'
        )
    )
    posting_type: Literal[
        'specific_company',
        'anonymous_recruiter',
        'aggregator_or_job_board',
    ] = Field(description='Whether the posting provides direct company context or should be treated cautiously.')
    main_evidence_thread: str = Field(description='The main project or experience that should anchor the cover letter.')
    supporting_evidence: list[str] = Field(
        default_factory=list,
        description='One to three additional projects, methods, or metrics that support the application.',
    )
    evidence_to_avoid_or_downplay: list[str] = Field(
        default_factory=list,
        description='Projects or claims that are less relevant or could overstate fit for this role.',
    )
    claims_not_to_make: list[str] = Field(
        default_factory=list,
        description='Claims the application must avoid because they are unsupported or too strong.',
    )
    tone_strategy: str = Field(description='Brief description of how the letter should sound for this role.')
    cover_letter_angle: str = Field(description='One-sentence strategy for the cover letter.')


class ResumeOptimization(BaseModel):
    application_plan: ApplicationPlan = Field(
        description=(
            'Concise strategy for tailoring this application. Decide the role type, posting context, '
            'evidence anchor, supporting evidence, unsupported claims to avoid, and tone before writing.'
        )
    )
    about: str = Field(
        description='Rewritten About section tailored to this specific job. Same length and style as the original — rephrase emphasis, not personality. Keep it first-person, concrete, honest.'
    )
    key_bullets: list[str] = Field(
        description='3-5 existing bullet points from the CV (quoted verbatim or slightly rephrased) that are most relevant to lead with for this role. Pick from experience/projects sections.'
    )
    technical_skills: list[str] = Field(
        description=(
            'Exact compact grouped technical skill lines for the CV. Usually 3-4 lines, '
            '2-5 allowed. Each line should be a factual grouped line such as '
            '"Programming: Python, C++, SQL".'
        )
    )
    project_order: list[str] = Field(
        description=(
            'Canonical existing project names from the resume/FlowCV page in the desired CV order. '
            'Do not invent project names.'
        )
    )
    cover_opener: str = Field(
        description='Complete cover letter: a salutation line, then 3 short body paragraphs (1) why this specific role/problem, (2) one specific relevant connection or the breadth/fast-learner argument, (3) honest close acknowledging career stage and wanting to learn from the team, then a closing formula and the candidate name. Written entirely in the requested language. Direct, humble tone — no self-promotion, no achievement enumeration. Separate the salutation, each paragraph, and the closing with blank lines.'
    )

    @field_validator('about', 'cover_opener')
    @classmethod
    def _fix_escaped_newlines(cls, value: str) -> str:
        return _normalize_escaped_newlines(value)

    @field_validator('technical_skills')
    @classmethod
    def _validate_technical_skills(cls, value: list[str]) -> list[str]:
        lines = [line.strip() for line in value if line and line.strip()]
        if not (2 <= len(lines) <= 5):
            raise ValueError('technical_skills must contain 2-5 non-empty grouped skill lines')
        for line in lines:
            if '|' in line:
                raise ValueError('technical_skills must not contain markdown tables')
            if len(line) > 180:
                raise ValueError('technical_skills lines must stay compact')
        return lines

    @field_validator('project_order')
    @classmethod
    def _validate_project_order(cls, value: list[str]) -> list[str]:
        names = [name.strip() for name in value if name and name.strip()]
        seen: set[str] = set()
        deduped: list[str] = []
        for name in names:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                deduped.append(name)
        if not deduped:
            raise ValueError('project_order must contain at least one existing project name')
        return deduped


class _RawJobAnalysis(BaseModel):
    """LLM output schema without code-derived ranking fields."""

    job_summary: str = Field(description='2-3 sentences on what this job actually involves day-to-day')
    team_assessment: TeamAssessment
    work_impact: WorkImpact
    location_fit: LocationFit
    candidate_fit: CandidateFit
    salary_note: str = Field(
        description='If salary is listed, note it and compare to ~€80k target. If NOT listed, return empty string — do not estimate or speculate.'
    )
    key_concerns: list[str] = Field(description='Deal-breakers or significant red flags')


class SeniorityBand(str, Enum):
    STANDARD = 'standard'
    SENIOR_STRETCH = 'senior stretch'
    EXCLUDED = 'excluded title'


Recommendation = Literal['strong apply', 'apply', 'stretch apply', 'consider', 'skip']


@dataclass(frozen=True)
class OpportunityWeights:
    team: float = 0.40
    work: float = 0.25
    location: float = 0.20


DEFAULT_OPPORTUNITY_WEIGHTS = OpportunityWeights()

_EXCLUDED_TITLE_PATTERN = re.compile(r'\b(?:lead|staff|principal|head|director)\b', re.IGNORECASE)
_SENIOR_TITLE_PATTERN = re.compile(r'\b(?:senior|expert)\b', re.IGNORECASE)


def classify_seniority(title: str) -> SeniorityBand:
    if _EXCLUDED_TITLE_PATTERN.search(title):
        return SeniorityBand.EXCLUDED
    if _SENIOR_TITLE_PATTERN.search(title):
        return SeniorityBand.SENIOR_STRETCH
    return SeniorityBand.STANDARD


def compute_opportunity_score(
    raw: _RawJobAnalysis,
    weights: OpportunityWeights = DEFAULT_OPPORTUNITY_WEIGHTS,
) -> float:
    total = weights.team + weights.work + weights.location
    assert total > 0
    score = (
        weights.team * raw.team_assessment.score
        + weights.work * raw.work_impact.score
        + weights.location * raw.location_fit.score
    ) / total
    return round(score, 2)


def _require_screening_score(candidate_fit: CandidateFit) -> float:
    if candidate_fit.screening_score is None or candidate_fit.screening_reasoning is None:
        raise ValueError('Fresh analyses must include screening_score and screening_reasoning')
    return candidate_fit.screening_score


def calibrate_screening_score(
    raw: _RawJobAnalysis,
    job: JobListing,
    seniority_band: SeniorityBand,
) -> float:
    score = _require_screening_score(raw.candidate_fit)
    if seniority_band is SeniorityBand.SENIOR_STRETCH:
        score = min(score, 5.5)
    if job.minimum_years_experience is not None and job.minimum_years_experience >= 5:
        score = min(score, 5.0)
    return score


def compute_recommendation(
    raw: _RawJobAnalysis,
    opportunity_score: float,
    seniority_band: SeniorityBand,
    calibrated_screening_score: float,
) -> Recommendation:
    technical_score = raw.candidate_fit.score

    if not raw.location_fit.works or raw.candidate_fit.hard_blockers:
        return 'skip'

    match seniority_band:
        case SeniorityBand.EXCLUDED:
            return 'skip'
        case SeniorityBand.SENIOR_STRETCH:
            if opportunity_score >= 7.5 and calibrated_screening_score >= 4.5 and technical_score >= 6.5:
                return 'stretch apply'
            if opportunity_score >= 6.0 and calibrated_screening_score >= 4.0:
                return 'consider'
            return 'skip'
        case SeniorityBand.STANDARD:
            if opportunity_score >= 8.0 and calibrated_screening_score >= 7.0:
                return 'strong apply'
            if opportunity_score >= 7.0 and calibrated_screening_score >= 5.5:
                return 'apply'
            if opportunity_score >= 8.0 and calibrated_screening_score >= 4.0 and technical_score >= 7.0:
                return 'stretch apply'
            if opportunity_score >= 6.0 and calibrated_screening_score >= 4.5:
                return 'consider'
            return 'skip'


def compute_priority_score(
    opportunity_score: float,
    calibrated_screening_score: float,
    recommendation: Recommendation,
) -> float:
    score = math.sqrt(opportunity_score * calibrated_screening_score)
    if recommendation == 'skip':
        score = -abs(score)
    return round(score, 2)


class JobAnalysis(_RawJobAnalysis):
    opportunity_score: float = Field(default=0.0, description='Role desirability computed in code.')
    calibrated_screening_score: float = Field(
        default=0.0,
        description='CV screening fit after deterministic seniority and experience calibration.',
    )
    overall_score: float = Field(default=0.0, description='Application priority computed in code.')
    seniority_band: SeniorityBand = Field(default=SeniorityBand.STANDARD)
    recommendation: Recommendation = Field(default='consider')


def build_job_analysis(raw: _RawJobAnalysis, job: JobListing) -> JobAnalysis:
    opportunity_score = compute_opportunity_score(raw)
    seniority_band = classify_seniority(job.title)
    calibrated_screening_score = calibrate_screening_score(raw, job, seniority_band)
    recommendation = compute_recommendation(
        raw,
        opportunity_score,
        seniority_band,
        calibrated_screening_score,
    )
    return JobAnalysis(
        **raw.model_dump(),
        opportunity_score=opportunity_score,
        calibrated_screening_score=calibrated_screening_score,
        overall_score=compute_priority_score(
            opportunity_score,
            calibrated_screening_score,
            recommendation,
        ),
        seniority_band=seniority_band,
        recommendation=recommendation,
    )
