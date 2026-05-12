"""
Source registry. To add a new site:
  1. Create scrapers/<sitename>.py with scrape_jobs(search_url, max_pages) -> list[JobListing]
  2. Add a Source entry to SOURCES below.
"""

from collections.abc import Callable
from dataclasses import dataclass

from models import JobListing
from scrapers.linkedin import scrape_jobs as _scrape_linkedin, SEARCH_URL as _LI_URL
from scrapers.remoterocketship import scrape_jobs as _scrape_rrs, SEARCH_URL as _RRS_URL
from scrapers.stepstone import scrape_jobs as _scrape_stepstone, SEARCH_URL as _SS_URL


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

    for source in SOURCES:
        if only is not None:
            if source.key not in only:
                continue
        elif not source.enabled:
            continue

        print(f'\n=== {source.name} ===')
        for job in source.fn(source.url, max_pages):
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                all_jobs.append(job)

    return all_jobs
