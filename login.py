"""
One-time manual login for all three sites.
Run this once: python login.py
Sessions are saved to user_data/chromium/ and reused automatically.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

from scrapers.browser import get_context

SITES = [
    ('Stepstone', 'https://www.stepstone.de'),
    # TODO ('Indeed', 'https://de.indeed.com/account/login'),
    ('LinkedIn', 'https://www.linkedin.com/login'),
]

pw, ctx = get_context()
page = ctx.new_page()

try:
    for name, url in SITES:
        page.goto(url, wait_until='domcontentloaded')
        input(f'\n  [{name}] Log in in the browser window, then press Enter...')
        print(f'  [{name}] Session saved.')
finally:
    ctx.close()
    pw.stop()

print('\nDone. All sessions stored in user_data/chromium/')
