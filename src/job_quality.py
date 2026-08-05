from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

try:
    from .models import JobListing
except ImportError:
    from models import JobListing


class ExtractionSeverity(str, Enum):
    WARNING = 'warning'
    ERROR = 'error'


class ExtractionIssueCode(str, Enum):
    INVALID_URL = 'invalid_url'
    MISSING_TITLE = 'missing_title'
    MISSING_COMPANY = 'missing_company'
    CONTENT_TOO_SHORT = 'content_too_short'
    BLOCK_OR_ERROR_PAGE = 'block_or_error_page'
    COMPANY_CONTENT_MISMATCH = 'company_content_mismatch'
    DUPLICATE_URL = 'duplicate_url'


class ExtractionIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ExtractionIssueCode
    severity: ExtractionSeverity
    detail: str


class ExtractionAuditRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    url: str
    title: str
    company: str
    accepted: bool
    issues: tuple[ExtractionIssue, ...]


class ExtractionAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    total: int
    accepted: int
    rejected: int
    records: tuple[ExtractionAuditRecord, ...]


_TITLE_SUFFIX_PATTERN = re.compile(
    r'\s*\((?:verified job|verifizierte stellenanzeige)\)\s*$',
    re.IGNORECASE,
)
_EXPERIENCE_PATTERN = re.compile(
    r'(?P<minimum>\d{1,2})(?:\s*[-–—]\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?|jahre[n]?)\b',
    re.IGNORECASE,
)
_BLOCK_PAGE_PATTERN = re.compile(
    r'\b(?:access denied|security check|captcha|page not found|job (?:is )?no longer available|sign in to view this job)\b',
    re.IGNORECASE,
)
_ABOUT_COMPANY_PATTERN = re.compile(
    r'\A\s*about\s+(?P<company>[^\r\n]{2,80})\s*(?:\r?\n|$)',
    re.IGNORECASE,
)
_GENERIC_ABOUT_LABELS = {'company', 'our company', 'the company', 'the role', 'the team', 'this role', 'us'}
_SENIORITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ('Director', re.compile(r'\bdirector\b', re.IGNORECASE)),
    ('Head', re.compile(r'\bhead\b', re.IGNORECASE)),
    ('Principal', re.compile(r'\bprincipal\b', re.IGNORECASE)),
    ('Staff', re.compile(r'\bstaff\b', re.IGNORECASE)),
    ('Lead', re.compile(r'\blead\b', re.IGNORECASE)),
    ('Expert', re.compile(r'\bexpert\b', re.IGNORECASE)),
    ('Senior', re.compile(r'\bsenior\b', re.IGNORECASE)),
    ('Mid-level', re.compile(r'\bmid(?:-level)?\b', re.IGNORECASE)),
    ('Junior', re.compile(r'\bjunior\b', re.IGNORECASE)),
)


def extract_minimum_years_experience(job: JobListing) -> int | None:
    text = '\n'.join((job.title, job.description, job.requirements))
    minimums = [int(match.group('minimum')) for match in _EXPERIENCE_PATTERN.finditer(text)]
    return max(minimums) if minimums else None


def infer_seniority(job: JobListing, minimum_years_experience: int | None) -> list[str]:
    evidence = ' '.join((job.title, *job.seniority))
    inferred = [label for label, pattern in _SENIORITY_PATTERNS if pattern.search(evidence)]
    if inferred:
        return inferred
    if minimum_years_experience is None:
        return []
    if minimum_years_experience >= 5:
        return ['Senior']
    if minimum_years_experience >= 3:
        return ['Mid-level']
    return ['Junior']


def normalize_job_listing(job: JobListing) -> JobListing:
    minimum_years_experience = extract_minimum_years_experience(job)
    return job.model_copy(
        update={
            'title': _TITLE_SUFFIX_PATTERN.sub('', job.title).strip(),
            'company': job.company.strip(),
            'url': job.url.strip(),
            'location': job.location.strip(),
            'summary': job.summary.strip(),
            'description': job.description.strip(),
            'requirements': job.requirements.strip(),
            'seniority': infer_seniority(job, minimum_years_experience),
            'minimum_years_experience': minimum_years_experience,
        }
    )


def _normalized_company_name(value: str) -> str:
    return ''.join(character for character in value.casefold() if character.isalnum())


def _claimed_company(description: str) -> str | None:
    match = _ABOUT_COMPANY_PATTERN.match(description)
    if match is None:
        return None
    claimed_company = match.group('company').strip(' .:-')
    if claimed_company.casefold() in _GENERIC_ABOUT_LABELS:
        return None
    return claimed_company


def _company_matches_claim(listing_company: str, claimed_company: str) -> bool:
    normalized_listing = _normalized_company_name(listing_company)
    normalized_claim = _normalized_company_name(claimed_company)
    return normalized_listing in normalized_claim or normalized_claim in normalized_listing


def audit_job_listing(source: str, job: JobListing) -> ExtractionAuditRecord:
    issues: list[ExtractionIssue] = []
    if not re.match(r'^https?://', job.url, flags=re.IGNORECASE):
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.INVALID_URL,
                severity=ExtractionSeverity.ERROR,
                detail='Listing URL is not an absolute HTTP(S) URL.',
            )
        )
    if not job.title:
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.MISSING_TITLE,
                severity=ExtractionSeverity.ERROR,
                detail='Job title is empty.',
            )
        )
    if not job.company:
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.MISSING_COMPANY,
                severity=ExtractionSeverity.ERROR,
                detail='Company is empty.',
            )
        )

    substantive_content = '\n'.join((job.summary, job.description, job.requirements)).strip()
    if len(substantive_content) < 300:
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.CONTENT_TOO_SHORT,
                severity=ExtractionSeverity.ERROR,
                detail=f'Only {len(substantive_content)} characters of substantive content were extracted.',
            )
        )
    if _BLOCK_PAGE_PATTERN.search(substantive_content):
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.BLOCK_OR_ERROR_PAGE,
                severity=ExtractionSeverity.ERROR,
                detail='Extracted content contains a block-page, authentication, or unavailable-job marker.',
            )
        )

    claimed_company = _claimed_company(job.description)
    if claimed_company is not None and not _company_matches_claim(job.company, claimed_company):
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.COMPANY_CONTENT_MISMATCH,
                severity=ExtractionSeverity.ERROR,
                detail=(
                    f'The description opens with "About {claimed_company}", which does not match '
                    f'the extracted company "{job.company}".'
                ),
            )
        )

    issue_tuple = tuple(issues)
    return ExtractionAuditRecord(
        source=source,
        url=job.url,
        title=job.title,
        company=job.company,
        accepted=not any(issue.severity is ExtractionSeverity.ERROR for issue in issue_tuple),
        issues=issue_tuple,
    )


def duplicate_audit_record(source: str, job: JobListing) -> ExtractionAuditRecord:
    return ExtractionAuditRecord(
        source=source,
        url=job.url,
        title=job.title,
        company=job.company,
        accepted=False,
        issues=(
            ExtractionIssue(
                code=ExtractionIssueCode.DUPLICATE_URL,
                severity=ExtractionSeverity.ERROR,
                detail='The same canonical listing URL was already collected in this run.',
            ),
        ),
    )


def build_extraction_audit(records: list[ExtractionAuditRecord]) -> ExtractionAudit:
    accepted = sum(record.accepted for record in records)
    return ExtractionAudit(
        generated_at=datetime.now(timezone.utc),
        total=len(records),
        accepted=accepted,
        rejected=len(records) - accepted,
        records=tuple(records),
    )


def write_extraction_audit(audit: ExtractionAudit, path: Path) -> None:
    path.write_text(audit.model_dump_json(indent=2), encoding='utf-8')
