from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


def _normalize_escaped_newlines(text: str) -> str:
    return text.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')


class JobListing(BaseModel):
    title: str
    company: str
    url: str
    apply_url: Optional[str] = None
    location: str = ''
    salary: Optional[str] = None
    seniority: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    company_size: Optional[str] = None
    industries: list[str] = Field(default_factory=list)
    date_added: Optional[str] = None
    summary: str = ''
    description: str = ''
    requirements: str = ''

    def __str__(self):
        desc = self.description[:120] + '...' if self.description else ''
        return f'{self.title} at {self.company} in {self.location} — {desc}'


class TeamAssessment(BaseModel):
    reasoning: str = Field(
        description='Are there senior ML/AI colleagues to learn from? Would the candidate be the sole ML expert? Assess the technical strength and size of the ML team.'
    )
    score: float = Field(
        description='0-10: 10=strong team of ML experts to learn from, 0=sole ML expert or no real ML team'
    )


class WorkImpact(BaseModel):
    reasoning: str = Field(
        description='Is the work meaningful and beneficial to humanity? Is the ML technically substantive (not shallow API wrappers or prompt engineering)? What does the day-to-day actually look like?'
    )
    score: float = Field(
        description='0-10: 10=highly impactful and technically deep, 0=harmful/meaningless or trivial wrapper work'
    )


class LocationFit(BaseModel):
    reasoning: str = Field(
        description='Does the location/remote setup work for the candidate based on their stated preferences in the profile? For non-local remote roles explicitly assess whether remote-from-their-country is genuinely possible or just marketing.'
    )
    works: bool = Field(
        description="True only if the location/remote setup is genuinely compatible with the candidate's constraints"
    )
    score: float = Field(
        description='0-10 numeric score for location fit. If works=False use 0-3. If works=True use 7-10 based on how ideal (10=perfect south Germany hybrid or fully remote, 7=technically works but not ideal).'
    )


class CandidateFit(BaseModel):
    reasoning: str = Field(
        description='Realistic assessment of technical match and acceptance probability. Be honest — this is weighted less than position quality.'
    )
    score: float = Field(description='0-10: realistic competitiveness for this role')
    strengths: list[str] = Field(description='Specific candidate strengths relevant to this role')
    gaps: list[str] = Field(description='Key gaps: skills or experience the role expects but candidate lacks')


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
    ] = Field(
        description='Whether the posting provides direct company context or should be treated cautiously.'
    )
    main_evidence_thread: str = Field(
        description='The main project or experience that should anchor the cover letter.'
    )
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
    tone_strategy: str = Field(
        description='Brief description of how the letter should sound for this role.'
    )
    cover_letter_angle: str = Field(
        description='One-sentence strategy for the cover letter.'
    )


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
    cover_opener: str = Field(
        description='Complete cover letter: a salutation line, then 3 short body paragraphs (1) why this specific role/problem, (2) one specific relevant connection or the breadth/fast-learner argument, (3) honest close acknowledging career stage and wanting to learn from the team, then a closing formula and the candidate name. Written entirely in the requested language. Direct, humble tone — no self-promotion, no achievement enumeration. Separate the salutation, each paragraph, and the closing with blank lines.'
    )

    @field_validator('about', 'cover_opener')
    @classmethod
    def _fix_escaped_newlines(cls, value: str) -> str:
        return _normalize_escaped_newlines(value)


class _RawJobAnalysis(BaseModel):
    """LLM output schema — no overall_score, that is computed in code."""

    job_summary: str = Field(description='2-3 sentences on what this job actually involves day-to-day')
    team_assessment: TeamAssessment
    work_impact: WorkImpact
    location_fit: LocationFit
    candidate_fit: CandidateFit
    salary_note: str = Field(
        description='If salary is listed, note it and compare to ~€80k target. If NOT listed, return empty string — do not estimate or speculate.'
    )
    recommendation: str = Field(
        description='Exactly one of: strong apply, apply, consider, skip. Based primarily on position fit (team/work/location), not acceptance probability.'
    )
    key_concerns: list[str] = Field(description='Deal-breakers or significant red flags')


DEFAULT_WEIGHTS = {'team': 0.40, 'work': 0.25, 'location': 0.20, 'candidate': 0.15}


def compute_overall_score(raw: _RawJobAnalysis, weights: dict[str, float] = DEFAULT_WEIGHTS) -> float:
    total = sum(weights.values())
    score = (
        weights['team'] * raw.team_assessment.score
        + weights['work'] * raw.work_impact.score
        + weights['location'] * raw.location_fit.score
        + weights['candidate'] * raw.candidate_fit.score
    ) / total
    if not raw.location_fit.works:
        score = -abs(score)
    return round(score, 2)


class JobAnalysis(_RawJobAnalysis):
    overall_score: float = Field(default=0.0, description='Weighted score computed in code, not by the LLM.')
