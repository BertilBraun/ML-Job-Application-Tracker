import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DB_PATH = Path(__file__).parent.parent / 'applications.db'


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                job_url           TEXT    NOT NULL UNIQUE,
                job_title         TEXT    NOT NULL,
                company           TEXT    NOT NULL,
                listing_url       TEXT,
                apply_url         TEXT,
                location          TEXT,
                salary            TEXT,
                status            TEXT    NOT NULL DEFAULT 'draft',
                created_at        TEXT    NOT NULL,
                applied_at        TEXT,
                about_text        TEXT,
                technical_skills  TEXT,
                project_order     TEXT,
                cover_letter      TEXT,
                job_payload       TEXT,
                analysis_payload  TEXT,
                materials_status  TEXT    NOT NULL DEFAULT '',
                generation_guidance TEXT NOT NULL DEFAULT '',
                language          TEXT    NOT NULL DEFAULT 'en',
                notes             TEXT    NOT NULL DEFAULT '',
                next_step_date    TEXT,
                next_step_label   TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id   INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                created_at       TEXT    NOT NULL,
                content          TEXT    NOT NULL
            );
        """)
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(applications)').fetchall()}
        if 'generation_guidance' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN generation_guidance TEXT NOT NULL DEFAULT ''")
        if 'language' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
        if 'technical_skills' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN technical_skills TEXT")
        if 'project_order' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN project_order TEXT")
        if 'job_payload' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN job_payload TEXT")
        if 'analysis_payload' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN analysis_payload TEXT")
        if 'materials_status' not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN materials_status TEXT NOT NULL DEFAULT ''")
