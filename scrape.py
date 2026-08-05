"""
Job Listing Scraper & Analyzer
Usage: python scrape.py [--pages N] [--sources linkedin stepstone ...]
"""

import argparse
import json
import sys
import io
from pathlib import Path

from pydantic import TypeAdapter

# Force UTF-8 output on Windows to handle emoji in job data
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src.analyzer import analyze_job
from src.build_ui import build as build_ui
from src.models import JobAnalysis, JobListing
from src.scrapers import SOURCE_KEYS, scrape_all_sources

GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'
JOBS_PATH = Path('scraped_jobs.json')
JOB_LIST_ADAPTER = TypeAdapter(list[JobListing])


def score_color(score: float) -> str:
    if score >= 7:
        return GREEN
    elif score >= 5:
        return YELLOW
    return RED


def rec_color(rec: str) -> str:
    r = rec.lower()
    if 'strong' in r or r == 'apply':
        return GREEN
    elif r in {'stretch apply', 'consider'}:
        return YELLOW
    return RED


def print_result(job: JobListing, analysis: JobAnalysis, rank: int) -> None:
    sc = score_color(analysis.overall_score)
    rc = rec_color(analysis.recommendation)

    print(f'\n{"=" * 72}')
    print(f'{BOLD}#{rank}  {sc}{analysis.overall_score:.1f}/10{RESET}  [{rc}{analysis.recommendation.upper()}{RESET}]')
    print(f'    {BOLD}{job.title}{RESET} @ {job.company}')

    meta_parts = []
    if job.location:
        meta_parts.append(job.location)
    if job.salary:
        meta_parts.append(job.salary)
    if job.company_size:
        meta_parts.append(f'{job.company_size} employees')
    if meta_parts:
        print(f'    {" | ".join(meta_parts)}')

    print(f'    Detail: {job.url}')
    if job.apply_url:
        print(f'    Apply:  {job.apply_url}')

    print(f'\n  {BOLD}What it is:{RESET} {analysis.job_summary}')
    print(
        f'\n  {BOLD}Score split:{RESET} priority {analysis.overall_score:.1f} | '
        f'opportunity {analysis.opportunity_score:.1f} | '
        f'technical {analysis.candidate_fit.score:.1f} | '
        f'CV screening {analysis.calibrated_screening_score:.1f}'
    )

    ta = analysis.team_assessment
    print(f'\n  {BOLD}Team{RESET} ({sc}{ta.score:.1f}/10{RESET}): {ta.reasoning}')

    wi = analysis.work_impact
    print(f'\n  {BOLD}Work impact{RESET} ({sc}{wi.score:.1f}/10{RESET}): {wi.reasoning}')

    lf = analysis.location_fit
    loc_ok = f'{GREEN}OK{RESET}' if lf.works else f'{RED}NO{RESET}'
    print(f'\n  {BOLD}Location{RESET} [{loc_ok}]: {lf.reasoning}')

    cf = analysis.candidate_fit
    print(f'\n  {BOLD}Technical match{RESET} ({sc}{cf.score:.1f}/10{RESET}): {cf.reasoning}')
    if cf.screening_reasoning is not None and cf.screening_score is not None:
        raw_note = (
            f'; evaluator: {cf.screening_score:.1f}'
            if cf.screening_score != analysis.calibrated_screening_score
            else ''
        )
        print(
            f'\n  {BOLD}CV screening fit{RESET} '
            f'({analysis.calibrated_screening_score:.1f}/10{raw_note}): {cf.screening_reasoning}'
        )

    if cf.strengths:
        print(f'\n  {GREEN}Strengths:{RESET}')
        for s in cf.strengths:
            print(f'    + {s}')

    if cf.gaps:
        print(f'\n  {YELLOW}Gaps:{RESET}')
        for g in cf.gaps:
            print(f'    - {g}')

    if analysis.salary_note:
        print(f'\n  {BOLD}Salary:{RESET} {analysis.salary_note}')

    if analysis.key_concerns:
        print(f'\n  {RED}Concerns:{RESET}')
        for c in analysis.key_concerns:
            print(f'    ⚠ {c}')


def write_scraped_jobs(jobs: list[JobListing], path: Path = JOBS_PATH) -> None:
    path.write_bytes(JOB_LIST_ADAPTER.dump_json(jobs, indent=2))


def load_scraped_jobs(path: Path) -> list[JobListing]:
    return JOB_LIST_ADAPTER.validate_json(path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description='Scrape and analyze job listings')
    parser.add_argument('--pages', type=int, default=20, metavar='N', help='pages per source (default: 20)')
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=SOURCE_KEYS,
        metavar='SOURCE',
        help=f'sources to scrape (default: all enabled); choices: {", ".join(SOURCE_KEYS)}',
    )
    parser.add_argument('--scrape-only', action='store_true', help='scrape and validate listings without LLM analysis')
    parser.add_argument('--input', type=Path, help='analyze a previously validated scraped_jobs.json file')
    args = parser.parse_args()

    if args.scrape_only and args.input is not None:
        parser.error('--scrape-only and --input cannot be used together')

    print(f'{BOLD}Job Listing Scraper & LLM Analyzer{RESET}')
    if args.sources:
        print(f'Sources: {", ".join(args.sources)} | Pages: {args.pages}')
    else:
        print(f'Sources: all enabled | Pages: {args.pages}')

    if args.input is not None:
        jobs = load_scraped_jobs(args.input)
        print(f'Loaded {len(jobs)} validated listing(s) from {args.input}')
    else:
        jobs = scrape_all_sources(max_pages=args.pages, only=args.sources)
        write_scraped_jobs(jobs)
        print(f'Validated listings saved to {JOBS_PATH}')

    if not jobs:
        print('\nNo jobs found. The site may require login for full listings.')
        print('Try fetching page 1 only — the first 2-3 listings are usually free.')
        return

    if args.scrape_only:
        print('\nScrape-only run complete; no LLM analysis was started.')
        return

    print(f'\n{BOLD}Found {len(jobs)} job(s). Running analysis...{RESET}')

    results: list[tuple[JobListing, JobAnalysis]] = []
    for i, job in enumerate(jobs, 1):
        print(f'  [{i}/{len(jobs)}] {job.title} @ {job.company}')
        analysis = analyze_job(job)
        if not analysis:
            print('         -> Analysis failed, skipping')
            continue
        results.append((job, analysis))

    if not results:
        print('All analyses failed. Check GEMINI_API_KEY in .env')
        return

    results.sort(key=lambda x: x[1].overall_score, reverse=True)

    print(f'\n\n{BOLD}{"=" * 72}{RESET}')
    print(f'{BOLD}RESULTS — {len(results)} jobs, ranked by match score{RESET}')

    for rank, (job, analysis) in enumerate(results, 1):
        print_result(job, analysis, rank)

    print('\n' + '=' * 72 + '\n')

    print(f'{BOLD}Summary:{RESET}')
    for rank, (job, analysis) in enumerate(results, 1):
        rc = rec_color(analysis.recommendation)
        sc = score_color(analysis.overall_score)
        print(
            f'  {rank}. {sc}{analysis.overall_score:.1f}{RESET}  [{rc}{analysis.recommendation:<12}{RESET}]  {job.title} @ {job.company}'
        )

    output_data = [{'job': job.model_dump(), 'analysis': analysis.model_dump()} for job, analysis in results]

    output_path = Path('results.json')
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nFull results saved to {output_path}')

    ui_path = Path('results.html')
    ui_path.write_text(build_ui(output_data), encoding='utf-8')
    print(f'UI saved to {ui_path}')
    print('Start the app server: python serve.py')


if __name__ == '__main__':
    main()
