# Job Listing Scraper & Application Tracker

Scrapes ML/AI job listings from LinkedIn, Stepstone, and RemoteRocketship, scores them with Gemini against a candidate profile, and provides a browser UI for reviewing results and tracking applications end-to-end.

## Features

- Playwright-based scrapers with persistent login sessions and detail-page caching
- Gemini LLM scoring across four dimensions: team quality, work impact, location fit, candidate fit
- Results UI with live score reweighting via sliders
- Application tracker: status pipeline, event log, notes, next-step scheduling
- On-demand resume tailoring and cover letter generation per job

## Setup

```bash
pip install -e .          # installs all dependencies and registers src/
playwright install chromium
```

Create a `.env` file at the project root:

```env
GEMINI_API_KEY=your_key_here
```

## Usage

### 1. Log in to job sites (once)

```bash
python login.py
```

Opens a browser window for each site. Log in manually, then press Enter. Sessions are saved to `user_data/chromium/` and reused on subsequent runs.

### 2. Scrape and analyze

```bash
python main.py [max_pages]   # default: 20 pages
```

Scrapes all enabled sources, scores every listing with Gemini, and writes `results.json` and `results.html`.

### 3. Start the app server

```bash
python app.py
```

Opens at `http://localhost:5000`.

- `/` — Results page: score breakdown, weight sliders, Track button per job
- `/applications` — Application tracker: status, notes, event log, generate tailored About + cover letter on demand

## Configuration

| File | Purpose |
| --- | --- |
| `PROFILE.md` | Candidate profile used by the LLM scorer |
| `RESUME.md` | Full CV used for tailored About/cover letter generation |
| `src/scrapers/__init__.py` | Enable/disable sources and set search URLs |

## Project structure

```text
main.py              # scrape + analyze entry point
app.py               # Flask server
login.py             # one-time login helper
applications.html    # tracker SPA (served by Flask)
PROFILE.md           # candidate profile
RESUME.md            # CV for resume optimization
src/
  models.py          # Pydantic models
  analyzer.py        # Gemini job scoring
  resume_optimizer.py# Gemini resume tailoring
  build_ui.py        # results.html generator
  db.py              # SQLite helpers
  scrapers/
    __init__.py      # source registry
    browser.py       # shared Playwright context
    base.py          # detail cache + scraping helpers
    linkedin.py
    stepstone.py
    remoterocketship.py
    indeed.py        # disabled (TODO)
```
