import hashlib
import json
import time
import cloudscraper
from bs4 import BeautifulSoup, Tag
from pathlib import Path
from models import JobListing

BASE_URL = "https://www.remoterocketship.com"
CACHE_DIR = Path(__file__).parent / "cache"

# cloudscraper handles Cloudflare JS challenges automatically
_session = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)


def _cache_path(url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _load_cached(url: str) -> dict | None:
    path = _cache_path(url)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_cache(url: str, data: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(url).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def fetch_soup(url: str) -> BeautifulSoup:
    if not _session.cookies:
        try:
            _session.get(BASE_URL, timeout=10)
            time.sleep(0.5)
        except Exception:
            pass

    resp = _session.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def classify_pill(text: str, has_employee_img: bool) -> str:
    t = text.strip()
    if has_employee_img:
        return "company_size"
    if " \u2013 " in t or " – " in t:  # em dash = location separator
        return "location"
    if any(c in t for c in ["💵", "£", "€"]) or (("$" in t or "k" in t.lower()) and "/" in t):
        return "salary"
    if t.startswith(("🟢", "🟡", "🟠", "🔴")):
        return "seniority"
    if t.startswith("⏰"):
        return "employment"
    if t.startswith(("🤖", "🏢", "🎮", "🌍", "🏛️", "📋", "🔒", "⚕️", "🏦", "🛒", "🚀", "🔬", "🎓", "🏗️", "🌐", "⚡", "🎯")):
        return "industry"
    if "🗣️" in t:
        return "language"
    if "employees" in t.lower():
        return "company_size"
    return "tech"


def parse_job_card(card: Tag) -> dict | None:
    title_el = card.select_one("h3 a[target='_blank']") or card.select_one("h3 a")
    if not title_el:
        return None

    href = title_el.get("href", "")
    if not href:
        return None

    job: dict = {
        "title": title_el.get_text(strip=True),
        "company": "",
        "url": BASE_URL + href if href.startswith("/") else href,
        "apply_url": None,
        "date_added": None,
        "summary": "",
        "location": "",
        "salary": None,
        "seniority": [],
        "tech_stack": [],
        "company_size": None,
        "industries": [],
    }

    company_el = card.select_one("h4 a")
    if company_el:
        job["company"] = company_el.get_text(strip=True)

    for p in card.find_all("p"):
        txt = p.get_text()
        if "🕒" in txt:
            job["date_added"] = txt.replace("🕒", "").strip()
            break

    summary_el = card.select_one("p.text-secondary.mb-4")
    if summary_el:
        job["summary"] = summary_el.get_text(strip=True)

    apply_el = card.select_one("a[rel='noreferrer noopener']")
    if apply_el:
        job["apply_url"] = apply_el.get("href")

    for pill in card.select("div.bg-pill, a.bg-pill"):
        p_el = pill.select_one("p")
        if not p_el:
            continue
        text = p_el.get_text(strip=True)
        if not text:
            continue
        has_employee_img = bool(pill.select_one("img"))
        category = classify_pill(text, has_employee_img)

        if category == "location" and not job["location"]:
            job["location"] = text
        elif category == "salary" and not job["salary"]:
            job["salary"] = text
        elif category == "seniority":
            job["seniority"].append(text)
        elif category == "company_size" and not job["company_size"]:
            job["company_size"] = text
        elif category == "industry":
            job["industries"].append(text)

    for mt4 in card.select("div.mt-4"):
        for pill in mt4.select("div.bg-pill, a.bg-pill"):
            p_el = pill.select_one("p")
            if not p_el:
                continue
            text = p_el.get_text(strip=True)
            if not text:
                continue
            has_img = bool(pill.select_one("img"))
            cat = classify_pill(text, has_img)
            if cat == "tech" and text not in job["tech_stack"]:
                job["tech_stack"].append(text)

    return job


def fetch_job_details(url: str) -> dict:
    """Fetch full description and requirements from the job detail page, using disk cache."""
    cached = _load_cached(url)
    if cached is not None:
        print("      (cached)")
        return cached

    time.sleep(0.75)
    details: dict = {"description": "", "requirements": "", "apply_url": None}
    try:
        soup = fetch_soup(url)

        for h3 in soup.find_all("h3"):
            heading = h3.get_text()
            if "Description" in heading:
                p = h3.find_next_sibling("p")
                if p:
                    details["description"] = p.get_text(strip=True)
            elif "Requirements" in heading:
                p = h3.find_next_sibling("p")
                if p:
                    details["requirements"] = p.get_text(strip=True)

        apply_el = soup.select_one("a[rel='noreferrer noopener']")
        if apply_el:
            details["apply_url"] = apply_el.get("href")

        _save_cache(url, details)

    except Exception as e:
        print(f"    Warning: could not fetch detail page: {e}")

    return details


def scrape_jobs(search_url: str, max_pages: int = 2) -> list[JobListing]:
    """Scrape job listings from the search results, fetching each detail page."""
    all_jobs: list[JobListing] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        if page == 1:
            url = search_url
        elif "page=1" in search_url:
            url = search_url.replace("page=1", f"page={page}")
        else:
            sep = "&" if "?" in search_url else "?"
            url = f"{search_url}{sep}page={page}"

        print(f"\nFetching page {page}: {url[:80]}...")

        try:
            soup = fetch_soup(url)
            cards = soup.select("div.list-none > div.relative")

            if not cards:
                print("  No job cards found on this page.")
                break

            print(f"  Found {len(cards)} job card(s)")
            new_on_page = 0

            for card in cards:
                job_data = parse_job_card(card)
                if not job_data:
                    continue

                if job_data["url"] in seen_urls:
                    continue
                seen_urls.add(job_data["url"])
                new_on_page += 1

                print(f"  -> Fetching details: {job_data['title']} @ {job_data['company']}")
                details = fetch_job_details(job_data["url"])

                if details["apply_url"]:
                    job_data["apply_url"] = details["apply_url"]
                job_data["description"] = details["description"]
                job_data["requirements"] = details["requirements"]

                all_jobs.append(JobListing(**job_data))

            if new_on_page == 0:
                print("  No new jobs on this page, stopping.")
                break

            time.sleep(1.5)

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break

    return all_jobs
