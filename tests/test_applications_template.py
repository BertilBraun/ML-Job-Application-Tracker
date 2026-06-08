from __future__ import annotations

from pathlib import Path


def test_applications_template_exposes_tailored_cv_download_button():
    template = Path('templates/applications.html').read_text(encoding='utf-8')

    assert 'Download tailored CV PDF' in template
    assert 'downloadTailoredCv' in template
    assert "/api/applications/${id}/cv.pdf" in template
