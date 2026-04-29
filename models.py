from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


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
        description='Does the location/remote setup work for the candidate? They want: hybrid in south Germany (Munich/Stuttgart/Karlsruhe/Freiburg) or Switzerland/Austria, OR fully remote from Germany. For non-DACH roles explicitly assess whether remote-from-Germany is genuinely possible or just marketing.'
    )
    works: bool = Field(
        description="True only if the location/remote setup is genuinely compatible with the candidate's constraints"
    )


class CandidateFit(BaseModel):
    reasoning: str = Field(
        description='Realistic assessment of technical match and acceptance probability. Be honest — this is weighted less than position quality.'
    )
    score: float = Field(description='0-10: realistic competitiveness for this role')
    strengths: list[str] = Field(description='Specific candidate strengths relevant to this role')
    gaps: list[str] = Field(description='Key gaps: skills or experience the role expects but candidate lacks')


class JobAnalysis(BaseModel):
    job_summary: str = Field(description='2-3 sentences on what this job actually involves day-to-day')
    team_assessment: TeamAssessment
    work_impact: WorkImpact
    location_fit: LocationFit
    candidate_fit: CandidateFit
    salary_note: str = Field(
        description='If salary is listed, note it and compare to ~€80k target. If NOT listed, return empty string — do not estimate or speculate.'
    )
    overall_score: float = Field(
        description='Position fit score 0-10. Weights: team 40% + work impact 25% + location 20% + candidate fit 15%. A great role scores high even if acceptance is uncertain. If location fit is impossible -> negate the overall score i.e. multiply by -1'
    )
    recommendation: str = Field(
        description='Exactly one of: strong apply, apply, consider, skip. Based primarily on position fit (team/work/location), not acceptance probability.'
    )
    key_concerns: list[str] = Field(description='Deal-breakers or significant red flags')
