import os
from dotenv import load_dotenv
from models import JobListing
from scrapers.base import load_detail_cache, save_detail_cache, pause_if_suspicious
from scrapers.browser import get_context, human_delay, wait_if_blocked

load_dotenv()

SEARCH_URL = os.environ.get('LINKEDIN_SEARCH_URL', '')
if not SEARCH_URL:
    raise ValueError('LINKEDIN_SEARCH_URL not set in .env — see .env.example')
BLOCK = [
    'div.challenge-dialog',
    '#captcha-internal',
    "h1:has-text('security check')",
    "h1:has-text('Let\\'s do a quick')",
]

# Extract title, company, location, salary from a card.
# LinkedIn renders the title twice: the visible text in span[aria-hidden="true"] and a
# screen-reader copy (suffixed e.g. "(Verified job)") in a sibling span. Read the aria-hidden
# span — the sibling is often empty or contaminated with that suffix.
# Company and location are the two <p> tags immediately following the title; the salary, when
# present, is a later <p> badge — read it from the card (job-accurate) rather than the shared
# detail pane, where a page-wide scan can pick another card's salary or UI noise.
_CARD_TEXTS_JS = r"""el => {
    const paras = Array.from(el.querySelectorAll('p'))
        .filter(p => !p.closest('button'));

    const titleIdx = paras.findIndex(p => p.querySelector('span[aria-hidden="true"]'));
    if (titleIdx === -1) return [];

    const titlePara = paras[titleIdx];
    const ariaHidden = titlePara.querySelector('span[aria-hidden="true"]');
    const title = (ariaHidden || titlePara).textContent.trim();

    const after = paras.slice(titleIdx + 1);
    const company  = after[0]?.textContent.trim() || '';
    const location = after[1]?.textContent.trim() || '';

    // Scan only the metadata paras after location — titles like "... | Upto $90/hr" otherwise false-match.
    const salaryRe = /(?=.*\d)(?=.*(?:€|\$|£|EUR|USD|GBP|CHF))(?=.*(?:\/?yr|\/?mo|\/?hr|year|month|Jahr|Monat))/i;
    const salaryPara = after.slice(2).find(p => salaryRe.test(p.textContent));
    const salary = salaryPara ? salaryPara.textContent.trim() : '';

    return [title, company, location, salary];
}"""


def _ensure_logged_in(page) -> None:
    page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded')
    if 'login' in page.url or 'authwall' in page.url:
        print('\nLinkedIn session expired. Log in manually in the browser, then press Enter...')
        input()


def scrape_jobs(search_url: str = SEARCH_URL, max_pages: int = 2) -> list[JobListing]:
    pw, ctx = get_context()
    page = ctx.new_page()
    jobs: list[JobListing] = []
    seen: set[str] = set()

    try:
        _ensure_logged_in(page)
        page.goto(search_url, wait_until='domcontentloaded')
        wait_if_blocked(page, BLOCK)
        human_delay(3, 6)

        for pg in range(1, max_pages + 1):
            try:
                page.wait_for_selector('[componentkey^="job-card-component-ref-"][tabindex="0"]', timeout=10000)
            except Exception:
                print(f'  !! No cards found on page {pg}')
                break
            human_delay(1, 2)

            cards = page.locator('[componentkey^="job-card-component-ref-"][tabindex="0"]').all()
            print(f'  Found {len(cards)} cards on page {pg}')

            # (job_id, url, title, company, location, salary)
            card_meta: list[tuple[str, str, str, str, str, str]] = []
            for card in cards:
                try:
                    componentkey = card.get_attribute('componentkey') or ''
                    job_id = componentkey.removeprefix('job-card-component-ref-')
                    if not job_id:
                        print(f'     !! Skipping card: empty job_id (componentkey={componentkey!r})')
                        continue
                    url = f'https://www.linkedin.com/jobs/view/{job_id}/'
                    if url in seen:
                        continue

                    card.scroll_into_view_if_needed(timeout=3000)
                    human_delay(0.2, 0.4)
                    texts = card.evaluate(_CARD_TEXTS_JS)
                    if not texts:
                        print(f'     !! Skipping card {job_id}: no <p> texts found')
                        continue
                    if len(texts) < 2:
                        print(f'     !! Skipping card {job_id}: only {len(texts)} paragraph(s): {texts}')
                        continue

                    title = texts[0]
                    company = texts[1] if len(texts) > 1 else ''
                    location = texts[2] if len(texts) > 2 else ''
                    card_salary = texts[3] if len(texts) > 3 else ''
                    card_meta.append((job_id, url, title, company, location, card_salary))
                    seen.add(url)
                except Exception as e:
                    print(f'     !! Card parse error: {e}')
                    continue

            print(f'  Collected {len(card_meta)} new cards to process')

            for job_id, url, title, company, location, card_salary in card_meta:
                cached = load_detail_cache(url)
                if cached:
                    print('      (cached)')
                    description = cached.get('description', '')
                    salary = cached.get('salary')
                    apply_url = cached.get('apply_url', url)
                else:
                    card = page.locator(f'[componentkey="job-card-component-ref-{job_id}"][tabindex="0"]')
                    card.click()
                    human_delay(1.5, 3)

                    try:
                        page.wait_for_selector('[data-testid="expandable-text-box"]', timeout=8000)
                    except Exception:
                        print(f'     !! Detail panel timeout for: {title}')
                        continue

                    description = (
                        page.locator('[data-testid="expandable-text-box"]').first.inner_text(timeout=5000).strip()
                    )
                    if not description:
                        print(f'     !! No description for: {title}')

                    salary = card_salary or None
                    apply_url = url

                    save_detail_cache(
                        url,
                        {
                            'description': description,
                            'salary': salary,
                            'apply_url': apply_url,
                        },
                    )

                    human_delay(2, 4)

                pause_if_suspicious('LinkedIn', title, company, url, description, location)
                jobs.append(
                    JobListing(
                        title=title,
                        company=company,
                        url=url,
                        location=location,
                        salary=salary,
                        summary='',
                        date_added=None,
                        seniority=[],
                        tech_stack=[],
                        industries=[],
                        description=description,
                        requirements='',
                        apply_url=apply_url,
                    )
                )
                print(jobs[-1])

            next_btn = page.locator('[data-testid="pagination-controls-next-button-visible"]')
            if next_btn.count() == 0 or pg >= max_pages:
                break
            next_btn.click()
            human_delay(4, 7)
            page.wait_for_load_state('domcontentloaded')

    finally:
        ctx.close()
        pw.stop()

    return jobs
