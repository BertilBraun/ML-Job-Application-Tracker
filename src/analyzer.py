import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from .models import JobAnalysis, JobListing, _RawJobAnalysis, build_job_analysis
except ImportError:
    from models import JobAnalysis, JobListing, _RawJobAnalysis, build_job_analysis

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / 'cache'
REQUEST_TIMEOUT_MS = 60_000
DEFAULT_ANALYSIS_MODEL = 'gemini-3.5-flash-lite'

client: genai.Client | None = None

_system_prompt: str | None = None


def _build_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        profile = (Path(__file__).parent.parent / 'PROFILE.md').read_text(encoding='utf-8')
        resume = (Path(__file__).parent.parent / 'RESUME.md').read_text(encoding='utf-8')
        evidence = (Path(__file__).parent.parent / 'CANDIDATE_EVIDENCE.md').read_text(encoding='utf-8')
        _system_prompt = f"""You are evaluating job listings for a specific candidate.

Keep three questions separate:
- OPPORTUNITY FIT: is the role, team, work, and location attractive to the candidate?
- TECHNICAL MATCH: does the candidate have relevant foundations and evidence to contribute and grow into the work?
- CV SCREENING FIT: is the current documented experience likely to pass the initial resume screen?

The candidate intentionally wants technically ambitious roles and learns quickly. Give real project depth full credit in technical match. Do not convert that potential into fictitious full-time tenure or senior-level resume evidence when assessing screening fit.

<candidate_profile>
{profile}
</candidate_profile>

<candidate_resume>
{resume}
</candidate_resume>

<candidate_evidence>
{evidence}
</candidate_evidence>

Score each dimension independently on a 0–10 scale:

1. TEAM
   Does the candidate have senior ML/AI colleagues to learn from who are working on similar problems?
   - HIGH (8–10): dedicated ML team with experienced researchers/engineers; candidate contributes to a larger ML effort
   - MID (4–7): small but technically solid team; some ML peers
   - LOW (0–3): sole ML expert; non-technical team; "build our ML from scratch alone"; no mention of existing ML colleagues
   - HARD RED FLAG: "you will own ML end-to-end" with no existing ML team

2. WORK IMPACT
   Is the work meaningful AND technically substantive?
   - HIGH: scientific research, healthcare/medical AI, climate, safety-critical systems, education, infrastructure, serious engineering products
   - MID: standard SaaS ML features, recommendation systems with real data
   - LOW: AI chat companions, social media engagement optimization, crypto/NFT, gambling, manipulative ad tech, pure prompt engineering / API glue with no real model work
   The question is: does the day-to-day involve real model work (training, evaluation, architecture) or just stitching APIs?

3. LOCATION
   Assess against the candidate's preferences stated in the profile.
   - WORKS (score 7–10): southern Germany with substantial remote time, or genuinely remote from Germany with manageable travel
   - BORDERLINE (score 4–6): office days or travel are unclear, including hybrid roles elsewhere in Switzerland or Austria
   - DOESN'T WORK (works=False, score 0–3): required on-site presence is impractical, or "remote" excludes working from Germany
   Verify the required office days and whether remote-from-Germany is genuinely supported. A hybrid label alone is not enough.

4. CANDIDATE FIT — return two deliberately different judgments
   a. `score` and `reasoning`: TECHNICAL MATCH and growth potential.
      - HIGH (8–10): directly relevant systems, methods, and demonstrated depth; credible ability to contribute even if the title is a stretch
      - MID (5–7): transferable foundations but meaningful domain or systems gaps
      - LOW (0–4): little evidence for the actual technical work
   b. `screening_score` and `screening_reasoning`: CURRENT CV SCREENING FIT.
      - HIGH (8–10): meets the stated career level, required years/credentials, and direct evidence is visible on the CV
      - PLAUSIBLE (6–7): credible screen pass with only modest experience gaps
      - STRETCH (4–5): strong adjacent projects or technical potential, but the CV is clearly short on full-time tenure, exact domain evidence, or required credentials
      - LOW (0–3): staff/principal/lead ownership, major hard requirements, or experience expectations are far beyond the documented CV
   The candidate has roughly four years of part-time working-student experience, not four years of full-time industry tenure. Do not call those equivalent. A senior title is usually a screening stretch even when technical match is high.
   Put only explicit, non-negotiable requirements the candidate clearly lacks in `hard_blockers`. Ordinary gaps belong in `gaps`, not `hard_blockers`.

5. SALARY (context only, not scored)
   Target ~€80k. If salary is listed, note and compare. If NOT listed, return empty string — never estimate or speculate.

Do not return a recommendation. Recommendation and ranking are computed deterministically after your assessment."""
    return _system_prompt


def _analysis_cache_path(job: JobListing, system_prompt: str, model_name: str) -> Path:
    key_material = f'{model_name}\n{system_prompt}\n{job.model_dump_json()}'
    key = hashlib.md5(key_material.encode()).hexdigest()
    return CACHE_DIR / f'{key}_analysis.json'


def _load_analysis_cache(job: JobListing, system_prompt: str, model_name: str) -> JobAnalysis | None:
    path = _analysis_cache_path(job, system_prompt, model_name)
    if path.exists():
        cached = JobAnalysis.model_validate_json(path.read_text(encoding='utf-8'))
        raw = _RawJobAnalysis.model_validate(cached.model_dump())
        return build_job_analysis(raw, job)
    return None


def _save_analysis_cache(job: JobListing, system_prompt: str, model_name: str, analysis: JobAnalysis) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _analysis_cache_path(job, system_prompt, model_name).write_text(analysis.model_dump_json(), encoding='utf-8')


def analyze_job(job: JobListing, *, model_name: str | None = None) -> JobAnalysis | None:
    global client
    if client is None:
        client = genai.Client(
            api_key=os.environ['GEMINI_API_KEY'],
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )

    system_prompt = _build_system_prompt()
    selected_model = model_name or os.getenv('GEMINI_ANALYSIS_MODEL', DEFAULT_ANALYSIS_MODEL)

    cached = _load_analysis_cache(job, system_prompt, selected_model)
    if cached is not None:
        print('      (cached)')
        return cached

    content = f"""Analyze this job listing for the candidate:

**{job.title}** at **{job.company}**

Location: {job.location or 'Not specified'}
Salary: {job.salary or 'Not specified'}
Seniority Level: {', '.join(job.seniority) if job.seniority else 'Not specified'}
Minimum Required Experience: {f'{job.minimum_years_experience}+ years' if job.minimum_years_experience is not None else 'Not extracted'}
Company Size: {job.company_size or 'Not specified'}
Industries: {', '.join(job.industries) if job.industries else 'Not specified'}
Tech Stack: {', '.join(job.tech_stack) if job.tech_stack else 'Not specified'}
Date Posted: {job.date_added or 'Not specified'}

**Summary:**
{job.summary or 'Not available'}

**Full Job Description:**
{job.description or 'Not available — analysis based on summary only'}

**Requirements:**
{job.requirements or 'Not available'}"""

    try:
        response = client.models.generate_content(
            model=selected_model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type='application/json',
                response_schema=_RawJobAnalysis,
            ),
        )
        if not response.text:
            raise ValueError('Empty response from model')
        raw = _RawJobAnalysis.model_validate_json(response.text)
        result = build_job_analysis(raw, job)
        _save_analysis_cache(job, system_prompt, selected_model, result)
        return result
    except Exception as error:  # noqa: BLE001 - provider and validation failures both invalidate this result.
        print(f'    Analysis error: {error}')
        return None
