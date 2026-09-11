# Build with: pyinstaller --noconfirm keyrhythm.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

app_hiddenimports = collect_submodules("sounddevice") + collect_submodules("soundfile")
worker_hiddenimports = [
    "basic_pitch.inference",
    "basic_pitch.note_creation",
    "librosa.beat",
    "librosa.core",
    "onnxruntime",
    "resampy",
    "soundfile",
]
analysis_datas = collect_data_files("basic_pitch")
project = Path(SPEC).resolve().parent
extra_binaries = []
extra_datas = []
for source, destination in [
    (project / "vendor" / "ffmpeg" / "ffmpeg.exe", "bin"),
    *[(path, "bin") for path in sorted((project / "vendor" / "fluidsynth").glob("*.dll"))],
]:
    if source.is_file():
        extra_binaries.append((str(source), destination))
soundfont = project / "assets" / "soundfonts" / "default.sf2"
if soundfont.is_file():
    extra_datas.append((str(soundfont), "assets/soundfonts"))
extra_datas.extend([
    (str(project / "licenses"), "licenses"),
    (str(project / "THIRD_PARTY_LICENSES.md"), "."),
    (str(project / "README.md"), "."),
])
version_file = str(project / "packaging" / "version_info.txt")
icon_file = str(project / "assets" / "keyrhythm.ico") if (project / "assets" / "keyrhythm.ico").is_file() else None

a_app = Analysis(
    ["src/keyrhythm/app.py"],
    pathex=["src"],
    binaries=extra_binaries,
    datas=extra_datas,
    hiddenimports=app_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["demucs"],
    noarchive=False,
)
pyz_app = PYZ(a_app.pure)
exe_app = EXE(
    pyz_app,
    a_app.scripts,
    [],
    exclude_binaries=True,
    name="KeyRhythm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    version=version_file,
    icon=icon_file,
)

a_worker = Analysis(
    ["src/keyrhythm/analysis/worker.py"],
    pathex=["src"],
    binaries=extra_binaries,
    datas=analysis_datas + extra_datas,
    hiddenimports=worker_hiddenimports,
    runtime_hooks=["tools/pyinstaller_rth_numba.py"],
    excludes=["PySide6", "demucs"],
    noarchive=False,
)
pyz_worker = PYZ(a_worker.pure)
exe_worker = EXE(
    pyz_worker,
    a_worker.scripts,
    [],
    exclude_binaries=True,
    name="KeyRhythmWorker",
    debug=False,
    strip=False,
    upx=True,
    console=True,
    version=version_file,
    icon=icon_file,
)
coll = COLLECT(
    exe_app, exe_worker,
    a_app.binaries, a_app.datas,
    a_worker.binaries, a_worker.datas,
    strip=False, upx=True, name="KeyRhythm",
)
