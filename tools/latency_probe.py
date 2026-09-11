from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from keyrhythm.audio import AudioEngine
from keyrhythm.config import AppPaths
from keyrhythm.domain.models import AudioBus
from keyrhythm.library import Database, SongRepository
from keyrhythm.library.presets import ensure_builtin_song


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a silent KeyRhythm output-stream stability probe")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = AppPaths.discover()
    paths.ensure()
    database = Database(paths.database)
    database.migrate()
    song = ensure_builtin_song(paths, SongRepository(database))
    engine = AudioEngine()
    engine.load_song(song.normalized_path)
    for bus in AudioBus:
        engine.set_bus_volume(bus, 0)
    engine.play()
    deadline = time.monotonic() + args.seconds
    samples = []
    while time.monotonic() < deadline:
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        samples.append(engine.get_diagnostics())
    snapshot = engine.get_timeline_snapshot()
    engine.close()
    last = samples[-1]
    payload = {
        "duration_seconds": args.seconds,
        "presented_frames": snapshot.presented_frame,
        "sample_rate": last.sample_rate,
        "block_size": last.block_size,
        "reported_output_latency_ms": last.output_latency_seconds * 1000,
        "max_cpu_load": max(sample.cpu_load for sample in samples),
        "xruns": last.xruns,
        "queue_overflows": last.queue_overflows,
        "clipping_events": last.clipping_events,
        "passes_output_path_gate": last.output_latency_seconds <= 0.035 and last.xruns == 0,
        "note": "This is not a physical key-to-speaker loopback measurement.",
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if payload["passes_output_path_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

