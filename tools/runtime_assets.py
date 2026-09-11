"""Build or install the checksum-pinned Windows runtime bundle (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = (
    "vendor/ffmpeg/ffmpeg.exe",
    "vendor/fluidsynth/libfluidsynth-3.dll",
    "vendor/fluidsynth/sndfile.dll",
    "assets/soundfonts/default.sf2",
)


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def verify(project: Path, manifest: dict) -> None:
    for item in manifest["files"]:
        path = project / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"].upper():
            raise ValueError(f"Missing or checksum mismatch: {item['path']}")


def build_bundle(project: Path, manifest: dict, output: Path) -> None:
    verify(project, manifest)
    names = set(RUNTIME_PATHS)
    names.update(path.relative_to(project).as_posix() for path in (project / "licenses").rglob("*") if path.is_file())
    names.update(("THIRD_PARTY_LICENSES.md", "vendor/ffmpeg/README.md", "vendor/fluidsynth/README.md", "assets/soundfonts/README.md"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (project / name).read_bytes())
    print(f"{sha256(output)}  {output.name}")


def install_bundle(project: Path, manifest: dict, archive_path: Path) -> None:
    if sha256(archive_path) != manifest["runtime_bundle"]["sha256"].upper():
        raise ValueError("Runtime bundle SHA-256 mismatch; no files installed")
    expected = {item["path"]: item["sha256"].upper() for item in manifest["files"]}
    root = project.resolve()
    # Extract only the explicit runtime allowlist, never arbitrary ZIP paths.
    with tempfile.TemporaryDirectory(prefix="keyrhythm-assets-") as directory:
        staging = Path(directory)
        with zipfile.ZipFile(archive_path) as archive:
            for name in RUNTIME_PATHS:
                if archive.namelist().count(name) != 1:
                    raise ValueError(f"Missing or duplicate archive member: {name}")
                if not (project / name).resolve().is_relative_to(root):
                    raise ValueError(f"Runtime destination leaves project: {name}")
                staged = staging / name
                staged.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, staged.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if sha256(staged) != expected[name]:
                    raise ValueError(f"Runtime file SHA-256 mismatch: {name}")
        # Verify every member before changing any existing runtime asset.
        for name in RUNTIME_PATHS:
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
                pending = Path(handle.name)
                try:
                    with (staging / name).open("rb") as source:
                        shutil.copyfileobj(source, handle)
                except BaseException:
                    handle.close()
                    pending.unlink(missing_ok=True)
                    raise
            try:
                os.replace(pending, destination)
            finally:
                pending.unlink(missing_ok=True)
    verify(project, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build", type=Path, metavar="ZIP", help="package local assets for a release")
    group.add_argument("--archive", type=Path, help="install an already downloaded bundle")
    group.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((PROJECT / "release-assets.json").read_text(encoding="utf-8"))
    if args.build:
        build_bundle(PROJECT, manifest, args.build)
    elif args.verify_only:
        verify(PROJECT, manifest)
        print("All release assets verified.")
    elif args.archive:
        install_bundle(PROJECT, manifest, args.archive)
        print("Runtime assets installed and verified.")
    else:
        try:
            verify(PROJECT, manifest)
        except ValueError:
            with tempfile.TemporaryDirectory(prefix="keyrhythm-download-") as directory:
                archive_path = Path(directory) / "runtime.zip"
                url = manifest["runtime_bundle"]["url"]
                print(f"Downloading {url}", flush=True)
                request = urllib.request.Request(url, headers={"User-Agent": "KeyRhythm-setup/1.0"})
                with urllib.request.urlopen(request, timeout=120) as source, archive_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                install_bundle(PROJECT, manifest, archive_path)
            print("Runtime assets installed and verified.")
        else:
            print("All release assets already verified; no download needed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(f"Runtime setup failed: {error}") from error
