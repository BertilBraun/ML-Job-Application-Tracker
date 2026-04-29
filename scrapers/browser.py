import random
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

USER_DATA_DIR = Path(__file__).parent.parent / "user_data" / "chromium"


def human_delay(lo: float = 1.5, hi: float = 4.0) -> None:
    time.sleep(random.uniform(lo, hi))


def get_context():
    """Returns (playwright, context). Caller must call context.close() and pw.stop()."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        slow_mo=80,
        viewport={"width": 1280, "height": 900},
        locale="de-DE",
        timezone_id="Europe/Berlin",
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    return pw, context


def wait_if_blocked(page: Page, indicators: list[str]) -> None:
    """Pause for human to solve CAPTCHA. Saves a screenshot, then waits for Enter."""
    for sel in indicators:
        try:
            if page.locator(sel).count() > 0:
                screenshot = Path(f"debug_blocked_{int(time.time())}.png")
                page.screenshot(path=str(screenshot))
                print(f"\n  !! Blocked ({sel}). Screenshot: {screenshot}")
                print("     Solve in the browser window, then press Enter to continue...")
                input()
                return
        except Exception:
            pass
