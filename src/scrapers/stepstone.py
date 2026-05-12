import os
from dotenv import load_dotenv
from models import JobListing
from scrapers.base import load_detail_cache, save_detail_cache, pause_if_suspicious
from scrapers.browser import get_context, human_delay, wait_if_blocked

load_dotenv()

SEARCH_URL = os.environ.get('STEPSTONE_SEARCH_URL', '')
if not SEARCH_URL:
    raise ValueError('STEPSTONE_SEARCH_URL not set in .env — see .env.example')
BLOCK = ['#captcha', '.g-recaptcha', "iframe[title*='recaptcha']"]


def _ensure_logged_in(page) -> None:
    page.goto('https://www.stepstone.de/mein-bereich/', wait_until='domcontentloaded')
    if 'login' in page.url or 'kandidaten' in page.url:
        print('\nStepstone session expired. Log in manually in the browser, then press Enter...')
        input()


# Detail page description selectors tried in order
_DESC_SELECTORS = [
    '[data-at="job-ad-content"]',
    "[data-testid='job-detail-description']",
    '.at-section-text',
    'main',
]


def _get_salary(card) -> str | None:
    try:
        el = card.locator('[data-at="salary-range"]')
        if el.count() > 0:
            return el.first.inner_text(timeout=1000).strip() or None
    except Exception:
        pass
    return None


def _get_description(page) -> str:
    for sel in _DESC_SELECTORS:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                text = el.first.inner_text(timeout=5000).strip()
                if text:
                    return text
        except Exception:
            pass
    return ''


def _try_get(locator, selector: str) -> str | None:
    try:
        el = locator.locator(selector)
        if el.count() > 0:
            return el.inner_text(timeout=1500).strip() or None
    except Exception:
        pass
    return None


def scrape_jobs(search_url: str = SEARCH_URL, max_pages: int = 3) -> list[JobListing]:
    pw, ctx = get_context()
    page = ctx.new_page()
    jobs: list[JobListing] = []
    seen: set[str] = set()

    try:
        _ensure_logged_in(page)

        for p in range(1, max_pages + 1):
            url = search_url if p == 1 else f'{search_url}&page={p}'
            page.goto(url, wait_until='domcontentloaded')
            wait_if_blocked(page, BLOCK)
            human_delay(2, 4)

            cards = page.locator("article[data-testid='job-item']").all()
            if not cards:
                break

            card_data = []
            for card in cards:
                try:
                    a = card.locator("a[data-testid='job-item-title']")
                    href = a.get_attribute('href')
                    if not href or href in seen:
                        continue
                    seen.add(href)
                    detail_url = href if href.startswith('http') else 'https://www.stepstone.de' + href
                    card_data.append(
                        {
                            'url': detail_url,
                            'title': a.inner_text(timeout=2000).strip(),
                            'company': card.locator("[data-at='job-item-company-name']")
                            .inner_text(timeout=2000)
                            .strip(),
                            'location': card.locator("[data-at='job-item-location']").inner_text(timeout=2000).strip(),
                            'salary': _get_salary(card),
                            'date_added': _try_get(card, "[data-at='job-item-timeago']"),
                        }
                    )
                except Exception:
                    continue

            for cd in card_data:
                cached = load_detail_cache(cd['url'])
                if cached:
                    details = cached
                else:
                    print(f'  Fetching details for: {cd["title"]} at {cd["company"]} — {cd["url"]}')
                    try:
                        page.goto(cd['url'], wait_until='domcontentloaded')
                    except Exception as e:
                        print(f'     !! Network error fetching detail page: {e}')
                        input('     !! Fix the issue (e.g. solve captcha in browser), then press Enter to continue...')
                        continue
                    wait_if_blocked(page, BLOCK)
                    human_delay(4, 8)

                    desc = _get_description(page)
                    if not desc:
                        print(f'     !! No description found — URL: {page.url}')

                    details = {
                        'description': desc,
                        'requirements': '',
                        'apply_url': page.url,
                    }
                    save_detail_cache(cd['url'], details)

                pause_if_suspicious(
                    'Stepstone', cd['title'], cd['company'], cd['url'], details.get('description', ''), cd['location']
                )
                jobs.append(
                    JobListing(
                        title=cd['title'],
                        company=cd['company'],
                        url=cd['url'],
                        location=cd['location'],
                        summary='',
                        salary=cd.get('salary'),
                        date_added=cd.get('date_added'),
                        seniority=[],
                        tech_stack=[],
                        industries=[],
                        **details,
                    )
                )
                print(jobs[-1])

            human_delay(4, 7)

    finally:
        ctx.close()
        pw.stop()

    return jobs
