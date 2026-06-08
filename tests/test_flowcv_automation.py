from __future__ import annotations

import pytest

from src.flowcv_automation import validate_about_text


PLAUSIBLE_ABOUT = (
    "AI engineer with a research background, building end-to-end ML systems across "
    "reinforcement learning, computer vision, and LLM pipelines. MSc from KIT with "
    "an AI specialization, completed in half the standard time, and 3+ years of "
    "industry experience across startups and large organizations including "
    "Mercedes-Benz. I like hard problems, especially systems that connect modeling, "
    "data pipelines, evaluation, and production deployment. Seeking applied ML or "
    "research engineering roles with experienced teams and challenging problems."
)


def test_validate_about_text_rejects_empty():
    with pytest.raises(ValueError, match='has not been generated'):
        validate_about_text('   ')


def test_validate_about_text_rejects_too_short():
    with pytest.raises(ValueError, match='too short'):
        validate_about_text('AI engineer.')


def test_validate_about_text_rejects_markdown_or_bullets():
    with pytest.raises(ValueError, match='must be prose'):
        validate_about_text('- ' + PLAUSIBLE_ABOUT)


def test_validate_about_text_accepts_plausible_prose():
    assert validate_about_text(PLAUSIBLE_ABOUT) == PLAUSIBLE_ABOUT
