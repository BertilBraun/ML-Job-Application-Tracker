from __future__ import annotations

import pytest
from src import analyzer
from src.models import JobListing


def test_analyzer_separates_technical_match_from_cv_screening(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analyzer, '_system_prompt', None)

    prompt = analyzer._build_system_prompt()

    assert '<candidate_resume>' in prompt
    assert '<candidate_evidence>' in prompt
    assert 'TECHNICAL MATCH' in prompt
    assert 'CURRENT CV SCREENING FIT' in prompt
    assert 'Do not call those equivalent' in prompt
    assert 'Do not return a recommendation' in prompt
    assert 'substantial remote time' in prompt
    assert 'A hybrid label alone is not enough' in prompt


def test_analysis_cache_is_model_specific() -> None:
    job = JobListing(title='ML Engineer', company='Example', url='https://example.com/job')

    flash_lite = analyzer._analysis_cache_path(job, 'prompt', 'gemini-3.5-flash-lite')
    flash = analyzer._analysis_cache_path(job, 'prompt', 'gemini-3.8-flash')

    assert flash_lite != flash
