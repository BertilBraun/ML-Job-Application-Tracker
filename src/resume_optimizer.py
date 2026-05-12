import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from models import JobListing, JobAnalysis, ResumeOptimization

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / 'cache'
RESUME_PATH = Path(__file__).parent.parent / 'RESUME.md'

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

_resume_text: str | None = None


def _get_resume() -> str:
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_PATH.read_text(encoding='utf-8')
    return _resume_text


def _cache_path(job_url: str) -> Path:
    resume = _get_resume()
    key = hashlib.md5((resume + job_url).encode()).hexdigest()
    return CACHE_DIR / f'{key}_resume.json'


def _load_cache(job_url: str) -> ResumeOptimization | None:
    path = _cache_path(job_url)
    if path.exists():
        return ResumeOptimization.model_validate_json(path.read_text(encoding='utf-8'))
    return None


def _save_cache(job_url: str, result: ResumeOptimization) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(job_url).write_text(result.model_dump_json(), encoding='utf-8')


_SYSTEM = """You are helping a job applicant tailor their resume for a specific role.
You will receive the candidate's full CV and a job listing. Your task:

1. Rewrite the About section to better match the role's emphasis — same honest, direct voice, same length.
   Shift which competencies and experiences are foregrounded; do not invent anything.

2. Select 3-5 existing bullet points from the CV's experience/projects sections that are most directly
   relevant to this role. Quote them verbatim or rephrase slightly for relevance. These are the bullets
   the candidate should move to the top of their most relevant experience entries.

3. Write a 2-3 sentence cover letter opener that is specific to this company and role.
   Reference something concrete about the company or job description. No filler phrases like
   "I am excited to apply". Sound like a person, not a template."""


def optimize_resume(job: JobListing, analysis: JobAnalysis) -> ResumeOptimization | None:
    cached = _load_cache(job.url)
    if cached is not None:
        print('      (resume cached)')
        return cached

    resume = _get_resume()

    content = f"""<candidate_cv>
{resume}
</candidate_cv>

<job_listing>
{job.title} at {job.company}
Location: {job.location or 'Not specified'}
Salary: {job.salary or 'Not specified'}

{job.description or job.summary or 'No description available'}
</job_listing>

<analysis_notes>
Candidate strengths for this role: {', '.join(analysis.candidate_fit.strengths)}
Gaps to be aware of: {', '.join(analysis.candidate_fit.gaps)}
</analysis_notes>

Tailor the resume for this specific role."""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                response_mime_type='application/json',
                response_schema=ResumeOptimization,
            ),
        )
        if not response.text:
            raise ValueError('Empty response')
        result = ResumeOptimization.model_validate_json(response.text)
        _save_cache(job.url, result)
        return result
    except Exception as e:
        print(f'    Resume optimization error: {e}')
        return None
