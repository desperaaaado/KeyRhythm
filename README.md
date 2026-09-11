# KeyRhythm

面向 **Windows 10/11 x64** 的本地音乐键盘演奏游戏。导入音乐后在本机离线生成谱面；游玩时按键立即发声，错键会产生错误音高，错拍会按真实输入时机发声。

**[下载 v1.0.0](https://github.com/desperaaaado/KeyRhythm/releases/tag/v1.0.0)** · **[反馈问题](https://github.com/desperaaaado/KeyRhythm/issues)**

## 下载并运行

普通玩家无需安装 Python，也无需下载源码。选择一种方式：

| 下载 | 使用方法 |
| --- | --- |
| [Windows 安装器（约 176 MiB）](https://github.com/desperaaaado/KeyRhythm/releases/download/v1.0.0/KeyRhythm-Setup-1.0.0-x64.exe) | 运行安装器，完成后从开始菜单启动 KeyRhythm；按当前用户安装，无需管理员权限。 |
| [Windows 便携包（约 244 MiB）](https://github.com/desperaaaado/KeyRhythm/releases/download/v1.0.0/KeyRhythm-1.0.0-windows-x64-portable.zip) | **完整解压**到一个文件夹，双击 `KeyRhythm.exe`。保留同目录的 `KeyRhythmWorker.exe` 和 `_internal/`，不能只复制主程序。 |
| [SHA256SUMS.txt](https://github.com/desperaaaado/KeyRhythm/releases/download/v1.0.0/SHA256SUMS.txt) | 下载校验清单；可用 `Get-FileHash -Algorithm SHA256 .\下载的文件名` 核对。 |

安装器和便携包均包含 Python、Qt、PortAudio、FFmpeg、FluidSynth、GeneralUser GS SoundFont、Basic Pitch ONNX 模型及分析依赖。下载完成后，导入、制谱、游玩、校谱和成绩保存均可离线进行。Releases 自动生成的 **Source code** 压缩包是开发源码，不是可直接运行的便携包。

启动后可先游玩内置练习曲，再导入自己有权使用的 MP3/WAV/FLAC/M4A 文件，等待分析完成后选择曲目和难度开始演奏。首次分析可能因模型加载和编译耗时较长。

当前版本未进行 Authenticode 代码签名，Windows 可能显示“未知发布者”。请从本仓库 Releases 下载并核对校验和；若设备策略禁止运行未签名应用，需要遵循设备管理策略。

安装位置为 `%LOCALAPPDATA%\Programs\KeyRhythm`。安装版与普通便携版的用户数据位于 `%LOCALAPPDATA%\KeyRhythm`；升级、卸载和重装不会删除曲库、谱面、设置或成绩。`KEYRHYTHM_DATA_DIR` 环境变量可指定其他数据目录。

## 功能

- SQLite 曲库、本地搜索和 staging 导入。
- MP3/WAV/FLAC/M4A 标准化，librosa 节拍分析与 Basic Pitch ONNX 音高分析。
- 按曲目音域动态生成 17/4/6/8 键谱面，支持长音与 Perfect/Good/Bad/Wrong/Miss 判定。
- FluidSynth + SoundFont 琴声、按键与命中特效、暂停和结算界面。
- 校谱器、谱面修订与备份、设置及设备诊断。

## 从源码运行和开发

要求：Windows 10/11 x64、**Python 3.11 x64**、Git，以及首次安装时能访问 PyPI 和 GitHub 的网络。当前发布流程仅验证 Windows x64；Python 3.12+、Windows ARM 和其他操作系统不在本版本支持范围内。

在 PowerShell 中依次运行（任一步报错时，先处理该错误）：

```powershell
git clone https://github.com/desperaaaado/KeyRhythm.git
cd KeyRhythm
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe tools\setup_environment.py
.\.venv\Scripts\python.exe tools\runtime_assets.py
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m keyrhythm.analysis.worker --self-test
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m keyrhythm.cli gui
```

无需激活虚拟环境。如果 `py` 不存在，改用已安装的 Python 3.11 x64 的 `python.exe` 完整路径创建虚拟环境。

`setup_environment.py` 安装 `requirements.lock` 中经过验证的固定版本及可编辑项目，不会重写锁定文件。Basic Pitch 0.4.0 的依赖元数据默认声明 TensorFlow，本项目使用 ONNX 后端，脚本会通过 `--no-deps` 安装锁定的完整依赖集，因此不要直接用 `pip install basic-pitch` 或普通的 `pip install -r requirements.lock` 替代该脚本。Basic Pitch 的 ONNX 模型由其 Python 包提供。

`runtime_assets.py` 从本仓库 v1.0.0 Release 下载固定的开发资源包，校验整个 ZIP 和每个运行文件的 SHA-256 后安装到：

| 资源 | 目标路径 |
| --- | --- |
| FFmpeg | `vendor/ffmpeg/ffmpeg.exe` |
| FluidSynth / libsndfile | `vendor/fluidsynth/libfluidsynth-3.dll`、`vendor/fluidsynth/sndfile.dll` |
| GeneralUser GS 1.471 | `assets/soundfonts/default.sf2` |

重复运行时，已通过校验的资源不会重新下载。也可以先手动下载 [开发资源包](https://github.com/desperaaaado/KeyRhythm/releases/download/v1.0.0/KeyRhythm-1.0.0-windows-x64-runtime.zip)，再指定本地文件：

```powershell
.\.venv\Scripts\python.exe tools\runtime_assets.py --archive C:\Downloads\KeyRhythm-1.0.0-windows-x64-runtime.zip
.\.venv\Scripts\python.exe tools\runtime_assets.py --verify-only
```

开发资源包只包含外部运行资源与第三方许可证，**不包含 Python 虚拟环境**。源码依赖首次安装需要联网；完整安装后的源码应用可以离线运行。

源码运行时，项目根目录下自动生成 `data/`，用于曲库、谱面、成绩和设置。该目录不进入 Git。无界面环境测试可先设置 `$env:QT_QPA_PLATFORM='offscreen'`；交互启动 GUI 前请用 `Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue` 清除该变量。

## 构建 Windows 安装包

先完成上面的源码环境准备与资源自检，然后安装 NSIS 3.11+（[NSIS 官方下载](https://nsis.sourceforge.io/Download)）。如 `makensis.exe` 不在 PATH，可显式设置路径：

```powershell
$env:MAKENSIS='C:\Program Files (x86)\NSIS\makensis.exe'
.\.venv\Scripts\python.exe tools\build_release.py
```

只生成便携版、不使用 NSIS：

```powershell
.\.venv\Scripts\python.exe tools\build_release.py --no-installer
```

构建会收集第三方许可证、执行测试和资源校验、用 PyInstaller 冻结主程序及分析 worker、执行启动自检，再输出 `dist/` 下的便携 ZIP、安装器、`release-report.json` 与 `SHA256SUMS.txt`。请预留足够磁盘空间并等待构建完成。

发布开发资源包时可运行：

```powershell
.\.venv\Scripts\python.exe tools\runtime_assets.py --build dist\KeyRhythm-1.0.0-windows-x64-runtime.zip
```

更新资源版本时应重新验证组件、更新 `release-assets.json` 中的 URL/哈希，并发布新的版本附件。历史上游下载地址仅用于来源记录；日常开发使用本仓库固定版本的 Release 资源包。

## 仓库内容与问题排查

- `src/`：应用源码；`tests/`：测试；`tools/`：安装、验证和打包工具。
- `packaging/`、`keyrhythm.spec`：NSIS 与 PyInstaller 配置。
- `requirements.lock`、`release-assets.json`：Python 依赖及运行资源基线。
- `licenses/`、[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)：第三方来源与许可证。
- [VALIDATION.md](VALIDATION.md)：历史验收记录及仍需独立环境验证的项目。

Git 不保存曲库、凭据、Python 环境、缓存或构建产物；安装器、便携版和开发资源包存放在 Releases。已有本地文件不会因 `.gitignore` 而删除。

遇到问题时，先运行 worker `--self-test` 和资源 `--verify-only`。导入失败时确认完整解压了便携包或安装了源码资源；没有声音时检查系统输出设备和应用音量。可在 Issues 中提供版本、Windows 版本、复现步骤和相关日志片段。日志位于用户数据目录的 `logs/`，请移除私人路径及曲目信息后再分享。

项目当前保留 `pyproject.toml` 中的 “All rights reserved” 声明；仓库公开不等同于另行授予开源许可证。第三方组件遵循各自许可证。请仅导入自己有权使用的音频，个人曲库不随发布包分发。
