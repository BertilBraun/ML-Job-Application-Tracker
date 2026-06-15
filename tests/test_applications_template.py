from __future__ import annotations

from pathlib import Path


def test_applications_template_exposes_tailored_cv_download_button():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'Download PDFs' in template
    assert 'downloadPdfs' in template
    assert 'downloadTailoredCv' in template
    assert "/api/applications/${id}/cv.pdf" in template
    assert "/api/applications/${id}/cover-letter.pdf" in template


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


def test_applications_template_exposes_job_url_import():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'Paste job URL to import and track' in template
    assert 'importJobUrl' in template
    assert '/api/applications/import-url' in template
    assert 'import-status-list' in template
    assert 'input.value = \'\'' in template


def test_applications_template_shows_material_generation_status():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'materials_status' in template
    assert 'Generating materials...' in template
    assert 'materials-status' not in template
    assert 'setMaterialsStatus' in template
    assert 'pollMaterialGeneration' in template
    assert 'syncGeneratedMaterials' in template
