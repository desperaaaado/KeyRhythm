from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def run(*arguments: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", *arguments], cwd=PROJECT, check=True)


def write_lock() -> None:
    rows: list[str] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "").strip()
        if not name or name.lower() in {"keyrhythm", "pip", "wheel"}:
            continue
        rows.append(f"{name}=={distribution.version}")
    rows = sorted(set(rows), key=str.casefold)
    (PROJECT / "requirements.lock").write_text(
        "# Generated for Python 3.11 x64 by tools/setup_environment.py\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-only", action="store_true")
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 11) or sys.maxsize <= 2**32:
        raise SystemExit("KeyRhythm's supported environment is Python 3.11 x64")
    if args.lock_only:
        write_lock()
        return 0
    # resampy 0.4.2 still imports pkg_resources, removed in newer setuptools.
    run("install", "--upgrade", "pip", "setuptools>=75,<81", "wheel")
    run("install", "-e", ".[app,analysis,dev]")
    # Basic Pitch 0.4.0 declares TensorFlow for Python 3.11. Its Windows ONNX
    # backend works with the explicitly installed dependencies in `analysis`.
    run("install", "--no-deps", "basic-pitch==0.4.0")
    write_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
