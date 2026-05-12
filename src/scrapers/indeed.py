from models import JobListing
from scrapers.base import load_detail_cache, save_detail_cache
from scrapers.browser import get_context, human_delay, wait_if_blocked

SEARCH_URL = "https://de.indeed.com/jobs?q=Machine+Learning+Engineer&l=Germany&from=searchOnDesktopSerp"
BLOCK = ["#captcha-title", "iframe[title*='recaptcha']", ".cf-challenge-running", "h1:has-text('Verify')"]
BASE = "https://de.indeed.com"


def _ensure_logged_in(page) -> None:
    page.goto("https://de.indeed.com/meine-jobs", wait_until="domcontentloaded")
    if "login" in page.url or "account" in page.url:
        print("\nIndeed session expired. Log in manually in the browser, then press Enter...")
        input()


def scrape_jobs(search_url: str = SEARCH_URL, max_pages: int = 3) -> list[JobListing]:
    pw, ctx = get_context()
    page = ctx.new_page()
    jobs: list[JobListing] = []
    seen: set[str] = set()

    try:
        _ensure_logged_in(page)

        for p in range(max_pages):
            url = search_url if p == 0 else f"{search_url}&start={p * 10}"
            page.goto(url, wait_until="networkidle")
            wait_if_blocked(page, BLOCK)
            human_delay(2, 4)

            if page.locator("div.jobsearch-NoResult").count() > 0:
                break

            cards = page.locator("div.job_seen_beacon").all()
            hrefs = []
            for card in cards:
                try:
                    href = card.locator("a.jcs-JobTitle").get_attribute("href")
                    if not href or href in seen:
                        continue
                    seen.add(href)
                    hrefs.append((
                        href,
                        card.locator("h2.jobTitle").inner_text(timeout=2000).strip(),
                        _try_get(card, "span.companyName") or _try_get(card, "[data-testid='company-name']") or "",
                        _try_get(card, "div.companyLocation") or _try_get(card, "[data-testid='text-location']") or "",
                        _try_get(card, "div.salary-snippet-container"),
                        card.inner_text(timeout=2000).strip()[:300],
                    ))
                except Exception:
                    continue

            for href, title, company, location, salary, summary in hrefs:
                detail_url = BASE + href if href.startswith("/") else href
                cached = load_detail_cache(detail_url)
                if cached:
                    print("      (cached)")
                    details = cached
                else:
                    page.goto(detail_url, wait_until="domcontentloaded")
                    wait_if_blocked(page, BLOCK)
                    # use the final URL after any redirect as the canonical key
                    final_url = page.url
                    human_delay(3, 7)
                    desc = _try_get_page(page, "div#jobDescriptionText") or ""
                    details = {
                        "description": desc,
                        "requirements": "",
                        "apply_url": None,
                    }
                    save_detail_cache(detail_url, details)
                    if final_url != detail_url:
                        save_detail_cache(final_url, details)
                    detail_url = final_url

                jobs.append(JobListing(
                    title=title,
                    company=company,
                    url=detail_url,
                    location=location,
                    salary=salary,
                    summary=summary,
                    seniority=[],
                    tech_stack=[],
                    industries=[],
                    **details,
                ))
                print(f"  -> {title} @ {company}")

            human_delay(4, 8)

    finally:
        ctx.close()
        pw.stop()

    return jobs


def _try_get(locator, selector: str) -> str | None:
    try:
        el = locator.locator(selector)
        if el.count() > 0:
            return el.inner_text(timeout=1500).strip() or None
    except Exception:
        pass
    return None


def _try_get_page(page, selector: str) -> str | None:
    try:
        el = page.locator(selector)
        if el.count() > 0:
            return el.inner_text(timeout=5000).strip() or None
    except Exception:
        pass
    return None
