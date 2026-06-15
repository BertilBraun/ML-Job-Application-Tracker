from __future__ import annotations

import re
import os
from dataclasses import dataclass

from google import genai
from google.genai import types
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .models import JobListing
from .resume_optimizer import _get_model_name, GEMINI_PROVIDER


MAX_MARKDOWN_CHARS = 45000


@dataclass(frozen=True)
class ImportedJobPage:
    url: str
    final_url: str
    title: str
    markdown: str


_EXTRACT_SYSTEM = """You convert rendered job-posting webpages into a structured job listing.

The input is Markdown converted from a fully rendered webpage. It may include navigation,
cookie text, footers, related jobs, or unrelated boilerplate.

Extract the actual job opening only. Return valid JSON matching the JobListing schema.

Rules:
- Do not invent details. Leave unknown fields empty, null, or [].
- Use the job posting URL as `url`.
- Use the best apply URL only if it is clearly present.
- Keep `description` as the substantive job description and responsibilities.
- Keep `requirements` as explicit requirements/qualifications.
- Put technologies/tools mentioned by the posting in `tech_stack`.
- Do not include site navigation, cookie banners, legal footer text, or lists of unrelated jobs.
"""


def fetch_job_page_markdown(url: str) -> ImportedJobPage:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            _settle_page(page)
            title = page.title()
            html = _rendered_html_with_frames(page)
            final_url = page.url
        finally:
            browser.close()

    markdown = _html_to_markdown(html)
    markdown = _clean_markdown(markdown)
    return ImportedJobPage(
        url=url,
        final_url=final_url,
        title=title.strip(),
        markdown=markdown[:MAX_MARKDOWN_CHARS],
    )


def parse_job_listing_from_markdown(page: ImportedJobPage) -> JobListing:
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    content = f"""<source_url>
{page.url}
</source_url>

<final_url>
{page.final_url}
</final_url>

<page_title>
{page.title}
</page_title>

<rendered_markdown>
{page.markdown}
</rendered_markdown>
"""
    response = client.models.generate_content(
        model=_get_model_name(GEMINI_PROVIDER),
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_EXTRACT_SYSTEM,
            response_mime_type='application/json',
            response_schema=JobListing,
        ),
    )
    if not response.text:
        raise ValueError('Empty job extraction response')
    job = JobListing.model_validate_json(response.text)
    if not job.url:
        job.url = page.final_url or page.url
    return job


def import_job_from_url(url: str) -> tuple[JobListing, ImportedJobPage]:
    clean_url = url.strip()
    if not re.match(r'^https?://', clean_url, flags=re.I):
        raise ValueError('URL must start with http:// or https://')
    page = fetch_job_page_markdown(clean_url)
    job = parse_job_listing_from_markdown(page)
    return job, page


def _settle_page(page: Page) -> None:
    try:
        page.wait_for_load_state('networkidle', timeout=10000)
    except PlaywrightTimeoutError:
        pass
    for fraction in (0.4, 0.8, 1.0):
        page.evaluate('(fraction) => window.scrollTo(0, document.body.scrollHeight * fraction)', fraction)
        page.wait_for_timeout(500)
    page.evaluate('window.scrollTo(0, 0)')
    page.wait_for_timeout(300)


def _rendered_html_with_frames(page: Page) -> str:
    chunks = [page.locator('body').evaluate('(body) => body.outerHTML')]
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame.wait_for_load_state('domcontentloaded', timeout=5000)
        except Exception:
            pass
        try:
            frame_html = frame.locator('body').evaluate('(body) => body.outerHTML', timeout=5000)
        except Exception:
            continue
        if frame_html.strip():
            chunks.append(f'<section data-source-frame="{frame.url}">{frame_html}</section>')
    return '\n'.join(chunks)


def _html_to_markdown(html: str) -> str:
    try:
        from html_to_markdown import convert_to_markdown

        return convert_to_markdown(html, heading_style='atx', bullets='-', wrap=True, wrap_width=100)
    except Exception:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript', 'svg']):
            tag.decompose()
        return soup.get_text('\n')


def _clean_markdown(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not blank:
                compact.append('')
            blank = True
            continue
        compact.append(stripped)
        blank = False
    return '\n'.join(compact).strip()
