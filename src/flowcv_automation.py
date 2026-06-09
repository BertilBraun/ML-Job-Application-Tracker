from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

FLOWCV_URL = 'https://app.flowcv.com/resume/content'
USER_DATA_DIR = Path('user_data') / 'flowcv'
DOWNLOAD_DIR = Path('downloads') / 'cv'
ORIGINAL_ABOUT_LENGTH = 728

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
    if len(clean) > 900:
        raise ValueError('Tailored About is too long for the CV About section')

    lower = int(ORIGINAL_ABOUT_LENGTH * 0.75)
    upper = int(ORIGINAL_ABOUT_LENGTH * 1.35)
    if not (lower <= len(clean) <= upper):
        raise ValueError(f'Tailored About length must stay close to the original ({lower}-{upper} characters)')
    if clean.startswith(('#', '-', '*')):
        raise ValueError('Tailored About must be prose, not markdown or bullets')
    return clean


def replace_about_and_download_cv(about_text: str, target_path: Path) -> Path:
    clean_about = validate_about_text(about_text)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    steps = (
        ('open page', lambda: page.goto(FLOWCV_URL, wait_until='domcontentloaded')),
        ('wait for content page', lambda: _wait_for_flowcv_content_page(page)),
        ('open about editor', lambda: _open_about_editor(page)),
        ('replace professional summary', lambda: _replace_professional_summary(page, clean_about)),
        ('confirm about preview', lambda: _confirm_about_preview(page, clean_about)),
        ('download pdf', lambda: _download_pdf(page, target_path)),
    )

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
        raise FlowCVLoginRequired('FlowCV session is not logged in. Log in once in the opened browser window.') from exc

    try:
        _about_nav_item(page).wait_for(timeout=60000)
    except PlaywrightTimeoutError as exc:
        raise FlowCVLoginRequired('FlowCV content page did not become available after login.') from exc


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
