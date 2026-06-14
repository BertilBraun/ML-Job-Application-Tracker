from __future__ import annotations

import pytest

from src.flowcv_automation import (
    _find_project_index,
    validate_about_text,
    validate_project_order,
    validate_technical_skills,
)


PLAUSIBLE_ABOUT = (
    'AI engineer with a research background, building end-to-end ML systems across '
    'reinforcement learning, computer vision, and LLM pipelines. MSc from KIT with '
    'an AI specialization, completed in half the standard time, and 3+ years of '
    'industry experience across startups and large organizations including '
    'Mercedes-Benz. I like hard problems. Whether that means designing a distributed '
    'self-play training system, building a multi-object tracking pipeline for video '
    'analysis, or developing automated LLM evaluation frameworks, I work across the '
    'full stack from research and algorithm design through to production deployment. '
    'Seeking applied ML or research engineering roles with experienced teams and '
    'challenging problems.'
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


def test_validate_technical_skills_accepts_compact_grouped_lines():
    skills = [
        'Programming: Python, C++',
        'ML systems: PyTorch, JAX',
        'Deployment: Docker, FastAPI',
    ]

    assert validate_technical_skills(skills) == skills


def test_validate_technical_skills_rejects_markdown_tables():
    with pytest.raises(ValueError, match='markdown tables'):
        validate_technical_skills(['Programming | Python', 'ML: PyTorch'])


def test_validate_project_order_deduplicates_names():
    assert validate_project_order(['GybeLock', ' GybeLock ', 'Agentic LLM Systems']) == [
        'GybeLock',
        'Agentic LLM Systems',
    ]


def test_project_matching_accepts_flowcv_titles_with_subtitles_and_dash_variants():
    current_order = [
        (
            'Agentic LLM Systems: Durable Coding Runtime & Multi-Agent Orchestration, '
            'Agentic AI systems combining resumable workflows.'
        ),
        (
            'GybeLock – Multi-Object Tracking & Video Intelligence System, '
            'Computer vision system for detecting and tracking windsurfers.'
        ),
        'GPU-Resident Reinforcement Learning with JAX',
        'GNN-Based Traffic Signal Control, Graph RL project for SUMO traffic control.',
    ]

    assert _find_project_index(
        current_order,
        'Agentic LLM Systems: Durable Coding Runtime & Multi-Agent Orchestration',
    ) == 0
    assert _find_project_index(
        current_order,
        'GybeLock - Multi-Object Tracking & Video Intelligence System',
    ) == 1
    assert _find_project_index(
        current_order,
        'Complete GPU-Resident Reinforcement Learning with JAX',
    ) == 2
    assert _find_project_index(current_order, 'GNN-Based Traffic Signal Control') == 3
