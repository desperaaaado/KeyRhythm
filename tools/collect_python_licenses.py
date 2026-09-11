from __future__ import annotations

import importlib.metadata
import json
import re
import shutil
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "licenses" / "python"
LICENSE_NAME = re.compile(r"(^|/)(licen[sc]e|copying|notice|authors?)([._-].*)?$", re.IGNORECASE)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unknown"


def main() -> int:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    manifest: list[dict[str, object]] = []
    for distribution in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata.get("Name", "").lower()):
        name = distribution.metadata.get("Name", "unknown")
        version = distribution.version
        target = OUTPUT / f"{safe_name(name)}-{safe_name(version)}"
        copied: list[str] = []
        for entry in distribution.files or ():
            normalized = str(entry).replace("\\", "/")
            if not LICENSE_NAME.search(normalized):
                continue
            source = distribution.locate_file(entry)
            if not source.is_file() or source.stat().st_size > 2_000_000:
                continue
            target.mkdir(exist_ok=True)
            destination = target / safe_name(Path(normalized).name)
            if destination.exists():
                continue
            shutil.copy2(source, destination)
            copied.append(destination.name)
        manifest.append({
            "name": name,
            "version": version,
            "license_expression": distribution.metadata.get("License-Expression"),
            "license_metadata": distribution.metadata.get("License"),
            "home_page": distribution.metadata.get("Home-page") or distribution.metadata.get("Project-URL"),
            "license_files": copied,
        })
    (OUTPUT / "PYTHON_PACKAGES.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
