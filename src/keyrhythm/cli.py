from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from keyrhythm.config import AppPaths
from keyrhythm.domain.chart import load_chart
from keyrhythm.library import Database, SongRepository
from keyrhythm.library.importer import SongImporter
from keyrhythm.library.presets import ensure_builtin_song
from keyrhythm.resources import executable_path, resource_path


def context() -> tuple[AppPaths, Database, SongRepository]:
    paths = AppPaths.discover()
    paths.ensure()
    database = Database(paths.database)
    database.migrate()
    repository = SongRepository(database)
    ensure_builtin_song(paths, repository)
    return paths, database, repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keyrhythm", description="KeyRhythm local music game")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="create the user data directories and database")
    listing = subparsers.add_parser("list", help="list or search the local library")
    listing.add_argument("query", nargs="?", default="")
    importing = subparsers.add_parser("import", help="import and analyze a local audio file")
    importing.add_argument("path", type=Path)
    importing.add_argument("--title")
    importing.add_argument("--artist", default="")
    importing.add_argument("--tag", action="append", default=[])
    validating = subparsers.add_parser("validate-chart", help="validate a chart.json file")
    validating.add_argument("path", type=Path)
    subparsers.add_parser("doctor", help="report runtime and optional dependency status")
    subparsers.add_parser("gui", help="launch the desktop application")
    return parser


def doctor() -> dict[str, object]:
    modules = ["PySide6", "numpy", "sounddevice", "soundfile", "librosa", "basic_pitch", "onnxruntime"]
    ffmpeg = executable_path("ffmpeg.exe") or executable_path("ffmpeg")
    fluidsynth = resource_path("bin/libfluidsynth-3.dll")
    soundfont = resource_path("assets/soundfonts/default.sf2")
    worker = Path(sys.executable).with_name("KeyRhythmWorker.exe") if getattr(sys, "frozen", False) else None
    return {
        "python": sys.version.split()[0],
        "supported_python": sys.version_info[:2] == (3, 11),
        "frozen": bool(getattr(sys, "frozen", False)),
        "executables": {
            "ffmpeg": ffmpeg,
            "fluidsynth": str(fluidsynth) if fluidsynth.is_file() else None,
            "analysis_worker": str(worker) if worker and worker.is_file() else ("source" if worker is None else None),
        },
        "assets": {"soundfont": str(soundfont) if soundfont.is_file() else None},
        "modules": {name: importlib.util.find_spec(name) is not None for name in modules},
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "gui":
        from keyrhythm.app import main as gui_main
        return gui_main([])
    if args.command == "validate-chart":
        chart = load_chart(args.path)
        print(f"valid schema v{chart.schema_version}: {len(chart.notes)} notes, revision {chart.chart_revision}")
        return 0

    paths, _database, repository = context()
    if args.command == "init":
        print(paths.root)
        return 0
    if args.command == "list":
        songs = repository.search(args.query)
        for song in songs:
            duration = song.duration_frames / 48_000
            print(f"{song.id}\t{song.status.value}\t{duration:.1f}s\t{song.artist}\t{song.title}")
        return 0
    if args.command == "import":
        importer = SongImporter(paths, repository)
        song = importer.import_file(
            args.path,
            title=args.title,
            artist=args.artist,
            tags=tuple(args.tag),
            progress=lambda stage, value: print(f"{stage}: {value:.0%}"),
        )
        print(song.id)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
