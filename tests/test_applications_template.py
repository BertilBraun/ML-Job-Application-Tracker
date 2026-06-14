from __future__ import annotations

from pathlib import Path


def test_applications_template_exposes_tailored_cv_download_button():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'Download tailored CV PDF' in template
    assert 'downloadTailoredCv' in template
    assert "/api/applications/${id}/cv.pdf" in template


def test_applications_template_auto_expands_open_query_card():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert "new URLSearchParams(window.location.search).get('open')" in template
    assert 'openApplicationFromQuery' in template
    assert 'getComputedStyle(body).display' in template


def test_applications_template_highlights_possible_duplicate_drafts():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'possible-duplicate' in template
    assert 'Possible duplicate' in template
    assert "a.status === 'draft'" in template


def test_applications_template_shows_tailored_cv_metadata():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'Tailored technical skills' in template
    assert 'Project order' in template
    assert 'parseCvList(a.technical_skills)' in template
    assert 'parseCvList(a.project_order)' in template
    assert 'updateMetadataList(`skills-${id}`, data.technical_skills' in template
    assert 'updateMetadataList(`projects-${id}`, data.project_order' in template
