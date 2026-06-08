import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from .models import JobListing, JobAnalysis, ResumeOptimization

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


def _cache_path(job_url: str, guidance: str = '') -> Path:
    resume = _get_resume()
    key = hashlib.md5((resume + job_url + guidance.strip()).encode()).hexdigest()
    return CACHE_DIR / f'{key}_resume.json'


def _load_cache(job_url: str, guidance: str = '') -> ResumeOptimization | None:
    path = _cache_path(job_url, guidance)
    if path.exists():
        return ResumeOptimization.model_validate_json(path.read_text(encoding='utf-8'))
    return None


def _save_cache(job_url: str, result: ResumeOptimization, guidance: str = '') -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(job_url, guidance).write_text(result.model_dump_json(), encoding='utf-8')


_SYSTEM = """You are helping a job applicant tailor their resume and write a cover letter for a specific role.
You will receive the candidate's full CV and a job listing. Your task:

1. ABOUT SECTION — MINIMAL ADJUSTMENTS ONLY
   Keep the About section as close to the original as possible. Only rephrase individual phrases or
   reorder emphasis where a specific project or skill is directly relevant to this role. Do not rewrite
   sentences that don't need changing. The goal is a version the candidate could send without noticing
   it was touched — not a new draft.

2. KEY BULLETS
   Select 3–5 existing bullet points from the CV's experience/projects sections that are most directly
   relevant to this role. Quote verbatim or rephrase slightly. These are bullets to lead with.

3. COVER LETTER (full letter, 3 short paragraphs)
   Write a complete cover letter following this exact structure:
   - Paragraph 1: Why this specific role or problem space is interesting to the candidate. Be specific
     to the role, product area, or public company information — not generic enthusiasm.
     Ground claims in the job listing or public information. Prefer cautious openers like
     "What stood out to me...", "From the role description...", "The part of the work that
     interests me...", or "This seems close to..." when describing the company or role.
   - Paragraph 2: One specific, relevant connection between the candidate's background and this role.
     Either a directly relevant project/experience, or the fast-learner/breadth argument briefly made.
     Do not enumerate multiple achievements — pick one thread and follow it.
   - Paragraph 3: Honest close. Acknowledge career stage without apology. End on wanting to learn from
     the team, not on confidence in the candidate's own abilities.

   TONE RULES — follow these strictly:
   - Direct and humble. No self-promotional framing.
   - Never enumerate achievements in prose ("I built X, I built Y, I built Z").
   - Never tell the reader what to value ("this matters more than credentials").
   - No superlatives or self-aggrandizing phrases ("the clearest signal I can offer", "uniquely positioned").
   - No filler openers ("I am excited to apply", "I am writing to express my interest").
   - No phrases like "at the intersection of research and production" unless the role explicitly uses that framing.
   - Do not imply insider knowledge about the company. Avoid phrasing like "Your team is building..."
     unless the listing or public company page explicitly says that.
   - Sound like a person writing to another person, not a template.

   REFERENCE EXAMPLE (good tone — study the register, not the content):
   ---
   What interests me most in AI right now is long-horizon agentic systems — AI that can operate
   autonomously and conduct research over extended time horizons. The work Anthropic is doing on
   autonomous capabilities, including the security research from recent Claude releases, is the most
   compelling demonstration that this can be developed both ambitiously and safely. The post-training
   team is where that gets built at the model level — the fine-tuning, evaluation, and alignment
   methodology that determines whether a capable model is also trustworthy. Getting capabilities right
   is one problem; getting alignment right at the same time is the harder one.

   I pick up new areas quickly — in roughly two years I've built systems across reinforcement learning,
   computer vision, LLM pipelines, and graph neural networks, with real results in each. The most
   directly relevant piece is my Master's thesis, where I ran DPO fine-tuning at scale with synthetically
   generated preference data and built the evaluation infrastructure alongside it — that work became a
   first-author ACL 2025 publication.

   I'm applying at an earlier stage than most people here — this is where I want to grow, and it's
   genuinely the work I care about most.
   ---"""


def optimize_resume(
    job: JobListing,
    analysis: JobAnalysis,
    force_regenerate: bool = False,
    guidance: str = '',
) -> ResumeOptimization | None:
    guidance = guidance.strip()
    cached = _load_cache(job.url, guidance)
    if cached is not None and not force_regenerate:
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
"""

    if guidance:
        content += f"""
<candidate_guidance>
{guidance}
</candidate_guidance>

Use the candidate guidance to choose emphasis for the About section and cover letter. Treat it as steering,
not as a source of new facts: only mention projects, skills, and claims that are supported by the CV.
"""

    content += """
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
        _save_cache(job.url, result, guidance)
        return result
    except Exception as e:
        print(f'    Resume optimization error: {e}')
        return None
