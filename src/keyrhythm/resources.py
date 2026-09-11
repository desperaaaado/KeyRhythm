from __future__ import annotations

import shutil
import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base) / relative

    project = Path(__file__).resolve().parents[2]
    direct = project / relative
    if direct.is_file():
        return direct
    name = Path(relative).name
    if relative.startswith("bin/"):
        for directory in (project / "vendor" / "ffmpeg", project / "vendor" / "fluidsynth"):
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return direct


def executable_path(name: str) -> str | None:
    bundled = resource_path(f"bin/{name}")
    if bundled.is_file():
        return str(bundled)
    return shutil.which(name)
