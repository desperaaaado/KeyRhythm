from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _default_data_root() -> Path:
    if getattr(sys, "frozen", False):
        runtime_directory = Path(sys.executable).resolve().parent
    else:
        runtime_directory = Path(__file__).resolve().parents[2]

    for candidate in (runtime_directory, *runtime_directory.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate / "data"

    # An installed build normally lives below Program Files or
    # %LOCALAPPDATA%\Programs.  Application files may be replaced or removed
    # during upgrades, so the library must never be stored beside the EXE.
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / "KeyRhythm"
    return Path.home() / "AppData" / "Local" / "KeyRhythm"


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    database: Path
    settings: Path
    library: Path
    staging: Path
    logs: Path
    models: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        override = os.environ.get("KEYRHYTHM_DATA_DIR")
        if override:
            root = Path(override).expanduser().resolve()
        else:
            root = _default_data_root()
        return cls(
            root=root,
            database=root / "keyrhythm.db",
            settings=root / "settings.json",
            library=root / "library",
            staging=root / "staging",
            logs=root / "logs",
            models=root / "models",
        )

    def ensure(self) -> None:
        for path in (self.root, self.library, self.staging, self.logs, self.models):
            path.mkdir(parents=True, exist_ok=True)


CHART_SAMPLE_RATE = 48_000
