"""
Job Listing Scraper & Analyzer
Usage: python main.py [max_pages]
  max_pages: number of search result pages to scrape (default: 20)
"""

import json
import sys
import io
from pathlib import Path

# Force UTF-8 output on Windows to handle emoji in job data
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from scrapers import scrape_all_sources
from analyzer import analyze_job
from models import JobListing, JobAnalysis
from build_ui import build as build_ui

GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'


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
    elif r == 'consider':
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

    ta = analysis.team_assessment
    print(f'\n  {BOLD}Team{RESET} ({sc}{ta.score:.1f}/10{RESET}): {ta.reasoning}')

    wi = analysis.work_impact
    print(f'\n  {BOLD}Work impact{RESET} ({sc}{wi.score:.1f}/10{RESET}): {wi.reasoning}')

    lf = analysis.location_fit
    loc_ok = f'{GREEN}OK{RESET}' if lf.works else f'{RED}NO{RESET}'
    print(f'\n  {BOLD}Location{RESET} [{loc_ok}]: {lf.reasoning}')

    cf = analysis.candidate_fit
    print(f'\n  {BOLD}Candidate fit{RESET} ({sc}{cf.score:.1f}/10{RESET}): {cf.reasoning}')

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


def main() -> None:
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    print(f'{BOLD}Job Listing Scraper & LLM Analyzer{RESET}')
    print(f'Scraping up to {max_pages} page(s)...')

    jobs = scrape_all_sources(max_pages=max_pages)

    if not jobs:
        print('\nNo jobs found. The site may require login for full listings.')
        print('Try fetching page 1 only — the first 2-3 listings are usually free.')
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
    print('Start the app server: python app.py')


if __name__ == '__main__':
    main()
