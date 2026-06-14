from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

FLOWCV_URL = 'https://app.flowcv.com/resume/content'
USER_DATA_DIR = Path('user_data') / 'flowcv'
DOWNLOAD_DIR = Path('downloads') / 'cv'
ORIGINAL_ABOUT_LENGTH = 758

# Headless by default; set FLOWCV_HEADLESS=false for the one-off visible re-login when the session expires.
HEADLESS = os.environ.get('FLOWCV_HEADLESS', 'true').lower() != 'false'


class FlowCVError(RuntimeError):
    pass


class FlowCVLoginRequired(FlowCVError):
    pass


def validate_about_text(text: str) -> str:
    clean = text.strip()
    if not clean:
        raise ValueError('Tailored About has not been generated yet')
    if len(clean) < 300:
        raise ValueError('Tailored About is too short for the CV About section')
    if len(clean) > 1200:
        raise ValueError('Tailored About is too long for the CV About section')

    lower = int(ORIGINAL_ABOUT_LENGTH * 0.75)
    upper = int(ORIGINAL_ABOUT_LENGTH * 1.35)
    if not (lower <= len(clean) <= upper):
        raise ValueError(
            f'Tailored About length must stay close to the original ({lower}-{upper} characters)'
        )
    if clean.startswith(('#', '-', '*')):
        raise ValueError('Tailored About must be prose, not markdown or bullets')
    return clean


def validate_technical_skills(skills: Iterable[str] | None) -> list[str]:
    if skills is None:
        return []
    lines = [str(line).strip() for line in skills if str(line).strip()]
    if not lines:
        return []
    if not (2 <= len(lines) <= 5):
        raise ValueError('Technical skills must contain 2-5 non-empty lines')
    for line in lines:
        if '|' in line:
            raise ValueError('Technical skills must not contain markdown tables')
        if len(line) > 180:
            raise ValueError('Technical skills lines must stay compact')
    return lines


def validate_project_order(project_order: Iterable[str] | None) -> list[str]:
    if project_order is None:
        return []
    names = [str(name).strip() for name in project_order if str(name).strip()]
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        key = _normalize_match_text(name)
        if key and key not in seen:
            seen.add(key)
            deduped.append(name)
    return deduped


def replace_about_and_download_cv(about_text: str, target_path: Path) -> Path:
    return replace_cv_content_and_download(
        about_text=about_text,
        technical_skills=None,
        project_order=None,
        target_path=target_path,
    )


def replace_cv_content_and_download(
    *,
    about_text: str,
    technical_skills: Iterable[str] | None = None,
    project_order: Iterable[str] | None = None,
    target_path: Path,
) -> Path:
    clean_about = validate_about_text(about_text)
    clean_skills = validate_technical_skills(technical_skills)
    clean_project_order = validate_project_order(project_order)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    steps = [
        ('open page', lambda: page.goto(FLOWCV_URL, wait_until='domcontentloaded')),
        ('wait for content page', lambda: _wait_for_flowcv_content_page(page)),
        ('open about editor', lambda: _open_about_editor(page)),
        ('replace professional summary', lambda: _replace_professional_summary(page, clean_about)),
        ('confirm about preview', lambda: _confirm_about_preview(page, clean_about)),
    ]
    if clean_skills:
        steps.extend(
            [
                ('replace technical skills', lambda: _replace_technical_skills(page, clean_skills)),
                ('confirm technical skills', lambda: _confirm_technical_skills(page, clean_skills)),
            ]
        )
    if clean_project_order:
        steps.extend(
            [
                ('reorder projects', lambda: _reorder_projects(page, clean_project_order)),
                ('confirm project order', lambda: _confirm_project_order(page, clean_project_order)),
            ]
        )
    steps.append(('download pdf', lambda: _download_pdf(page, target_path)))

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=HEADLESS,
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)

        current_step = 'launch'
        try:
            for current_step, action in steps:
                action()
            return target_path
        except FlowCVLoginRequired:
            raise
        except Exception as exc:
            kind = 'timed out' if isinstance(exc, PlaywrightTimeoutError) else 'failed'
            raise FlowCVError(f'FlowCV automation {kind} at step "{current_step}": {exc}') from exc
        finally:
            context.close()


def _wait_for_flowcv_content_page(page: Page) -> None:
    try:
        page.wait_for_url('**/resume/content**', timeout=60000)
    except PlaywrightTimeoutError as exc:
        raise FlowCVLoginRequired(
            'FlowCV session is not logged in. Log in once in the opened browser window.'
        ) from exc

    try:
        _about_nav_item(page).wait_for(timeout=60000)
    except PlaywrightTimeoutError as exc:
        raise FlowCVLoginRequired(
            'FlowCV content page did not become available after login.'
        ) from exc


def _about_nav_item(page: Page) -> Locator:
    return page.get_by_text('About', exact=True).first


def _open_about_editor(page: Page) -> None:
    _about_nav_item(page).click()

    preview = (
        page.locator('.previewHtmlContent')
        .filter(has_text=re.compile('AI engineer|research background|hard problems', re.I))
        .first
    )
    if _is_visible(preview, timeout=3000):
        preview.click()
    else:
        page.locator('.previewHtmlContent').first.click()

    editor = page.locator('[data-name="rich-text-editor"][contenteditable="true"]').first
    if _is_visible(editor, timeout=2000):
        return

    edit_button = page.get_by_role('button', name=re.compile('edit', re.I)).first
    if _is_visible(edit_button, timeout=5000):
        edit_button.click()


def _replace_professional_summary(page: Page, about_text: str) -> None:
    editor = page.locator('[data-name="rich-text-editor"][contenteditable="true"]').first
    if not _is_visible(editor, timeout=10000):
        editor = page.locator('.ProseMirror[contenteditable="true"]').first

    editor.click()
    page.keyboard.press('Control+A')
    page.keyboard.press('Delete')

    paragraphs = [paragraph for paragraph in about_text.split('\n') if paragraph.strip()]
    for index, paragraph in enumerate(paragraphs):
        if index:
            page.keyboard.press('Enter')
        page.keyboard.insert_text(paragraph)

    page.get_by_role('button', name=re.compile('^done$', re.I)).first.click()


def _confirm_about_preview(page: Page, about_text: str) -> None:
    probe = about_text[:80]
    page.locator('.previewHtmlContent').filter(has_text=probe).first.wait_for(timeout=15000)


def _replace_technical_skills(page: Page, skills: list[str]) -> None:
    _open_droppable_section(page, 'droppable-certificate', ('Skills', 'Technical Skills', 'Certificates'))
    rows = _draggable_rows(page, 'droppable-certificate')
    row_count = rows.count()
    if row_count < len(skills):
        raise FlowCVError(
            f'FlowCV technical skills section has {row_count} rows, cannot write {len(skills)} lines'
        )

    for index, line in enumerate(skills):
        title, content = _split_skill_line(line)
        row = rows.nth(index)
        _open_row_editor(page, row)
        _replace_skill_editor_fields(page, title, content)

    for index in range(len(skills), row_count):
        _hide_row_if_visible(rows.nth(index))


def _confirm_technical_skills(page: Page, skills: list[str]) -> None:
    preview = page.locator('#certificate-container').first
    preview.wait_for(state='visible', timeout=15000)
    section_text = preview.inner_text(timeout=15000)
    for line in skills:
        title, content = _split_skill_line(line)
        if title not in section_text:
            raise FlowCVError(f'Could not verify FlowCV skill title: {title}')
        if content and content.split(',')[0].strip() not in section_text:
            raise FlowCVError(f'Could not verify FlowCV skill content for: {title}')


def _reorder_projects(page: Page, requested_order: list[str]) -> None:
    _open_droppable_section(page, 'droppable-project', ('Projects',))
    current = _current_project_rows(page)
    matched = [name for name in requested_order if _find_project_index(current, name) is not None]
    unknown = [name for name in requested_order if name not in matched]
    if unknown:
        print(f'FlowCV project reorder warning: unknown project names ignored: {unknown}')
    if not matched:
        raise FlowCVError('None of the requested project_order names matched FlowCV project rows')

    for target_index, desired_name in enumerate(matched):
        current = _current_project_rows(page)
        source_index = _find_project_index(current, desired_name)
        if source_index is None:
            continue
        if source_index == target_index:
            continue
        if not _keyboard_reorder_project(page, source_index, target_index):
            _drag_reorder_project(page, source_index, target_index)


def _confirm_project_order(page: Page, requested_order: list[str]) -> None:
    _open_droppable_section(page, 'droppable-project', ('Projects',))
    current = _current_project_rows(page)
    matched = [name for name in requested_order if _find_project_index(current, name) is not None]
    if not matched:
        raise FlowCVError('None of the requested project_order names matched FlowCV project rows')

    visible_order = [_normalize_match_text(title) for title in current]
    expected_prefix = [_normalize_match_text(title) for title in matched]
    if visible_order[: len(expected_prefix)] != expected_prefix:
        raise FlowCVError(
            'Project reorder verification failed. '
            f'Expected prefix {matched}, got {current[:len(matched)]}'
        )


def _download_pdf(page: Page, target_path: Path) -> None:
    download_button = page.get_by_role('button', name=re.compile('download', re.I)).first
    with page.expect_download(timeout=60000) as download_info:
        download_button.click()
    download = download_info.value
    download.save_as(str(target_path))


def _is_visible(locator: Locator, timeout: int) -> bool:
    try:
        locator.wait_for(state='visible', timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


def _receives_pointer_events(locator: Locator) -> bool:
    try:
        return bool(
            locator.evaluate(
                """element => {
                    const rect = element.getBoundingClientRect();
                    if (!rect.width || !rect.height) return false;
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const top = document.elementFromPoint(x, y);
                    return !!top && (top === element || element.contains(top));
                }"""
            )
        )
    except Exception:
        return False


def _wait_until_receives_pointer_events(page: Page, locator: Locator, timeout_ms: int = 5000) -> bool:
    deadline = timeout_ms / 100
    for _ in range(int(deadline)):
        if _receives_pointer_events(locator):
            return True
        page.wait_for_timeout(100)
    return False


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower()
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def _split_skill_line(line: str) -> tuple[str, str]:
    if ':' not in line:
        return line.strip(), ''
    title, content = line.split(':', 1)
    return title.strip(), content.strip()


def _droppable(page: Page, droppable_id: str) -> Locator:
    return page.locator(f'[data-rbd-droppable-id="{droppable_id}"]').first


def _draggable_rows(page: Page, droppable_id: str) -> Locator:
    return _droppable(page, droppable_id).locator('[data-rbd-draggable-id]')


def _open_droppable_section(page: Page, droppable_id: str, headings: tuple[str, ...]) -> None:
    section = _droppable(page, droppable_id)
    rows = _draggable_rows(page, droppable_id)
    if rows.count() > 0 and _is_visible(rows.first, timeout=2000) and _receives_pointer_events(rows.first):
        return

    for heading in headings:
        candidate = page.get_by_text(heading, exact=True).first
        if _is_visible(candidate, timeout=1000):
            candidate.evaluate('(element) => element.scrollIntoView({block: "center", inline: "nearest"})')
            page.wait_for_timeout(100)
            candidate.click()
            if (
                rows.count() > 0
                and _is_visible(rows.first, timeout=5000)
                and _wait_until_receives_pointer_events(page, rows.first)
            ):
                return

    section.wait_for(state='attached', timeout=15000)
    if rows.count() == 0:
        raise FlowCVError(f'FlowCV section {droppable_id} has no draggable rows')
    rows.first.wait_for(state='visible', timeout=15000)
    if not _wait_until_receives_pointer_events(page, rows.first):
        raise FlowCVError(f'FlowCV section {droppable_id} is present but still covered/collapsed')


def _open_row_editor(page: Page, row: Locator) -> None:
    row.evaluate('(element) => element.scrollIntoView({block: "center", inline: "nearest"})')
    page.wait_for_timeout(150)
    click_target = row.locator('.relative.min-w-0').first
    target = click_target if _is_visible(click_target, timeout=1000) else row

    try:
        target.click(timeout=3000)
    except PlaywrightTimeoutError:
        try:
            target.click(force=True, timeout=3000)
        except PlaywrightTimeoutError:
            row.focus()
            page.keyboard.press('Enter')

    done = page.get_by_role('button', name=re.compile(r'^(done|save)$', re.I)).first
    fields = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]')
    try:
        done.wait_for(state='visible', timeout=5000)
    except PlaywrightTimeoutError:
        fields.first.wait_for(state='visible', timeout=5000)


def _replace_skill_editor_fields(page: Page, title: str, content: str) -> None:
    fields = _skill_editor_fields(page)
    if len(fields) < 2:
        raise FlowCVError('Could not find editable title/content fields for FlowCV skill row')

    _replace_field_text(page, fields[0], title)
    _replace_field_text(page, fields[1], content)
    done = page.get_by_role('button', name=re.compile(r'^(done|save)$', re.I)).first
    if not _is_visible(done, timeout=5000):
        raise FlowCVError('Could not find Done/Save button after editing FlowCV skill row')
    done.click()


def _skill_editor_fields(page: Page) -> list[Locator]:
    labeled_fields = [
        page.get_by_label(re.compile(r'^(word|title|name)$', re.I)).first,
        page.get_by_label(re.compile(r'^(info|description|content)$', re.I)).first,
    ]
    if all(_is_visible(field, timeout=500) for field in labeled_fields):
        return labeled_fields

    return _visible_editor_fields(page)


def _visible_editor_fields(page: Page) -> list[Locator]:
    fields = page.locator(
        'input:not([type="hidden"]), textarea, [contenteditable="true"]'
    )
    visible: list[Locator] = []
    for index in range(fields.count()):
        field = fields.nth(index)
        if _is_visible(field, timeout=250):
            visible.append(field)
    return visible


def _replace_field_text(page: Page, field: Locator, value: str) -> None:
    field.click()
    page.keyboard.press('Control+A')
    page.keyboard.press('Delete')
    page.keyboard.insert_text(value)


def _hide_row_if_visible(row: Locator) -> None:
    if 'opacity-50' in (row.get_attribute('class') or ''):
        return
    visibility_button = row.locator('button').last
    if _is_visible(visibility_button, timeout=1000):
        visibility_button.click(force=True)


def _current_project_rows(page: Page) -> list[str]:
    rows = _draggable_rows(page, 'droppable-project')
    titles: list[str] = []
    for index in range(rows.count()):
        titles.append(_project_title_from_row(rows.nth(index)))
    return titles


def _project_title_from_row(row: Locator) -> str:
    bold_title = row.locator('.font-bold').first
    if _is_visible(bold_title, timeout=250):
        title = bold_title.inner_text(timeout=1000).strip()
        if title:
            return title

    text = row.inner_text(timeout=5000)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text.strip())
    if ' , ' in first_line:
        first_line = first_line.split(' , ', 1)[0]
    elif ',' in first_line:
        first_line = first_line.split(',', 1)[0]
    return first_line.strip()


def _find_project_index(current_order: list[str], requested_name: str) -> int | None:
    requested = _normalize_project_name(requested_name)
    for index, current_name in enumerate(current_order):
        current = _normalize_project_name(current_name)
        if _project_names_match(current, requested):
            return index
    return None


def _normalize_project_name(value: str) -> str:
    normalized = _normalize_match_text(value)
    return re.sub(r'^complete gpu resident ', 'gpu resident ', normalized)


def _project_names_match(current: str, requested: str) -> bool:
    if not current or not requested:
        return False
    return (
        current == requested
        or current.startswith(f'{requested} ')
        or requested.startswith(f'{current} ')
    )


def _keyboard_reorder_project(page: Page, source_index: int, target_index: int) -> bool:
    rows = _draggable_rows(page, 'droppable-project')
    row = rows.nth(source_index)
    try:
        row.focus()
        page.keyboard.press('Space')
        key = 'ArrowUp' if target_index < source_index else 'ArrowDown'
        for _ in range(abs(source_index - target_index)):
            page.keyboard.press(key)
        page.keyboard.press('Space')
        page.wait_for_timeout(500)
        return True
    except Exception:
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return False


def _drag_reorder_project(page: Page, source_index: int, target_index: int) -> None:
    rows = _draggable_rows(page, 'droppable-project')
    source = rows.nth(source_index)
    target = rows.nth(target_index)
    source.drag_to(target)
    page.wait_for_timeout(500)
