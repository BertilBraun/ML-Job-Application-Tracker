# Job Listing Scraper & Application Tracker

Scrapes ML/AI job listings from LinkedIn, Stepstone, and RemoteRocketship, scores them with Gemini against a candidate profile, and provides a browser UI for reviewing results and tracking applications end-to-end.

## Features

- Playwright-based scrapers with persistent login sessions and detail-page caching
- Gemini assessment of team quality, work impact, location, technical match, and realistic CV screening fit
- Stretch-aware deterministic recommendations: senior roles can be stretches; lead/staff/principal/head/director roles are excluded
- Results UI with separate application-priority, opportunity-fit, screening-fit, and technical-match rankings
- Extraction quality gate with seniority/experience normalization and a per-run `extraction_audit.json`
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
python scrape.py [--pages N] [--sources linkedin stepstone ...]
```

Scrapes all enabled sources, quarantines malformed extractions, scores every accepted listing with Gemini, and writes `extraction_audit.json`, `results.json`, and `results.html`.

To inspect extraction before spending model calls, split the run:

```bash
python scrape.py --pages 1 --scrape-only
python scrape.py --input scraped_jobs.json
```

### 3. Start the app server

```bash
python serve.py
```

Opens at `http://localhost:5000`.

- `/` — Results page: score breakdown, weight sliders, Track button per job
- `/applications` — Application tracker: status, notes, event log, generate tailored About + cover letter on demand

## Configuration

| File | Purpose |
| --- | --- |
| `PROFILE.md` | Candidate profile used by the LLM scorer |
| `RESUME.md` | Full CV used for tailored About/cover letter generation |
| `CANDIDATE_EVIDENCE.md` | Evidence/status guardrails used by scoring and application generation |
| `src/scrapers/__init__.py` | Enable/disable sources and set search URLs |

## Project structure

```text
scrape.py            # scrape + analyze entry point
serve.py             # Flask server
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
