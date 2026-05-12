"""
Source registry. To add a new site:
  1. Create scrapers/<sitename>.py with a scrape_jobs(search_url, max_pages) -> list[JobListing]
  2. Add an entry to SOURCES below.
"""

from models import JobListing
from scrapers.remoterocketship import scrape_jobs as _scrape_rrs, SEARCH_URL as _RRS_URL
from scrapers.stepstone import scrape_jobs as _scrape_stepstone, SEARCH_URL as _SS_URL
from scrapers.indeed import scrape_jobs as _scrape_indeed, SEARCH_URL as _IN_URL
from scrapers.linkedin import scrape_jobs as _scrape_linkedin, SEARCH_URL as _LI_URL

SOURCES = [
    {'name': 'RemoteRocketship', 'fn': _scrape_rrs, 'url': _RRS_URL, 'enabled': True},
    {'name': 'Stepstone', 'fn': _scrape_stepstone, 'url': _SS_URL, 'enabled': True},
    # TODO {"name": "Indeed",           "fn": _scrape_indeed,    "url": _IN_URL,  "enabled": True},
    {'name': 'LinkedIn', 'fn': _scrape_linkedin, 'url': _LI_URL, 'enabled': True},
]


def scrape_all_sources(max_pages: int = 2) -> list[JobListing]:
    all_jobs: list[JobListing] = []
    seen_urls: set[str] = set()

    for source in SOURCES:
        if not source['enabled']:
            continue
        print(f'\n=== {source["name"]} ===')
        for job in source['fn'](source['url'], max_pages):
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                all_jobs.append(job)

    return all_jobs
