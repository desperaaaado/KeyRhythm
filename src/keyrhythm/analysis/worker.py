from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from keyrhythm.analysis.pipeline import analyze_audio
from keyrhythm.domain.chart import save_chart_atomic
from keyrhythm.resources import executable_path, resource_path


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="verify bundled analysis and synthesis resources")
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--song-id")
    parser.add_argument("--audio-sha256")
    parser.add_argument("--duration-frames", type=int)
    return parser


def release_self_test() -> dict[str, object]:
    import numpy as np  # type: ignore
    from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore
    from keyrhythm.audio.synthesizer import FluidSynthSynthesizer

    ffmpeg = executable_path("ffmpeg.exe") or executable_path("ffmpeg")
    soundfont = resource_path("assets/soundfonts/default.sf2")
    fluidsynth = resource_path("bin/libfluidsynth-3.dll")
    missing = [
        name for name, path in (
            ("ffmpeg", Path(ffmpeg) if ffmpeg else None),
            ("soundfont", soundfont),
            ("fluidsynth", fluidsynth),
            ("basic_pitch_model", Path(ICASSP_2022_MODEL_PATH)),
        ) if path is None or not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"missing release resources: {', '.join(missing)}")

    ffmpeg_result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-version"], capture_output=True, text=True, timeout=30
    )
    if ffmpeg_result.returncode != 0:
        raise RuntimeError(ffmpeg_result.stderr.strip() or "FFmpeg self-test failed")

    synth = FluidSynthSynthesizer(np, 48_000, soundfont, fluidsynth)
    buffer = np.zeros((512, 2), dtype=np.float32)
    try:
        synth.note_on(60, 100)
        synth.render_into(buffer, 0, len(buffer))
        synth.note_off(60)
    finally:
        synth.close()
    peak = float(np.max(np.abs(buffer)))
    if peak <= 0.0:
        raise RuntimeError("FluidSynth rendered silence")
    return {
        "ffmpeg": ffmpeg_result.stdout.splitlines()[0],
        "fluidsynth_peak": peak,
        "soundfont_bytes": soundfont.stat().st_size,
        "model_bytes": Path(ICASSP_2022_MODEL_PATH).stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.self_test:
            emit({"type": "self_test", "ok": True, **release_self_test()})
            return 0
        missing = [
            name for name in ("audio", "output", "song_id", "audio_sha256", "duration_frames")
            if getattr(args, name) is None
        ]
        if missing:
            raise ValueError(f"missing required arguments: {', '.join(missing)}")
        chart, playable = analyze_audio(
            args.audio,
            song_id=args.song_id,
            audio_sha256=args.audio_sha256,
            duration_frames=args.duration_frames,
            progress=lambda stage, value: emit({"type": "progress", "stage": stage, "progress": value}),
        )
        save_chart_atomic(chart, args.output, backup=False)
        emit({"type": "result", "chart_path": str(args.output), "playable": playable})
        return 0
    except Exception as error:
        emit({"type": "error", "error_code": type(error).__name__, "detail": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
