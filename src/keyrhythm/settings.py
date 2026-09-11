from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    output_device: str = ""
    backing_volume: int = 70
    instrument_volume: int = 90
    master_volume: int = 80
    judgement_offset_frames: int = 0
    visual_offset_frames: int = 0
    piano_base_pitch: int = 48

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            allowed = {field for field in cls.__dataclass_fields__}
            return cls(**{key: value for key, value in raw.items() if key in allowed})
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

