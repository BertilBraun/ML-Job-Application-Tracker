from __future__ import annotations

import src.resume_optimizer as resume_optimizer


def test_resume_cache_key_includes_generation_guidance(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_optimizer, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(resume_optimizer, '_get_resume', lambda: 'resume text')

    no_guidance = resume_optimizer._cache_path('https://example.com/job', '')
    with_guidance = resume_optimizer._cache_path(
        'https://example.com/job',
        'Emphasize AlphaZero self-play and adversarial learning.',
    )

    assert no_guidance != with_guidance
    assert no_guidance.parent == tmp_path
    assert with_guidance.parent == tmp_path
