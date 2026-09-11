# KeyRhythm 1.0

KeyRhythm 是一个面向 Windows 10/11 x64 的本地音乐键盘演奏游戏。音乐导入后在本机离线生成谱面；游玩时按键立即发声，错键会产生可听见的错误音高，错拍会按真实输入时机发声。

## 安装发布版

Git 仓库保存源码和构建说明，不包含安装包；下列文件由本地构建生成。

正式构建产物位于 `dist`：

- `KeyRhythm-Setup-1.0.0-x64.exe`：推荐，按当前 Windows 用户安装，不需要管理员权限。
- `KeyRhythm-1.0.0-windows-x64-portable.zip`：解压后直接运行 `KeyRhythm.exe`。
- `SHA256SUMS.txt`：下载或复制后用于验证文件完整性。

安装包已内置 Python、Qt、PortAudio、FFmpeg、FluidSynth、GeneralUser GS SoundFont、Basic Pitch ONNX 模型及分析依赖。目标电脑不需要预装 Python、FFmpeg 或 FluidSynth，安装后可离线完成 MP3/WAV/FLAC/M4A 导入、自动制谱、游玩、校谱和成绩保存。

安装位置固定为 `%LOCALAPPDATA%\Programs\KeyRhythm`。安装版和普通便携版的用户数据位于 `%LOCALAPPDATA%\KeyRhythm`；升级、卸载和重装不会删除歌曲、谱面、设置或成绩。`KEYRHYTHM_DATA_DIR` 环境变量仍拥有最高优先级。

当前安装包未使用商业代码签名证书，因此 Windows SmartScreen 可能显示“未知发布者”。这不影响程序功能；面向公众分发前建议由发布者使用自己的 Authenticode 证书签名安装器和两个主程序。

## 功能

- 版本化 SQLite 曲库、本地搜索和安全 staging 导入。
- `chart.json` schema v3、v2 自动迁移、备份和谱面修订。
- 按曲目音域动态生成 17/4/6/8 键谱面。
- 霓虹街机游戏界面、常驻键帽、判定偏差、连击和命中特效。
- Perfect/Good/Bad/Wrong/Miss、空击和长音释放判定。
- FFmpeg 48 kHz 双声道标准化、librosa 节拍分析和 Basic Pitch ONNX 音高分析。
- FluidSynth + SoundFont 琴声；开发环境缺少资源时仍保留正弦波回退。
- 校谱器、暂停/结算覆盖层、设置和设备诊断。

## 源码开发

发布基线是 Python 3.11 x64：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python tools\setup_environment.py
```

首次克隆后，先按下节准备本地运行资源，再执行完整测试和启动程序：

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m keyrhythm.cli gui
```

源码运行或从项目 `dist` 目录运行时会向上找到 `pyproject.toml`，继续使用项目根目录的 `data`，因此当前开发曲库仍保存在 D 盘项目内。安装到其他位置后才切换到 `%LOCALAPPDATA%\KeyRhythm`。

### 准备本地运行资源

Git 仓库不包含 FFmpeg、FluidSynth 动态库和 SoundFont。Python 依赖（含 Basic Pitch 的 ONNX 模型）由 `tools/setup_environment.py` 安装；该脚本不下载下表资源。

从 `release-assets.json` 中对应组件的 `archive_url` 下载归档，核对 `archive_sha256` 后解压，并按下表放置文件：

| 组件 | 项目内目标路径 |
| --- | --- |
| FFmpeg | `vendor/ffmpeg/ffmpeg.exe` |
| FluidSynth | `vendor/fluidsynth/libfluidsynth-3.dll` 和 `vendor/fluidsynth/sndfile.dll` |
| GeneralUser GS 1.471 | 将归档中的 `.sf2` 文件复制为 `assets/soundfonts/default.sf2` |

可以用 PowerShell 的 `Get-FileHash -Algorithm SHA256 <文件路径>` 校验下载文件。资源就位后，运行以下命令核对全部发布资产：

```powershell
.venv\Scripts\python -c "from tools.build_release import verify_assets; verify_assets(); print('Release assets verified')"
```

清单中的 FFmpeg 下载地址包含 `latest`，上游更新后可能与记录的哈希不一致；此时需要取得对应的历史构建，或在重新验证版本和许可证后更新清单，不应跳过哈希校验。各组件说明和许可证保存在 `vendor/*/README.md`、`assets/soundfonts/README.md` 和 `licenses/`。

完整测试中的 `tests/test_resources.py` 以及正式打包都要求上述资源存在。未准备资源时，可以运行 `.venv\Scripts\python -m pytest -q --ignore=tests/test_resources.py` 检查其余测试；音频导入需要可用的 FFmpeg，缺少 SoundFont 时开发模式使用正弦波回退。

### Git 同步范围

仓库保留 `src/`、`tests/`、`tools/`、打包配置、依赖清单、应用图标、设计与验收文档和第三方许可证。`.gitignore` 排除本地 Python 环境、缓存、开发工具、`build/`、`dist/`、下载的运行资源及凭据文件。

`data/` 中的歌曲、谱面、成绩和设置属于本地用户数据，不会上传到 GitHub。忽略规则只影响版本管理，不会删除本地文件。安装器和便携包适合另行作为 GitHub Release 附件分发。

## 生成发布包

发布资源版本和 SHA-256 固定在 `release-assets.json`。准备好 Python 3.11 x64 环境和 NSIS 3.11+ 后运行：

```powershell
.venv\Scripts\python tools\collect_python_licenses.py
.venv\Scripts\python tools\build_release.py
```

构建会执行全部测试、资源哈希审计、PyInstaller 双程序冻结、冻结 worker 资源自检、GUI 启动检查、便携 ZIP 和 NSIS 安装器生成，并输出 `release-report.json` 与 `SHA256SUMS.txt`。

第三方组件、来源和许可证见 `THIRD_PARTY_LICENSES.md` 与随包 `licenses` 目录。用户只能导入自己有权使用的音频；商业歌曲不得随 KeyRhythm 安装包分发。
