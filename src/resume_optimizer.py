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
EVIDENCE_MAP_PATH = Path(__file__).parent.parent / 'CANDIDATE_EVIDENCE.md'

MODEL_NAME = 'gemini-3.1-pro-preview'

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

_resume_text: str | None = None
_evidence_map_text: str | None = None


def _get_resume() -> str:
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_PATH.read_text(encoding='utf-8')
    return _resume_text


def _get_evidence_map() -> str:
    global _evidence_map_text
    if _evidence_map_text is None:
        _evidence_map_text = EVIDENCE_MAP_PATH.read_text(encoding='utf-8')
    return _evidence_map_text


_SYSTEM = """You are helping a job applicant tailor their resume and write a cover letter for a specific role.
The candidate applies primarily to roles in Germany, Austria, and Switzerland.

You will receive the candidate's full CV and a job listing.

First create the application_plan field. Use it to decide the strategy before writing the About section, key bullets, and cover letter.

The plan must decide:
- what kind of role this is,
- whether the posting is company-specific, anonymous, or aggregator/recruiter-style,
- which project or experience should be the main evidence thread,
- which 1-3 supporting pieces of evidence should be used,
- which projects or claims should be avoided or downplayed,
- which claims would overstate the candidate's fit,
- whether the cover letter should be research-oriented, systems-oriented, production-oriented, or performance-oriented.

The plan is part of the JSON output and may be inspected by the user. Keep it concise and useful.

Your task:

1. ABOUT SECTION — MINIMAL ADJUSTMENTS ONLY
   Keep the About section as close to the original as possible.
   Only rephrase individual phrases or reorder emphasis where a specific project or skill is directly relevant to this role.
   Do not rewrite sentences that do not need changing.
   The goal is a version the candidate could send without noticing it was heavily edited.

2. TECHNICAL SKILLS — TARGETED BUT FACTUAL
   You may reorder, regroup, or lightly rewrite the technical skills section to surface directly relevant skills already supported by the CV.
   Do not add unsupported technologies, frameworks, methods, or claims.
   Prefer role-specific clusters over generic categories.

   Examples:
   - RL / autonomy / control roles: PPO, DAgger, AlphaZero/MCTS, self-play, GNN policies, SUMO/TraCI, JAX, PyTorch, C++.
   - LLM / agent / evaluation roles: LLM pipelines, fine-tuning, automated evaluation, DPO if supported by CV, RAG, agent orchestration, observability.
   - LLM infrastructure / performance roles: JAX, PyTorch, GPU-resident training loops, batched inference, distributed workers, Docker, observability.
   - CV / multimodal roles: YOLO, tracking, pose/orientation models, video pipelines, deployment, full-stack ML systems.
   - General ML engineering roles: Python, PyTorch, JAX where relevant, Docker, FastAPI, ML pipelines, deployment, evaluation, observability.

3. KEY BULLETS
   Select 2–4 existing bullet points from the CV's experience/projects sections that are most directly relevant to this role.
   Quote verbatim or rephrase slightly.
   These are bullets to lead with.
   Choose by domain fit and explicit role requirements, not only by the largest metric.

   Reinforcement learning routing:
   - For RL in simulated, control, traffic, robotics, autonomy, or real-world decision systems, use the GNN traffic signal control project as the main project when the role emphasizes decision-making, simulation environments, control, PPO, or real-world systems.
   - Use AlphaZero/self-play as supporting evidence when the role emphasizes large-scale experiments, self-play, exploration, policy improvement, search, multi-agent RL, or policy iteration.
   - Use the JAX GPU-resident RL project as supporting evidence when the role emphasizes scalability, compute efficiency, runtime performance, JAX, GPU training, vectorization, or resource-efficient AI.
   - It is acceptable to mention all three briefly if the listing asks for broad RL research, large-scale experiments, and efficient implementation.

   LLM routing:
   - For LLM, agent, RAG, orchestration, evaluation, fine-tuning, post-training, or observability roles, prefer the agentic LLM systems and Master's thesis / LLM evaluation work.
   - Use the JAX GPU-resident project only as supporting evidence for performance engineering unless the listing explicitly emphasizes JAX or low-level training efficiency.

4. COVER LETTER
   Write a complete cover letter: salutation + 3 short paragraphs + closing.

   DACH application style:
   - Use a professional, factual, technically specific tone.
   - Avoid US-style motivational language, exaggerated enthusiasm, grand claims, and hype.
   - Avoid excessive humility that makes the candidate sound unqualified.
   - The ideal tone is precise, modest, confident through evidence, contribution-oriented, not salesy, and not bureaucratic.
   - Keep the letter concise: usually 180–260 words unless the language naturally requires slightly more.
   - The letter should sound like a competent technical applicant writing to another professional.

   Refined DACH tone rules:
   - Professional, factual, technically specific.
   - Modest but not apologetic.
   - Confident through evidence, not through self-praise.
   - Avoid US-style motivational language, exaggerated enthusiasm, and grand claims.
   - Avoid excessive humility that makes the candidate sound unqualified.
   - Avoid bureaucratic German nominal style.
   - Keep the cover letter concise: usually 180-260 words.
   - Do not frame the candidate as a trainee.
   - Do not say that the candidate wants to learn from more experienced people.
   - It is fine to express interest in contributing to a team and continuing to develop technically, but contribution must be the primary framing.

   Structure:
   - Salutation:
     Address the hiring team or company.
     If no contact name is known, use a polite generic greeting appropriate to the letter's language and DACH convention.
     English: "Dear Hiring Team,"
     German: "Sehr geehrte Damen und Herren,"
     One line, then a blank line.

   - Paragraph 1:
     Explain why this role or problem space is interesting to the candidate.
     Be specific to the listing, product area, or company information.
     If the posting is anonymous, recruiter-posted, or from an aggregator, refer only to "the role description" or "this role" and do not pretend company-specific knowledge.
     Prefer cautious openers like:
     "What stood out to me..."
     "From the role description..."
     "The part of the work that interests me..."
     "This seems close to..."
     For German letters, prefer factual formulations like:
     "Besonders interessiert mich..."
     "An der Rolle spricht mich vor allem an..."
     "Aus der Stellenbeschreibung geht für mich besonders hervor..."

   - Paragraph 2:
     Give the strongest evidence for fit.
     Use one main project as the narrative anchor, but include 1–2 additional concise proof points if they directly map to explicit role requirements.
     Prefer quantified, verifiable evidence from the CV.
     Do not list unrelated achievements.
     The letter should have high evidence density: concrete methods, metrics, systems, and outcomes are better than adjectives.

   - Paragraph 3:
     Close honestly and directly.
     Connect the candidate's working style to the role: end-to-end systems thinking, research-driven experimentation, performance focus, deployment orientation, fast technical depth, or careful evaluation.
     End with a grounded contribution-oriented close.
     The tone should be humble but not submissive.
     Do not frame the candidate as seeking training or permission to grow.
     Do not make the candidate sound like a trainee unless the job is explicitly junior.

   - Closing:
     A blank line, then a closing formula appropriate to the language:
     English: "Kind regards,"
     German: "Mit freundlichen Grüßen,"
     A blank line, then "Bertil Braun".

   Career-stage rule:
   Do not mention missing PhD, missing seniority, or early career stage unless the job explicitly makes this a major issue and the gap would otherwise be conspicuous.
   If mentioned, frame it as an unconventional/high-slope background with concrete evidence, not as a weakness.
   Prefer not mentioning it at all.

   German cover-letter rules:
   - Use "Sehr geehrte Damen und Herren," if no contact name is known.
   - Use "Mit freundlichen Grüßen" as closing.
   - Prefer clear factual phrasing over emotional enthusiasm.
   - Avoid overly casual formulations such as "ich brenne für", "mega spannend", "super spannend", "total begeistert".
   - Avoid inflated phrases such as "einzigartige Gelegenheit" unless the listing itself uses such wording.
   - Avoid translating English startup phrases literally.
   - Prefer "einbringen" / "beitragen" / "weiterentwickeln" over "lernen von".
   - Avoid unnecessary nominal style and bureaucratic phrasing.

   English cover-letter rules for DACH companies:
   - Use natural professional English, but avoid highly American self-marketing.
   - Prefer "What stood out to me..." or "The part of the role that interests me..." over "I am thrilled to apply..."
   - Emphasize concrete fit and contribution.
   - Avoid overly emotional language such as "passionate about" unless clearly natural and restrained.

   Never write:
   - "I am excited to apply..."
   - "I am writing to express my interest..."
   - "I am thrilled to apply..."
   - "While I am at an earlier stage in my career..."
   - "Although I do not hold a PhD..."
   - "I would welcome the opportunity to learn from..."
   - "I would love the opportunity to learn from..."
   - "I may not meet all requirements..."
   - "I may not meet all the listed qualifications..."
   - "I believe my background makes me uniquely positioned..."
   - "the clearest signal I can offer..."
   - "I am passionate about..."
   - "at the intersection of research and production" unless the job explicitly uses that framing.

   Do not imply insider knowledge about the company.
   Avoid phrasing like "your team is building..." unless the listing or public company page explicitly says that.

   The cover letter is candidate-facing application text.
   Do not include caveats, gap analysis, or strategic commentary inside it.
   
   Prefer concrete technical phrasing over abstract ML/general business phrasing.
   Avoid stacked abstract nouns such as "decision-making optimization", "convergence stability", "robust deployment pipelines", or "advanced AI initiatives" unless the phrase is unavoidable.

   Avoid abstract stacked technical phrases.
   Prefer concrete technical wording over generic phrases copied from job descriptions.

   Avoid phrases like:
   - optimize decision-making in dynamic environments
   - maintain convergence behavior
   - advanced AI initiatives
   - cutting-edge technologies
   - robust deployment pipelines
   - resource-efficient architectures
   - push the boundaries
   - real-world impact
   - end-to-end AI solutions

   Instead, use concrete systems, methods, and metrics:
   - SUMO/TraCI
   - GATv2
   - DAgger
   - PPO
   - MCTS
   - batched GPU inference
   - host-device transfers
   - 27.6x speedup
   - 5,248 updates/sec
   - 96 CPUs / 4 A10 GPUs
   - 280k games in 12h
   - OpenTelemetry / Grafana
   - FastAPI / Modal GPU jobs

   Every cover letter should include, if supported by the CV:
   - one concrete system or project,
   - one concrete method or technology,
   - one concrete metric.

   Do not use the phrase "I like hard problems" in generated About sections.
   Replace it with more factual wording such as:
   "My work focuses on technically demanding ML systems..."

   Project-selection principle:
   Use the project that best matches the role's actual work, not the project with the most impressive metric.

   Examples:
   - RL/control/simulation/autonomy roles: usually anchor on GNN traffic control. Support with AlphaZero and/or JAX GPU-resident RL if the listing emphasizes scale, self-play, PPO, sample efficiency, or compute efficiency.
   - LLM infrastructure/fine-tuning/inference roles: usually anchor on LLM evaluation/thesis/CAS and JAX performance work. Support with AlphaZero only for distributed training evidence.
   - General production ML roles: usually anchor on GybeLock, LLM evaluation pipelines, or agentic LLM systems. Do not lead with RL unless the job asks for RL.
   - Cybersecurity/anomaly/fraud/behavioral analytics roles: do not claim security-domain experience unless present. Anchor on deployed ML systems, data/model pipelines, evaluation, observability, and production integration. Prefer GybeLock and agentic/observability systems over JAX RL.
   - Computer vision/video roles: anchor on GybeLock.
   - Agentic AI/platform/orchestration roles: anchor on Agentic LLM systems and support with LLM evaluation/thesis.

5. FACTUALITY
   Only mention projects, skills, methods, publications, metrics, and claims supported by the CV or candidate guidance.
   Candidate guidance may steer emphasis, but it is not a source of new facts.
   Use gaps only to avoid unsupported claims.
   Do not mention gaps in the cover letter unless explicitly instructed.
"""


LANGUAGE_NAMES = {
    'en': 'English',
    'de': 'German',
}


def _cache_key(
    *,
    resume: str,
    evidence_map: str,
    job: JobListing,
    analysis: JobAnalysis,
    guidance: str,
    language: str,
) -> str:
    schema_repr = repr(ResumeOptimization.model_json_schema())

    key_material = '\n'.join(
        [
            'resume_optimizer_v4_plan_evidence_dach',
            MODEL_NAME,
            _SYSTEM,
            schema_repr,
            resume,
            evidence_map,
            job.url or '',
            job.title or '',
            job.company or '',
            job.location or '',
            job.salary or '',
            job.description or '',
            job.summary or '',
            guidance.strip(),
            language,
            'strengths:',
            '\n'.join(analysis.candidate_fit.strengths),
            'gaps:',
            '\n'.join(analysis.candidate_fit.gaps),
        ]
    )

    return hashlib.sha256(key_material.encode('utf-8')).hexdigest()


def _cache_path(
    *,
    job: JobListing,
    analysis: JobAnalysis,
    guidance: str = '',
    language: str = 'en',
) -> Path:
    resume = _get_resume()
    evidence_map = _get_evidence_map()
    key = _cache_key(
        resume=resume,
        evidence_map=evidence_map,
        job=job,
        analysis=analysis,
        guidance=guidance,
        language=language,
    )
    return CACHE_DIR / f'{key}_resume.json'


def _load_cache(
    *,
    job: JobListing,
    analysis: JobAnalysis,
    guidance: str = '',
    language: str = 'en',
) -> ResumeOptimization | None:
    path = _cache_path(
        job=job,
        analysis=analysis,
        guidance=guidance,
        language=language,
    )
    if path.exists():
        return ResumeOptimization.model_validate_json(path.read_text(encoding='utf-8'))
    return None


def _save_cache(
    *,
    job: JobListing,
    analysis: JobAnalysis,
    result: ResumeOptimization,
    guidance: str = '',
    language: str = 'en',
) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = _cache_path(
        job=job,
        analysis=analysis,
        guidance=guidance,
        language=language,
    )
    path.write_text(result.model_dump_json(), encoding='utf-8')


def optimize_resume(
    job: JobListing,
    analysis: JobAnalysis,
    force_regenerate: bool = False,
    guidance: str = '',
    language: str = 'en',
) -> ResumeOptimization | None:
    guidance = guidance.strip()

    cached = _load_cache(
        job=job,
        analysis=analysis,
        guidance=guidance,
        language=language,
    )
    if cached is not None and not force_regenerate:
        print('      (resume cached)')
        print('      Application plan:')
        print(cached.application_plan.model_dump_json(indent=2))
        return cached

    resume = _get_resume()
    evidence_map = _get_evidence_map()
    language_name = LANGUAGE_NAMES.get(language, 'English')

    content = f"""<candidate_cv>
{resume}
</candidate_cv>

<candidate_evidence_map>
{evidence_map}
</candidate_evidence_map>

<job_listing>
Title: {job.title}
Company: {job.company}
Location: {job.location or 'Not specified'}
Salary: {job.salary or 'Not specified'}
URL: {job.url or 'Not specified'}

{job.description or job.summary or 'No description available'}
</job_listing>

<analysis_notes>
Candidate strengths for this role:
{chr(10).join(f'- {s}' for s in analysis.candidate_fit.strengths)}

Gaps to be aware of:
{chr(10).join(f'- {g}' for g in analysis.candidate_fit.gaps)}
</analysis_notes>

Use strengths to choose emphasis.
Use gaps only to avoid unsupported claims.
Do not mention gaps, missing credentials, missing seniority, or weaknesses in the cover letter unless explicitly instructed.
Use the application_plan field to make the strategy explicit before writing.
The final application text should follow the plan.
If the job is a stretch fit, handle that by choosing adjacent but honest evidence. Do not apologize for missing requirements.
"""

    if guidance:
        content += f"""
<candidate_guidance>
{guidance}
</candidate_guidance>

Use the candidate guidance to choose emphasis for the About section, skills section, key bullets, and cover letter.
Treat it as steering, not as a source of new facts.
Only mention projects, skills, metrics, and claims that are supported by the CV.
"""

    content += f"""
Tailor the resume for this specific role.

Write the cover letter entirely in {language_name}.
This includes salutation, body, and closing.

The About section stays in English regardless of the cover letter language.

Return only valid JSON matching the provided schema.
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
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

        print('      Application plan:')
        print(result.application_plan.model_dump_json(indent=2))

        _save_cache(
            job=job,
            analysis=analysis,
            result=result,
            guidance=guidance,
            language=language,
        )

        return result

    except Exception as e:
        print(f'    Resume optimization error: {e}')
        return None
