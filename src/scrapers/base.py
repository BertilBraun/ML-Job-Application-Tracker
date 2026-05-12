"""Shared HTTP session and detail-page disk cache used by all scrapers."""
import hashlib
import json
import time
import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"

_session = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)


def fetch_soup(url: str, warmup_url: str | None = None) -> BeautifulSoup:
    if warmup_url and not _session.cookies:
        try:
            _session.get(warmup_url, timeout=10)
            time.sleep(0.5)
        except Exception:
            pass
    resp = _session.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _detail_cache_path(url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def load_detail_cache(url: str) -> dict | None:
    path = _detail_cache_path(url)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_detail_cache(url: str, data: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _detail_cache_path(url).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def pause_if_suspicious(source: str, title: str, company: str, url: str, description: str, location: str) -> None:
    empty = [name for name, val in [('title', title), ('company', company), ('description', description)] if not val]
    if not empty:
        return
    print(f'\n{"!" * 60}')
    print(f'  [{source}] SUSPICIOUS JOB — empty fields: {", ".join(empty)}')
    print(f'  Title      : {title!r}')
    print(f'  Company    : {company!r}')
    print(f'  Location   : {location!r}')
    print(f'  URL        : {url}')
    print(f'  Description: {description[:300]!r}{"..." if len(description) > 300 else ""}')
    print(f'{"!" * 60}')
    input('  Press Enter to continue (or Ctrl+C to abort)...')
