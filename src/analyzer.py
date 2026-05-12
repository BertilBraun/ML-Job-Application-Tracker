import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from models import JobListing, JobAnalysis, _RawJobAnalysis, compute_overall_score

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / 'cache'

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

_system_prompt: str | None = None


def _build_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        profile = (Path(__file__).parent.parent / 'PROFILE.md').read_text(encoding='utf-8')
        _system_prompt = f"""You are evaluating job listings for a specific candidate. Your goal is to assess POSITION FIT — how good is this job for the candidate — not primarily whether they'll be accepted. A great position scores high even with uncertain acceptance.

<candidate_profile>
{profile}
</candidate_profile>

Score each dimension independently on a 0-10 scale:

1. TEAM: Can the candidate learn from senior ML/AI colleagues working on the same problems?
   - HIGH: dedicated ML team, senior researchers/engineers, candidate contributes to a larger ML effort
   - LOW: sole ML expert, tiny non-technical team, or "build our ML from scratch alone"
   - RED FLAG: phrasing like "you will own ML end-to-end" with no mention of existing ML colleagues

2. WORK IMPACT: Is the work meaningful AND technically substantive?
   - HIGH: healthcare/medical AI, scientific research, climate, safety-critical systems, education, infrastructure
   - LOW: AI chat companions, social media engagement bait, crypto/NFT, gambling, manipulative advertising, vanity apps
   - Also flag: roles that are 90% prompt engineering / API glue with no real model work

3. LOCATION: The candidate wants hybrid in south Germany (Munich/Stuttgart/Karlsruhe/Freiburg area) or Switzerland/Austria. OR fully remote from Germany or DACH-EU.
   - For non-DACH remote roles: explicitly check whether "remote" means remote-from-Germany or just within their country
   - Barcelona/Spain: flag — is it remote-from-Germany possible, or do they need someone local/Spanish-speaking?
   - On-site outside DACH: hard no (works=False, score 0-2)

4. CANDIDATE FIT: Technical match and realistic acceptance probability. Be honest — many "mid" roles expect 3-5 years industry experience. The candidate has strong project depth but limited formal tenure.

5. SALARY (context, not scored): Target ~€80k. If salary is listed, note and compare. If NOT listed, return empty string — never estimate or guess."""
    return _system_prompt


def _analysis_cache_path(url: str, system_prompt: str) -> Path:
    key = hashlib.md5((system_prompt + url).encode()).hexdigest()
    return CACHE_DIR / f'{key}_analysis.json'


def _load_analysis_cache(url: str, system_prompt: str) -> JobAnalysis | None:
    path = _analysis_cache_path(url, system_prompt)
    if path.exists():
        return JobAnalysis.model_validate_json(path.read_text(encoding='utf-8'))
    return None


def _save_analysis_cache(url: str, system_prompt: str, analysis: JobAnalysis) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _analysis_cache_path(url, system_prompt).write_text(analysis.model_dump_json(), encoding='utf-8')


def analyze_job(job: JobListing) -> JobAnalysis | None:
    system_prompt = _build_system_prompt()

    cached = _load_analysis_cache(job.url, system_prompt)
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
            model='gemini-2.5-flash-lite',
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
        _save_analysis_cache(job.url, system_prompt, result)
        return result
    except Exception as e:
        print(f'    Analysis error: {e}')
        return None
