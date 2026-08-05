from __future__ import annotations

from pathlib import Path

from scrape import load_scraped_jobs, write_scraped_jobs
from src.models import JobListing


def test_scraped_jobs_round_trip_uses_typed_job_list(tmp_path: Path) -> None:
    path = tmp_path / 'scraped_jobs.json'
    jobs = [
        JobListing(
            title='ML Engineer',
            company='Example GmbH',
            url='https://example.com/job',
            description='Build machine-learning systems. ' * 12,
            minimum_years_experience=3,
            seniority=['Mid-level'],
        )
    ]

    write_scraped_jobs(jobs, path)

    assert load_scraped_jobs(path) == jobs
