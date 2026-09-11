from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
ASSET_MANIFEST = PROJECT / "release-assets.json"


def fail(message: str) -> None:
    raise SystemExit(f"release preflight failed: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def run(command: list[str], *, env: dict[str, str] | None = None, timeout: int | None = None) -> None:
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=PROJECT, env=env, timeout=timeout, check=True)


def verify_assets() -> dict[str, object]:
    manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = PROJECT / item["path"]
        if not path.is_file():
            fail(f"required release asset is missing: {item['path']}")
        actual = sha256(path)
        if actual != item["sha256"].upper():
            fail(f"checksum mismatch for {item['path']}: expected {item['sha256']}, got {actual}")
    return manifest


def find_makensis() -> Path | None:
    configured = os.environ.get("MAKENSIS")
    on_path = shutil.which("makensis.exe")
    candidates = [
        Path(configured) if configured else None,
        PROJECT / ".keyrhythm-dev" / "nsis" / "tools" / "Bin" / "makensis.exe",
        Path(on_path) if on_path else None,
    ]
    return next((path for path in candidates if path and path.is_file()), None)


def smoke_test(dist: Path, env: dict[str, str]) -> dict[str, object]:
    worker = dist / "KeyRhythmWorker.exe"
    gui = dist / "KeyRhythm.exe"
    ffmpeg = dist / "_internal" / "bin" / "ffmpeg.exe"
    for path in (worker, gui, ffmpeg):
        if not path.is_file():
            fail(f"frozen output is missing: {path.relative_to(PROJECT)}")

    self_test = subprocess.run(
        [str(worker), "--self-test"], cwd=dist, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if self_test.returncode != 0:
        fail(f"worker self-test failed: {self_test.stdout}\n{self_test.stderr}")
    payload = json.loads(self_test.stdout.strip().splitlines()[-1])
    if not payload.get("ok"):
        fail(f"worker self-test returned an invalid result: {payload}")

    ffmpeg_test = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-version"], cwd=dist,
        capture_output=True, text=True, timeout=30,
    )
    if ffmpeg_test.returncode != 0:
        fail("bundled FFmpeg did not start")

    process = subprocess.Popen([str(gui)], cwd=dist, env=env)
    try:
        time.sleep(10)
        if process.poll() is not None:
            fail(f"frozen GUI exited during startup smoke test with code {process.returncode}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return payload


def write_checksums(paths: list[Path], output: Path) -> None:
    rows = [f"{sha256(path)}  {path.name}" for path in paths]
    output.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify the KeyRhythm Windows release")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--no-installer", action="store_true")
    args = parser.parse_args(argv)

    if sys.version_info[:2] != (3, 11) or sys.maxsize <= 2**32:
        fail("use Python 3.11 x64")
    required_modules = (
        "PySide6", "numpy", "sounddevice", "soundfile", "librosa",
        "basic_pitch", "onnxruntime", "PyInstaller", "pytest",
    )
    missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
    if missing:
        fail(f"missing modules: {', '.join(missing)}")

    manifest = verify_assets()
    project_metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project_metadata["project"]["version"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT / "src")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    run([sys.executable, str(PROJECT / "tools" / "collect_python_licenses.py")], env=env, timeout=60)
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q"], env=env, timeout=600)
    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "keyrhythm.spec"], env=env, timeout=3600)

    dist = PROJECT / "dist" / "KeyRhythm"
    with tempfile.TemporaryDirectory(prefix="keyrhythm-release-smoke-") as temporary:
        smoke_env = env.copy()
        smoke_env["LOCALAPPDATA"] = str(Path(temporary) / "LocalAppData")
        smoke_env.pop("KEYRHYTHM_DATA_DIR", None)
        self_test = smoke_test(dist, smoke_env)

    portable_base = PROJECT / "dist" / f"KeyRhythm-{version}-windows-x64-portable"
    portable_zip = Path(shutil.make_archive(str(portable_base), "zip", root_dir=dist))
    artifacts = [portable_zip]

    installer = PROJECT / "dist" / f"KeyRhythm-Setup-{version}-x64.exe"
    if not args.no_installer:
        makensis = find_makensis()
        if not makensis:
            fail("makensis.exe was not found; set MAKENSIS or install NSIS 3.11+")
        run([
            str(makensis),
            f"/DAPP_VERSION={version}",
            f"/DDIST_DIR={dist}",
            f"/DOUT_FILE={installer}",
            str(PROJECT / "packaging" / "keyrhythm.nsi"),
        ], timeout=3600)
        if not installer.is_file():
            fail("NSIS completed without creating the installer")
        artifacts.append(installer)

    checksums = PROJECT / "dist" / "SHA256SUMS.txt"
    write_checksums(artifacts, checksums)
    report = {
        "version": version,
        "platform": "Windows 10/11 x64",
        "artifacts": [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in artifacts],
        "bundled_assets": manifest["components"],
        "self_test": self_test,
        "code_signed": False,
    }
    (PROJECT / "dist" / "release-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
