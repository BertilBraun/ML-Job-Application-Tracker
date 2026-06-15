from __future__ import annotations

from src.build_ui import build


def _entry() -> dict:
    return {
        'job': {
            'title': 'ML Engineer',
            'company': 'Example GmbH',
            'url': 'https://example.com/job',
            'apply_url': 'https://example.com/apply',
            'location': 'Karlsruhe',
            'salary': '',
            'company_size': '',
            'date_added': '',
            'industries': [],
            'seniority': [],
        },
        'analysis': {
            'overall_score': 8,
            'recommendation': 'apply',
            'job_summary': 'Build ML systems.',
            'team_assessment': {'score': 8, 'reasoning': 'Good team.'},
            'work_impact': {'score': 8, 'reasoning': 'Good work.'},
            'location_fit': {'score': 8, 'works': True, 'reasoning': 'Works.'},
            'candidate_fit': {'score': 8, 'reasoning': 'Good fit.', 'strengths': [], 'gaps': []},
            'salary_note': '',
            'key_concerns': [],
        },
    }


def test_results_tracker_link_opens_created_application_in_new_tab():
    html = build([_entry()])

    assert 'target="_blank"' in html
    assert 'openTrackerForCurrentApplication' in html
    assert "window.open(`/applications?open=${_currentAppId}`, '_blank')" in html
    assert "btn.onclick = () => openTrackerForApplication(appId)" in html


def test_results_track_starts_background_generation_without_modal():
    html = build([_entry()])

    assert 'generate-background' in html
    assert "btn.textContent = 'Tracking...'" in html
    assert "_markTracked(_currentJobUrl, _currentAppId, 'generating')" in html
    assert "a.materials_status || ''" in html
    assert "Generating..." in html
    assert "document.getElementById('apply-modal').style.display = 'flex';" not in html
