from __future__ import annotations

import sqlite3

import src.db as db


def test_init_db_migrates_tailored_cv_columns(tmp_path, monkeypatch):
    db_path = tmp_path / 'applications.db'
    monkeypatch.setattr(db, 'DB_PATH', db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_url TEXT NOT NULL UNIQUE,
                job_title TEXT NOT NULL,
                company TEXT NOT NULL,
                created_at TEXT NOT NULL,
                about_text TEXT,
                cover_letter TEXT
            )
            """
        )

    db.init_db()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(applications)').fetchall()}

    assert 'technical_skills' in columns
    assert 'project_order' in columns
