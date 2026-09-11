from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import wave
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from keyrhythm.config import AppPaths, CHART_SAMPLE_RATE
from keyrhythm.domain.models import AnalysisJob, AnalysisStage, Song, SongStatus
from keyrhythm.library.repository import DuplicateAudioError, SongRepository
from keyrhythm.resources import executable_path


SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a"}


class ImportErrorBase(RuntimeError):
    pass


class UnsupportedAudioError(ImportErrorBase):
    pass


class ExternalToolError(ImportErrorBase):
    pass


ProgressCallback = Callable[[str, float], None]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pcm_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != CHART_SAMPLE_RATE or handle.getnchannels() != 2 or handle.getsampwidth() != 2:
            raise ExternalToolError("normalized WAV is not 48 kHz stereo PCM16")
        frames = handle.getnframes()
        while data := handle.readframes(16_384):
            digest.update(data)
    return digest.hexdigest(), frames


class SongImporter:
    def __init__(self, paths: AppPaths, repository: SongRepository, ffmpeg: str | None = None):
        self.paths = paths
        self.repository = repository
        self.ffmpeg = ffmpeg or executable_path("ffmpeg.exe") or executable_path("ffmpeg")

    def import_file(
        self,
        source: Path,
        *,
        title: str | None = None,
        artist: str = "",
        tags: tuple[str, ...] = (),
        progress: ProgressCallback | None = None,
    ) -> Song:
        source = source.expanduser().resolve()
        self._validate(source)
        self.paths.ensure()
        job_id = str(uuid.uuid4())
        song_id = str(uuid.uuid4())
        stage = self.paths.staging / job_id
        stage.mkdir(parents=True)
        manifest_path = stage / "import.json"
        current_stage = AnalysisStage.VALIDATE

        def emit(name: str, value: float) -> None:
            nonlocal current_stage
            try:
                current_stage = AnalysisStage(name)
            except ValueError:
                pass
            self._write_manifest(manifest_path, job_id, song_id, name, value, None)
            self.repository.upsert_analysis_job(AnalysisJob(job_id, song_id, current_stage, value))
            if progress:
                progress(name, value)

        try:
            emit("validate", 1.0)
            source_hash = sha256_file(source)
            managed_source = stage / f"source{source.suffix.lower()}"
            shutil.copy2(source, managed_source)
            emit("normalize", 0.1)
            normalized = stage / "normalized.wav"
            self._normalize(managed_source, normalized)
            emit("normalize", 1.0)
            audio_hash, duration_frames = pcm_sha256(normalized)
            duplicate = self.repository.find_by_pcm_hash(audio_hash)
            if duplicate:
                raise DuplicateAudioError(f"audio already exists as {duplicate.id}")

            chart_path = stage / "chart.json"
            playable = self._run_worker(
                normalized,
                chart_path,
                song_id=song_id,
                audio_sha256=audio_hash,
                duration_frames=duration_frames,
                progress=emit,
            )
            emit("validation", 1.0)

            target = self.paths.library / song_id
            if target.exists():
                raise ImportErrorBase(f"target directory already exists: {target}")
            os.replace(stage, target)
            final_source = target / managed_source.name
            final_normalized = target / normalized.name
            final_chart = target / chart_path.name
            now = datetime.now(UTC).isoformat(timespec="seconds")
            song = Song(
                id=song_id,
                source_sha256=source_hash,
                audio_pcm_sha256=audio_hash,
                title=(title or source.stem).strip() or source.stem,
                artist=artist.strip(),
                duration_frames=duration_frames,
                source_path=final_source,
                normalized_path=final_normalized,
                chart_path=final_chart,
                status=SongStatus.READY if playable else SongStatus.NEEDS_REVIEW,
                analysis_version="2026.1",
                created_at=now,
                updated_at=now,
                tags=tuple(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
            )
            try:
                self.repository.add(song)
            except Exception:
                os.replace(target, stage)
                raise
            return song
        except Exception as error:
            if stage.exists():
                self._write_manifest(manifest_path, job_id, song_id, "failed", 0.0, error)
            self.repository.upsert_analysis_job(
                AnalysisJob(job_id, song_id, current_stage, 0.0, type(error).__name__, str(error))
            )
            raise

    def recover_staging(self) -> list[Path]:
        self.paths.ensure()
        return [path for path in self.paths.staging.iterdir() if path.is_dir()]

    def discard_staging(self, job_directory: Path) -> None:
        resolved = job_directory.resolve()
        staging = self.paths.staging.resolve()
        if resolved.parent != staging:
            raise ValueError("refusing to remove a directory outside staging")
        shutil.rmtree(resolved)

    def _validate(self, source: Path) -> None:
        if not source.is_file():
            raise UnsupportedAudioError(f"file does not exist: {source}")
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise UnsupportedAudioError(f"unsupported extension: {source.suffix}")
        if not self.ffmpeg:
            raise ExternalToolError("ffmpeg was not found on PATH")
        required = max(source.stat().st_size * 5, 100 * 1024 * 1024)
        free = shutil.disk_usage(self.paths.root.parent if self.paths.root.parent.exists() else source.parent).free
        if free < required:
            raise ImportErrorBase(f"insufficient disk space: need approximately {required} bytes")

    def _normalize(self, source: Path, output: Path) -> None:
        command = [
            str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(source), "-vn", "-ar", str(CHART_SAMPLE_RATE), "-ac", "2",
            "-c:a", "pcm_s16le", str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise ExternalToolError(result.stderr.strip() or "ffmpeg normalization failed")

    @staticmethod
    def _run_worker(
        audio: Path,
        chart_path: Path,
        *,
        song_id: str,
        audio_sha256: str,
        duration_frames: int,
        progress: ProgressCallback | None,
    ) -> bool:
        if getattr(sys, "frozen", False):
            worker = Path(sys.executable).with_name("KeyRhythmWorker.exe")
            if not worker.is_file():
                raise ExternalToolError(f"analysis worker is missing: {worker}")
            command = [str(worker)]
        else:
            command = [sys.executable, "-m", "keyrhythm.analysis.worker"]
        command.extend([
            "--audio", str(audio), "--output", str(chart_path), "--song-id", song_id,
            "--audio-sha256", audio_sha256, "--duration-frames", str(duration_frames),
        ])
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"
        )
        playable = False
        error_payload: dict[str, object] | None = None
        last_output = ""
        assert process.stdout is not None
        for line in process.stdout:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                last_output = line.strip() or last_output
                continue
            if payload.get("type") == "progress" and progress:
                progress(str(payload["stage"]), float(payload["progress"]))
            elif payload.get("type") == "result":
                playable = bool(payload.get("playable"))
            elif payload.get("type") == "error":
                error_payload = payload
        return_code = process.wait(timeout=3600)
        if return_code != 0 or error_payload:
            detail = str(error_payload.get("detail")) if error_payload else last_output
            raise ExternalToolError(detail or "analysis worker failed")
        if not chart_path.is_file():
            raise ExternalToolError("analysis worker did not create chart.json")
        return playable

    @staticmethod
    def _write_manifest(
        path: Path,
        job_id: str,
        song_id: str,
        stage: str,
        progress: float,
        error: Exception | None,
    ) -> None:
        payload = {
            "job_id": job_id,
            "song_id": song_id,
            "stage": stage,
            "progress": progress,
            "error_code": type(error).__name__ if error else None,
            "error_detail": str(error) if error else None,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
