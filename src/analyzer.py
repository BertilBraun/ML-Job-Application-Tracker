import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
try:
    from .models import JobListing, JobAnalysis, _RawJobAnalysis, compute_overall_score
except ImportError:
    from models import JobListing, JobAnalysis, _RawJobAnalysis, compute_overall_score

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / 'cache'

client: genai.Client | None = None

_system_prompt: str | None = None


def _build_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        profile = (Path(__file__).parent.parent / 'PROFILE.md').read_text(encoding='utf-8')
        _system_prompt = f"""You are evaluating job listings for a specific candidate. Your goal is to assess POSITION FIT — how good is this job for this candidate — not primarily whether they'll get hired. A great position scores high even with uncertain acceptance probability.

<candidate_profile>
{profile}
</candidate_profile>

Score each dimension independently on a 0–10 scale:

1. TEAM (most important — weight 40%)
   Does the candidate have senior ML/AI colleagues to learn from who are working on similar problems?
   - HIGH (8–10): dedicated ML team with experienced researchers/engineers; candidate contributes to a larger ML effort
   - MID (4–7): small but technically solid team; some ML peers
   - LOW (0–3): sole ML expert; non-technical team; "build our ML from scratch alone"; no mention of existing ML colleagues
   - HARD RED FLAG: "you will own ML end-to-end" with no existing ML team

2. WORK IMPACT (weight 25%)
   Is the work meaningful AND technically substantive?
   - HIGH: scientific research, healthcare/medical AI, climate, safety-critical systems, education, infrastructure, serious engineering products
   - MID: standard SaaS ML features, recommendation systems with real data
   - LOW: AI chat companions, social media engagement optimization, crypto/NFT, gambling, manipulative ad tech, pure prompt engineering / API glue with no real model work
   The question is: does the day-to-day involve real model work (training, evaluation, architecture) or just stitching APIs?

3. LOCATION (weight 20%)
   Assess against the candidate's preferences stated in the profile.
   - WORKS (score 7–10): hybrid in south Germany / Switzerland / Austria, OR genuinely remote-from-Germany
   - BORDERLINE (score 4–6): remote role but unclear if remote-from-Germany is genuinely supported
   - DOESN'T WORK (works=False, score 0–3): on-site outside DACH, or "remote" that clearly requires local presence
   For any non-DACH remote role: explicitly assess whether remote-from-Germany is real or just marketing copy.

4. CANDIDATE FIT (weight 15%)
   Honest technical match and realistic acceptance probability.
   The candidate has strong breadth (RL, CV, LLMs, systems) and real results, but ~4 years of working-student experience rather than full-time industry tenure. Be realistic — many "mid-level" roles expect 3–5 years full-time. Don't over-penalise project depth; don't ignore genuine experience gaps.

5. SALARY (context only, not scored)
   Target ~€80k. If salary is listed, note and compare. If NOT listed, return empty string — never estimate or speculate."""
    return _system_prompt


def _analysis_cache_path(job: JobListing, system_prompt: str) -> Path:
    key_material = '\n'.join([system_prompt, job.model_dump_json()])
    key = hashlib.md5(key_material.encode()).hexdigest()
    return CACHE_DIR / f'{key}_analysis.json'


def _load_analysis_cache(job: JobListing, system_prompt: str) -> JobAnalysis | None:
    path = _analysis_cache_path(job, system_prompt)
    if path.exists():
        return JobAnalysis.model_validate_json(path.read_text(encoding='utf-8'))
    return None


def _save_analysis_cache(job: JobListing, system_prompt: str, analysis: JobAnalysis) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _analysis_cache_path(job, system_prompt).write_text(
        analysis.model_dump_json(), encoding='utf-8'
    )


def analyze_job(job: JobListing) -> JobAnalysis | None:
    global client
    if client is None:
        client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

    system_prompt = _build_system_prompt()

    cached = _load_analysis_cache(job, system_prompt)
    if cached is not None:
        print('      (cached)')
        cached.overall_score = compute_overall_score(cached)
        return cached

    content = f"""Analyze this job listing for the candidate:

**{job.title}** at **{job.company}**

Location: {job.location or 'Not specified'}
Salary: {job.salary or 'Not specified'}
Seniority Level: {', '.join(job.seniority) if job.seniority else 'Not specified'}
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
            model='gemini-3.1-flash-lite',
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
        result = JobAnalysis(**raw.model_dump(), overall_score=compute_overall_score(raw))
        _save_analysis_cache(job, system_prompt, result)
        return result
    except Exception as e:
        print(f'    Analysis error: {e}')
        return None
