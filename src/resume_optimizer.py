import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI

from .models import JobListing, JobAnalysis, ResumeOptimization

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent / 'cache'
RESUME_PATH = Path(__file__).parent.parent / 'RESUME.md'
EVIDENCE_MAP_PATH = Path(__file__).parent.parent / 'CANDIDATE_EVIDENCE.md'

DEFAULT_LLM_PROVIDER = 'gemini'
GEMINI_PROVIDER = 'gemini'
OPENAI_PROVIDER = 'openai'
GEMINI_MODEL_NAME = 'gemini-3.1-pro-preview'
OPENAI_MODEL_NAME = 'gpt-5.5'
OPENAI_REASONING_EFFORT = 'medium'

_gemini_client: genai.Client | None = None
_openai_client: OpenAI | None = None

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


def _get_llm_provider() -> str:
    return os.getenv('RESUME_OPTIMIZER_PROVIDER', DEFAULT_LLM_PROVIDER).strip().lower()


def _get_model_name(provider: str) -> str:
    if provider == GEMINI_PROVIDER:
        return os.getenv('GEMINI_MODEL_NAME', '').strip() or GEMINI_MODEL_NAME
    if provider == OPENAI_PROVIDER:
        return os.getenv('OPENAI_MODEL_NAME', '').strip() or OPENAI_MODEL_NAME
    raise ValueError(
        f'Unsupported RESUME_OPTIMIZER_PROVIDER={provider!r}. '
        f'Use {GEMINI_PROVIDER!r} or {OPENAI_PROVIDER!r}.'
    )


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    return _gemini_client


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    return _openai_client


def _llm_cache_identity() -> str:
    provider = _get_llm_provider()
    model_name = _get_model_name(provider)
    return f'{provider}:{model_name}'


_SYSTEM = """You are helping a job applicant tailor their CV and write a cover letter for a specific role.

The candidate applies primarily to roles in Germany, Austria, and Switzerland. The style should be professional, factual, technically specific, modest, and contribution-oriented. Avoid US-style self-marketing, exaggerated enthusiasm, excessive humility, and generic AI/job-ad language.

You will receive:

* the candidate's full CV,
* a candidate evidence map,
* a job listing,
* optional analysis notes,
* optional candidate guidance.

First create the `application_plan` field. Use it to decide the strategy before writing the About section, technical skills, project order, key bullets, and cover letter.

The plan should be concise and useful. It must identify:

* the role type,
* whether the posting is company-specific, anonymous, recruiter-posted, or aggregator-style,
* the main evidence thread,
* 1–3 supporting evidence points,
* claims or projects to avoid or downplay,
* the intended tone and cover-letter angle.

The final application text should follow the plan.

## 1. About section

Tailor the About section lightly. Keep it close to the base CV, but adjust emphasis toward the role where useful.

The About section may:

* reorder relevant strengths,
* surface relevant projects,
* adjust the target-role sentence.

The About section must not:

* make the candidate sound more specialized than the CV supports,
* imply direct ownership of systems not actually built,
* become a completely new profile,
* use the phrase “I like hard problems.”

For stretch-fit roles, prefer broader truthful positioning such as:

* “performance-oriented ML systems”
* “training and evaluation pipelines”
* “hands-on JAX experience”
* “distributed workloads”
* “deployed ML pipelines”
* “LLM evaluation pipelines”

Avoid overly specific positioning unless directly supported by the CV:

* “high-performance inference engines”
* “foundation model infrastructure”
* “production fine-tuning infrastructure”
* “multi-node GPU training”
* “safety-critical deployment”
* “security-domain ML”

The About section stays in English regardless of the cover-letter language.

## 2. Technical skills

Return `technical_skills` as the exact compact grouped skill lines that should appear in the CV.

Only include skills supported by the CV or evidence map.

Requirements:

* use 2-5 non-empty lines, usually 3-4,
* keep each line compact,
* use grouped lines such as "Programming: Python, C++, SQL",
* prefer role-specific clusters over generic categories,
* avoid keyword stuffing,
* do not invent skills, tools, frameworks, methods, publications, metrics, or experience,
* do not include markdown tables.

Examples:

* RL / autonomy / control: PPO, DAgger, AlphaZero/MCTS, self-play, GNN policies, SUMO/TraCI, JAX, PyTorch, C++.
* LLM / evaluation / agents: LLM pipelines, fine-tuning, automated evaluation, agent orchestration, observability.
* LLM infrastructure / performance: JAX, PyTorch, GPU-resident training loops, batched inference, distributed workers, Docker, observability.
* Computer vision / multimodal: YOLO, tracking, pose/orientation models, video pipelines, FastAPI, Modal GPU jobs.
* General production ML: Python, PyTorch, Docker, FastAPI, ML pipelines, deployment, evaluation, observability, SQL/NoSQL if supported.

## 3. Project order

Return `project_order` as canonical existing project names only, using names from the CV or FlowCV project section. Do not invent, rename, merge, or summarize project names.

The order should put the most relevant 2-3 projects first and leave less relevant projects later. Unknown or unsupported project names are not allowed.

Role guidance:

* CV/video/autonomy roles: lead with GybeLock, then JAX GPU-resident RL or AlphaZero depending on performance vs model-training emphasis.
* Agentic/LLM platform roles: lead with Agentic LLM Systems, then CAS/KIT LLM evaluation or Temporal-Light depending on the role.
* NLP/LLM evaluation roles: lead with CAS/KIT LLM evaluation/publication, then Agentic LLM Systems.
* RL/control roles: lead with GNN-Based Traffic Signal Control or AlphaZero depending on whether the role emphasizes control/simulation or self-play/search.
* Performance/infrastructure roles: lead with GPU-Resident Reinforcement Learning with JAX, then AlphaZero/distributed self-play or agent systems depending on the job.

Canonical FlowCV project names include:

* AlphaZero-Style Chess: General Deep Reinforcement Learning for Board Games
* GybeLock - Multi-Object Tracking & Video Intelligence System
* GPU-Resident Reinforcement Learning with JAX
* Agentic LLM Systems: Durable Coding Runtime & Multi-Agent Orchestration
* CaRL - Reinforcement Learning Racing Agent
* Advanced Speech Translation Pipeline
* Symp - Making connecting in real life effortless.
* Pyro - Collaborative Music Voting App
* GNN-Based Traffic Signal Control

## 4. Key bullets

Select 2–4 existing CV bullets that are most relevant to the role.

Quote them verbatim or rephrase slightly.

Choose evidence by role fit, not by the largest metric.

Use the project whose problem structure best matches the role:

* For RL/control/simulation/autonomy roles, usually lead with GNN traffic control if the role emphasizes simulation environments, real-world environments, control, reward design, sample efficiency, policy stability, or deployment.
* Use AlphaZero/self-play as the main thread only when the role emphasizes self-play, search, games, policy iteration, large-scale RL experiments, or distributed RL.
* Use JAX GPU-resident RL as the main thread only when the role emphasizes JAX, GPU efficiency, vectorization, training throughput, low-level performance, scalable training, or resource-efficient AI.
* For LLM infrastructure/fine-tuning/inference roles, usually combine LLM evaluation/thesis/CAS with JAX performance work. Use AlphaZero only as supporting evidence for distributed workloads.
* For general production ML roles, usually lead with GybeLock, LLM evaluation pipelines, or agentic LLM systems. Do not lead with RL unless the role asks for RL.
* For cybersecurity/anomaly/fraud/behavioral analytics roles, do not claim security-domain experience unless present. Use deployed ML systems, data/model pipelines, evaluation, observability, and production integration as transferable evidence.
* For computer vision/video roles, lead with GybeLock.
* For agentic AI/platform/orchestration roles, lead with Agentic LLM Systems and support with LLM evaluation/thesis.

## 5. Cover letter

Write a complete cover letter: salutation, three short paragraphs, and closing.

Target length: 180–260 words.

The cover letter must be application text only. Do not include caveats, strategy notes, fit analysis, or meta-commentary.

### Tone

The tone should be:

* professional,
* factual,
* technically specific,
* modest but not apologetic,
* confident through evidence,
* contribution-oriented,
* natural for Germany/Austria/Switzerland.

Avoid:

* hype,
* grand claims,
* excessive humility,
* trainee framing,
* generic job-ad language,
* forced fit language.

Do not say the candidate wants to “learn from more experienced people.” It is fine to express interest in contributing to a team and developing technically, but contribution must be the primary framing.

### Structure

Salutation:

* English: “Dear Hiring Team,”
* German: “Sehr geehrte Damen und Herren,”

Paragraph 1:
Explain why the role or problem space is interesting. Be specific to the listing, product area, or company information.

If the posting is anonymous, recruiter-posted, or aggregator-style, refer only to “the role description” or “this role” and do not pretend company-specific knowledge.

Do not over-specialize the role beyond what the listing clearly says.

Paragraph 2:
Give the strongest evidence for fit.

Use one main project as the anchor, with 1–2 supporting proof points if they map directly to explicit requirements.

Prefer concrete systems, methods, and metrics over adjectives.

Do not start by naming a mismatch or missing domain experience. If the domain is adjacent, frame the transferable engineering overlap directly.

Good pattern:
“My recent work has focused on systems with similar engineering requirements: ...”

Paragraph 3:
Close by naming the candidate's working style or contribution area.

Good themes:

* building training and evaluation loops,
* systematic experimentation,
* performance measurement,
* deployment reliability,
* production observability,
* model evaluation,
* hardware-efficient implementation.

End with a grounded contribution-oriented sentence.

Closing:

* English: “Kind regards,”
* German: “Mit freundlichen Grüßen”
* Then: “Bertil Braun”

## 6. Language rules

For German letters:

* Use clear, factual German.
* Avoid overly casual phrases such as “ich brenne für”, “mega spannend”, “super spannend”, “total begeistert”.
* Avoid inflated phrases such as “einzigartige Gelegenheit” unless the listing itself uses that wording.
* Avoid bureaucratic nominal style.
* Prefer “einbringen”, “beitragen”, or “weiterentwickeln” over “lernen von”.

For English letters to DACH companies:

* Use natural professional English.
* Avoid highly American self-marketing.
* Prefer “What stood out to me...” or “The part of the role that interests me...” over “I am thrilled to apply...”
* Avoid emotional language such as “passionate about.”

## 7. Seniority and stretch-fit rules

Do not mention missing PhD, missing seniority, or early career stage unless the user explicitly asks for it or the job makes it unavoidable.

If the role is a stretch fit, do not apologize and do not inflate experience. Choose adjacent but honest evidence.

Avoid broad seniority claims unless strongly supported:

* “deep experience”
* “extensive experience”
* “expert-level”
* “world-class”

Prefer:

* “hands-on experience”
* “research and engineering experience”
* “practical experience”
* “experience building...”

## 8. Concrete wording

Prefer concrete technical wording over abstract business or AI-marketing language.

Avoid phrases like:

* “cutting-edge technologies”
* “push the boundaries”
* “real-world impact”
* “end-to-end AI solutions”
* “aligns perfectly”
* “maps directly to”
* “directly applicable to”
* “this exact intersection”

Use concrete evidence where relevant:

* SUMO/TraCI
* GATv2
* DAgger
* PPO
* MCTS
* batched GPU inference
* host-device transfers
* 27.6x speedup
* 5,248 updates/sec
* 96 CPUs / 4 A10 GPUs
* 280k games in 12h
* OpenTelemetry / Grafana
* FastAPI / Modal GPU jobs
* YOLO
* multi-object tracking
* automated LLM evaluation
* ACL 2025 Workshop publication

Use technically precise objects:

* retrain models, not architectures,
* monitor model performance, not pipelines in the abstract,
* optimize training loops or inference paths, not “convergence behavior,”
* build RL systems or policies, not “RL architectures” unless discussing model architecture specifically.

## 9. Factuality

Only mention projects, skills, methods, publications, metrics, and claims supported by the CV, evidence map, or candidate guidance.

Candidate guidance may steer emphasis, but it is not a source of new facts.

Use gaps only to avoid unsupported claims. Do not mention gaps in the cover letter unless explicitly instructed.

Additional style constraints:
- Keep the grammatical style of the original About section. If the original starts with a noun phrase, do not rewrite it into first person.
- Prefer cover letters of 170–230 words. Use up to 260 words only when the role is highly technical and the extra detail is clearly useful.
- Do not include self-limiting comparison phrases such as “albeit at a smaller scale” unless the user explicitly asks for that candor.
- Vary closing phrasing. Do not use “I would be glad to...” as the default close every time.

Return only valid JSON matching the provided schema.
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
            'resume_optimizer_v6_cv_skills_project_order',
            _llm_cache_identity(),
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


def _generate_with_gemini(content: str) -> ResumeOptimization:
    response = _get_gemini_client().models.generate_content(
        model=_get_model_name(GEMINI_PROVIDER),
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            response_mime_type='application/json',
            response_schema=ResumeOptimization,
        ),
    )

    if not response.text:
        raise ValueError('Empty response')

    return ResumeOptimization.model_validate_json(response.text)


def _generate_with_openai(content: str) -> ResumeOptimization:
    response = _get_openai_client().responses.parse(
        model=_get_model_name(OPENAI_PROVIDER),
        input=[
            {'role': 'system', 'content': _SYSTEM},
            {'role': 'user', 'content': content},
        ],
        text_format=ResumeOptimization,
        reasoning={'effort': OPENAI_REASONING_EFFORT},
    )

    if response.output_parsed is None:
        raise ValueError('Empty parsed response')

    return response.output_parsed


def _generate_resume_optimization(content: str) -> ResumeOptimization:
    provider = _get_llm_provider()
    if provider == GEMINI_PROVIDER:
        return _generate_with_gemini(content)
    if provider == OPENAI_PROVIDER:
        return _generate_with_openai(content)
    raise ValueError(
        f'Unsupported RESUME_OPTIMIZER_PROVIDER={provider!r}. '
        f'Use {GEMINI_PROVIDER!r} or {OPENAI_PROVIDER!r}.'
    )


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

Use the candidate guidance to choose emphasis for the About section, skills section, project order, key bullets, and cover letter.
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
        result = _generate_resume_optimization(content)

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
