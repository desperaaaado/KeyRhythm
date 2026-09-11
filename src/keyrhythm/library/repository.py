from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from keyrhythm.domain.models import AnalysisJob, AnalysisStage, Score, Song, SongStatus
from keyrhythm.library.database import Database


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DuplicateAudioError(ValueError):
    pass


class SongRepository:
    def __init__(self, database: Database):
        self.database = database

    def add(self, song: Song) -> None:
        now = utc_now()
        song.created_at = song.created_at or now
        song.updated_at = now
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO songs(
                        id, source_sha256, audio_pcm_sha256, title, artist,
                        duration_frames, source_path, normalized_path, chart_path,
                        cover_path, status, analysis_version, chart_revision,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        song.id, song.source_sha256, song.audio_pcm_sha256, song.title, song.artist,
                        song.duration_frames, str(song.source_path), str(song.normalized_path),
                        str(song.chart_path) if song.chart_path else None,
                        str(song.cover_path) if song.cover_path else None, song.status.value,
                        song.analysis_version, 1 if song.chart_path else 0, song.created_at, song.updated_at,
                    ),
                )
                self._replace_tags(connection, song.id, song.tags)
                self._refresh_fts(connection, song.id)
        except sqlite3.IntegrityError as error:
            if "audio_pcm_sha256" in str(error):
                raise DuplicateAudioError(song.audio_pcm_sha256) from error
            raise

    def update_status(
        self,
        song_id: str,
        status: SongStatus,
        *,
        chart_path: Path | None = None,
        analysis_version: str | None = None,
        chart_revision: int | None = None,
    ) -> None:
        fields = ["status = ?", "updated_at = ?"]
        values: list[object] = [status.value, utc_now()]
        if chart_path is not None:
            fields.append("chart_path = ?")
            values.append(str(chart_path))
        if analysis_version is not None:
            fields.append("analysis_version = ?")
            values.append(analysis_version)
        if chart_revision is not None:
            fields.append("chart_revision = ?")
            values.append(chart_revision)
        values.append(song_id)
        with self.database.transaction() as connection:
            connection.execute(f"UPDATE songs SET {', '.join(fields)} WHERE id = ?", values)
            self._refresh_fts(connection, song_id)

    def get(self, song_id: str) -> Song | None:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
            return self._to_song(connection, row) if row else None

    def find_by_pcm_hash(self, digest: str) -> Song | None:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM songs WHERE audio_pcm_sha256 = ?", (digest,)).fetchone()
            return self._to_song(connection, row) if row else None

    def list(self, *, limit: int = 100) -> list[Song]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM songs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._to_song(connection, row) for row in rows]

    def search(self, query: str, *, limit: int = 100) -> list[Song]:
        term = query.strip()
        if not term:
            return self.list(limit=limit)
        with self.database.read() as connection:
            try:
                rows = connection.execute(
                    "SELECT s.* FROM songs_fts f JOIN songs s ON s.id=f.song_id WHERE songs_fts MATCH ? LIMIT ?",
                    (f'"{term.replace(chr(34), chr(34) * 2)}"', limit),
                ).fetchall()
            except sqlite3.OperationalError:
                like = f"%{term}%"
                rows = connection.execute(
                    """
                    SELECT DISTINCT s.* FROM songs s
                    LEFT JOIN song_tags t ON t.song_id=s.id
                    WHERE s.title LIKE ? OR s.artist LIKE ? OR t.tag LIKE ?
                    ORDER BY s.updated_at DESC LIMIT ?
                    """,
                    (like, like, like, limit),
                ).fetchall()
            return [self._to_song(connection, row) for row in rows]

    def delete(self, song_id: str) -> None:
        with self.database.transaction() as connection:
            try:
                connection.execute("DELETE FROM songs_fts WHERE song_id = ?", (song_id,))
            except sqlite3.OperationalError:
                pass
            connection.execute("DELETE FROM songs WHERE id = ?", (song_id,))

    def save_score(self, score: Score) -> int:
        score.completed_at = score.completed_at or utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scores(
                    song_id, chart_revision, chart_hash, mode, difficulty, total_score, accuracy,
                    max_combo, perfect_count, good_count, bad_count, wrong_count, miss_count,
                    hold_break_count, calibration_frames, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.song_id, score.chart_revision, score.chart_hash, score.mode.value,
                    score.difficulty.value if score.difficulty else None, score.total_score, score.accuracy,
                    score.max_combo, score.perfect_count, score.good_count, score.bad_count,
                    score.wrong_count, score.miss_count, score.hold_break_count,
                    score.calibration_frames, score.completed_at,
                ),
            )
            return int(cursor.lastrowid)

    def upsert_analysis_job(self, job: AnalysisJob) -> None:
        now = utc_now()
        job.created_at = job.created_at or now
        job.updated_at = now
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO analysis_jobs(id, song_id, stage, progress, error_code, error_detail, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    song_id=excluded.song_id, stage=excluded.stage, progress=excluded.progress,
                    error_code=excluded.error_code, error_detail=excluded.error_detail, updated_at=excluded.updated_at
                """,
                (
                    job.id, job.song_id, job.stage.value, job.progress, job.error_code,
                    job.error_detail, job.created_at, job.updated_at,
                ),
            )

    def get_analysis_job(self, job_id: str) -> AnalysisJob | None:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM analysis_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        return AnalysisJob(
            id=row["id"], song_id=row["song_id"], stage=AnalysisStage(row["stage"]),
            progress=row["progress"], error_code=row["error_code"], error_detail=row["error_detail"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _replace_tags(connection: sqlite3.Connection, song_id: str, tags: tuple[str, ...]) -> None:
        connection.execute("DELETE FROM song_tags WHERE song_id = ?", (song_id,))
        connection.executemany(
            "INSERT OR IGNORE INTO song_tags(song_id, tag) VALUES (?, ?)",
            ((song_id, tag.strip()) for tag in tags if tag.strip()),
        )

    @staticmethod
    def _refresh_fts(connection: sqlite3.Connection, song_id: str) -> None:
        try:
            connection.execute("DELETE FROM songs_fts WHERE song_id = ?", (song_id,))
            connection.execute(
                """
                INSERT INTO songs_fts(song_id, title, artist, tags)
                SELECT s.id, s.title, s.artist, COALESCE(group_concat(t.tag, ' '), '')
                FROM songs s LEFT JOIN song_tags t ON t.song_id=s.id
                WHERE s.id=? GROUP BY s.id
                """,
                (song_id,),
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _to_song(connection: sqlite3.Connection, row: sqlite3.Row) -> Song:
        tags = tuple(
            value[0] for value in connection.execute("SELECT tag FROM song_tags WHERE song_id=? ORDER BY tag", (row["id"],))
        )
        return Song(
            id=row["id"],
            source_sha256=row["source_sha256"],
            audio_pcm_sha256=row["audio_pcm_sha256"],
            title=row["title"],
            artist=row["artist"],
            duration_frames=row["duration_frames"],
            source_path=Path(row["source_path"]),
            normalized_path=Path(row["normalized_path"]),
            chart_path=Path(row["chart_path"]) if row["chart_path"] else None,
            cover_path=Path(row["cover_path"]) if row["cover_path"] else None,
            status=SongStatus(row["status"]),
            analysis_version=row["analysis_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tags=tags,
        )
