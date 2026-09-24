from __future__ import annotations

from types import SimpleNamespace

import pytest
from src import job_importer
from src.job_importer import ImportedJobPage
from src.models import JobListing


def _page() -> ImportedJobPage:
    return ImportedJobPage(
        url='https://example.com/job',
        final_url='https://example.com/job',
        title='Example job',
        markdown='# Example job',
    )


def _install_response(monkeypatch: pytest.MonkeyPatch, job: JobListing) -> None:
    response = SimpleNamespace(text=job.model_dump_json())
    models = SimpleNamespace(generate_content=lambda **_arguments: response)
    client = SimpleNamespace(models=models)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(job_importer.genai, 'Client', lambda **_arguments: client)


def test_parse_job_listing_normalizes_valid_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_response(
        monkeypatch,
        JobListing(
            title='Senior ML Engineer (Verified job)',
            company='Example GmbH',
            url='https://example.com/job',
            description='Build, train, evaluate, and deploy machine-learning systems. ' * 10,
            requirements='Requires 5+ years of relevant experience.',
        ),
    )

    job = job_importer.parse_job_listing_from_markdown(_page())

    assert job.title == 'Senior ML Engineer'
    assert job.seniority == ['Senior']
    assert job.minimum_years_experience == 5


def test_parse_job_listing_rejects_placeholder_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_response(
        monkeypatch,
        JobListing(
            title='ML Engineer',
            company='Example GmbH',
            url='https://example.com/job',
            description='Access denied',
        ),
    )

    with pytest.raises(ValueError, match='failed quality checks'):
        job_importer.parse_job_listing_from_markdown(_page())


def test_parse_job_listing_uses_fetched_url_not_model_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_response(
        monkeypatch,
        JobListing(
            title='ML Engineer',
            company='Example GmbH',
            url='https://unrelated.example/job',
            description='Build, train, evaluate, and deploy machine-learning systems. ' * 10,
        ),
    )

    job = job_importer.parse_job_listing_from_markdown(_page())

    assert job.url == 'https://example.com/job'


def test_html_to_markdown_preserves_job_structure() -> None:
    markdown = job_importer._html_to_markdown('<h1>ML Engineer</h1><p>Build models.</p>')

    assert '# ML Engineer' in markdown
    assert 'Build models.' in markdown
