from __future__ import annotations

from src.job_quality import (
    ExtractionIssueCode,
    audit_job_listing,
    build_extraction_audit,
    duplicate_audit_record,
    normalize_job_listing,
    write_extraction_audit,
)
from src.models import JobListing
from src.scrapers.stepstone import _page_url


def _job(**updates: object) -> JobListing:
    values: dict[str, object] = {
        'title': 'Senior ML Engineer (Verified job)',
        'company': ' Example GmbH ',
        'url': ' https://example.com/jobs/1 ',
        'location': ' Karlsruhe ',
        'description': 'Build and evaluate production machine-learning systems. ' * 12,
        'requirements': 'At least 5 years of professional experience with Python and PyTorch.',
    }
    values.update(updates)
    return JobListing.model_validate(values)


def test_normalize_job_listing_cleans_title_and_extracts_seniority() -> None:
    normalized = normalize_job_listing(_job())

    assert normalized.title == 'Senior ML Engineer'
    assert normalized.company == 'Example GmbH'
    assert normalized.url == 'https://example.com/jobs/1'
    assert normalized.location == 'Karlsruhe'
    assert normalized.minimum_years_experience == 5
    assert normalized.seniority == ['Senior']


def test_experience_range_uses_lower_bound() -> None:
    normalized = normalize_job_listing(_job(title='ML Engineer', requirements='Requires 4-8 years of experience.'))

    assert normalized.minimum_years_experience == 4
    assert normalized.seniority == ['Mid-level']


def test_audit_quarantines_short_and_blocked_content() -> None:
    short = normalize_job_listing(_job(description='Access denied', requirements=''))

    record = audit_job_listing('example', short)

    assert not record.accepted
    assert {issue.code for issue in record.issues} == {
        ExtractionIssueCode.CONTENT_TOO_SHORT,
        ExtractionIssueCode.BLOCK_OR_ERROR_PAGE,
    }


def test_audit_accepts_substantive_listing() -> None:
    record = audit_job_listing('example', normalize_job_listing(_job()))

    assert record.accepted
    assert record.issues == ()


def test_audit_rejects_mismatched_company_claim() -> None:
    job = _job(
        company='SignalAI',
        description='About Anthropic\n\n' + ('Substantive model-training work. ' * 20),
    )

    record = audit_job_listing('linkedin', job)

    assert record.accepted is False
    assert ExtractionIssueCode.COMPANY_CONTENT_MISMATCH in {issue.code for issue in record.issues}


def test_audit_accepts_matching_company_claim() -> None:
    job = _job(
        company='Mistral AI',
        description='About Mistral\n\n' + ('Substantive model-training work. ' * 20),
    )

    record = audit_job_listing('linkedin', normalize_job_listing(job))

    assert record.accepted is True


def test_extraction_audit_serializes_rejections(tmp_path) -> None:
    job = normalize_job_listing(_job())
    records = [audit_job_listing('example', job), duplicate_audit_record('example', job)]
    audit = build_extraction_audit(records)
    path = tmp_path / 'extraction_audit.json'

    write_extraction_audit(audit, path)

    assert audit.total == 2
    assert audit.accepted == 1
    assert audit.rejected == 1
    assert 'duplicate_url' in path.read_text(encoding='utf-8')


def test_stepstone_page_url_handles_queries_and_replaces_existing_page() -> None:
    assert _page_url('https://example.com/jobs?q=ml', 2) == 'https://example.com/jobs?q=ml&page=2'
    assert _page_url('https://example.com/jobs?page=1&q=ml', 3) == 'https://example.com/jobs?page=3&q=ml'
