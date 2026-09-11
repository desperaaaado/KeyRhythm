from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    );
    INSERT INTO schema_version(version)
    SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
    """,
    """
    CREATE TABLE songs (
        id TEXT PRIMARY KEY,
        source_sha256 TEXT NOT NULL,
        audio_pcm_sha256 TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        duration_frames INTEGER NOT NULL CHECK(duration_frames > 0),
        source_path TEXT NOT NULL,
        normalized_path TEXT NOT NULL,
        chart_path TEXT,
        cover_path TEXT,
        status TEXT NOT NULL CHECK(status IN ('importing','ready','needs_review','failed')),
        analysis_version TEXT,
        chart_revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX songs_source_hash_idx ON songs(source_sha256);
    CREATE INDEX songs_updated_idx ON songs(updated_at DESC);

    CREATE TABLE song_tags (
        song_id TEXT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
        tag TEXT NOT NULL COLLATE NOCASE,
        PRIMARY KEY(song_id, tag)
    );

    CREATE TABLE song_mix_settings (
        song_id TEXT PRIMARY KEY REFERENCES songs(id) ON DELETE CASCADE,
        backing_volume INTEGER CHECK(backing_volume BETWEEN 0 AND 100),
        instrument_volume INTEGER CHECK(instrument_volume BETWEEN 0 AND 100),
        master_volume INTEGER CHECK(master_volume BETWEEN 0 AND 100)
    );

    CREATE TABLE scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_id TEXT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
        chart_revision INTEGER NOT NULL,
        chart_hash TEXT NOT NULL,
        mode TEXT NOT NULL,
        difficulty TEXT,
        total_score INTEGER NOT NULL,
        accuracy REAL NOT NULL,
        max_combo INTEGER NOT NULL,
        perfect_count INTEGER NOT NULL,
        good_count INTEGER NOT NULL,
        bad_count INTEGER NOT NULL,
        wrong_count INTEGER NOT NULL,
        miss_count INTEGER NOT NULL,
        hold_break_count INTEGER NOT NULL,
        calibration_frames INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT NOT NULL
    );

    CREATE TABLE analysis_jobs (
        id TEXT PRIMARY KEY,
        song_id TEXT,
        stage TEXT NOT NULL,
        progress REAL NOT NULL DEFAULT 0,
        error_code TEXT,
        error_detail TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
)


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def migrate(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(MIGRATIONS[0])
            current = int(connection.execute("SELECT version FROM schema_version").fetchone()[0])
            for target, script in enumerate(MIGRATIONS[1:], start=1):
                if current < target:
                    connection.executescript(script)
                    connection.execute("UPDATE schema_version SET version = ?", (target,))
                    current = target
            self._create_search(connection)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _create_search(connection: sqlite3.Connection) -> None:
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS songs_fts USING fts5(song_id UNINDEXED, title, artist, tags)"
            )
        except sqlite3.OperationalError:
            return

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
