"""
Source registry. To add a new site:
  1. Create scrapers/<sitename>.py with scrape_jobs(search_url, max_pages) -> list[JobListing]
  2. Add a Source entry to SOURCES below.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    from ..job_quality import (
        ExtractionAuditRecord,
        audit_job_listing,
        build_extraction_audit,
        duplicate_audit_record,
        normalize_job_listing,
        write_extraction_audit,
    )
    from ..models import JobListing
    from .linkedin import SEARCH_URL as _LI_URL
    from .linkedin import scrape_jobs as _scrape_linkedin
    from .remoterocketship import SEARCH_URL as _RRS_URL
    from .remoterocketship import scrape_jobs as _scrape_rrs
    from .stepstone import SEARCH_URL as _SS_URL
    from .stepstone import scrape_jobs as _scrape_stepstone
except ImportError:
    from job_quality import (
        ExtractionAuditRecord,
        audit_job_listing,
        build_extraction_audit,
        duplicate_audit_record,
        normalize_job_listing,
        write_extraction_audit,
    )
    from models import JobListing
    from scrapers.linkedin import SEARCH_URL as _LI_URL
    from scrapers.linkedin import scrape_jobs as _scrape_linkedin
    from scrapers.remoterocketship import SEARCH_URL as _RRS_URL
    from scrapers.remoterocketship import scrape_jobs as _scrape_rrs
    from scrapers.stepstone import SEARCH_URL as _SS_URL
    from scrapers.stepstone import scrape_jobs as _scrape_stepstone


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    fn: Callable[[str, int], list[JobListing]]
    url: str
    enabled: bool


SOURCES: list[Source] = [
    Source('linkedin', 'LinkedIn', _scrape_linkedin, _LI_URL, True),
    Source('stepstone', 'Stepstone', _scrape_stepstone, _SS_URL, True),
    Source('remoterocketship', 'RemoteRocketship', _scrape_rrs, _RRS_URL, True),
]

SOURCE_KEYS: list[str] = [s.key for s in SOURCES]


def scrape_all_sources(max_pages: int = 2, only: list[str] | None = None) -> list[JobListing]:
    all_jobs: list[JobListing] = []
    seen_urls: set[str] = set()
    audit_records: list[ExtractionAuditRecord] = []

    for source in SOURCES:
        if only is not None:
            if source.key not in only:
                continue
        elif not source.enabled:
            continue

        print(f'\n=== {source.name} ===')
        for scraped_job in source.fn(source.url, max_pages):
            job = normalize_job_listing(scraped_job)
            if job.url in seen_urls:
                audit_records.append(duplicate_audit_record(source.key, job))
                continue

            seen_urls.add(job.url)
            record = audit_job_listing(source.key, job)
            audit_records.append(record)
            if record.accepted:
                all_jobs.append(job)
                continue

            reasons = ', '.join(issue.code.value for issue in record.issues)
            print(f'  !! Quarantined malformed listing: {job.title!r} @ {job.company!r} ({reasons})')

    audit = build_extraction_audit(audit_records)
    audit_path = Path('extraction_audit.json')
    write_extraction_audit(audit, audit_path)
    print(f'\nExtraction audit: {audit.accepted} accepted, {audit.rejected} quarantined -> {audit_path}')

    return all_jobs
