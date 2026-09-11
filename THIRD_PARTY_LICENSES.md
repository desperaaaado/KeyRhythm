# KeyRhythm third-party notices

KeyRhythm 1.0 的 Windows 发布包包含下列第三方组件。完整的通用许可证文本位于 `licenses`，Python 分发包自带的许可证和元数据汇总在 `licenses/python`。本清单是工程记录，不替代任何许可证原文或法律意见。

| 组件 | 固定版本/构建 | 许可证 | 来源与发布用途 |
| --- | --- | --- | --- |
| FFmpeg | `n8.1.2-44-g7c533d0f86-20260817`, BtbN win64 LGPL static | LGPL-3.0-or-later；所选构建排除 GPL-only 与 nonfree 变体 | [BtbN FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds)，作为独立 `ffmpeg.exe` 进程进行音频解码和标准化 |
| FluidSynth | 2.6.0 win10-x64-cpp11 | LGPL-2.1-or-later | [FluidSynth v2.6.0](https://github.com/FluidSynth/fluidsynth/releases/tag/v2.6.0)，动态加载 `libfluidsynth-3.dll` |
| libsndfile | FluidSynth 2.6.0 Windows 包所带运行库 | LGPL-2.1-or-later | 作为 `libfluidsynth-3.dll` 的同目录动态依赖 `sndfile.dll` |
| GeneralUser GS | 1.471 | GeneralUser GS License v2.0 | [作者页面](https://www.schristiancollins.com/generaluser.php)，随包 `default.sf2`；许可证允许软件项目使用和修改 |
| Basic Pitch | 0.4.0，ONNX 后端 | Apache-2.0 | [Spotify Basic Pitch](https://github.com/spotify/basic-pitch)，只在导入分析 worker 中运行 |
| ONNX Runtime | 1.28.0 | MIT | [Microsoft ONNX Runtime](https://github.com/microsoft/onnxruntime) |
| Qt / PySide6 / Shiboken6 | 6.11.1 | LGPL-3.0/GPL/商业多重许可；本构建按 LGPL-3.0 使用动态库 | [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html) |
| Python | 3.11.15 | PSF License | [Python](https://www.python.org/) |
| NumPy / SciPy / scikit-learn / librosa / resampy | 见 `requirements.lock` | BSD/ISC 等宽松许可证 | 自动制谱与实时音频数值处理 |
| sounddevice / PortAudio | 0.5.5 / 随 wheel 版本 | MIT | Windows 音频输出 |
| python-soundfile | 0.14.0 | BSD-3-Clause | WAV 读取；其 libsndfile 运行库遵循 LGPL |
| PyInstaller | 6.21.0 | GPL-2.0-or-later with bootloader exception | 仅用于生成可再分发冻结程序 |
| NSIS | 3.12 | zlib/libpng 等（构建工具及安装器 stub） | [NSIS](https://nsis.sourceforge.io/)，用于生成安装器 |

## 固定资产校验

准确的下载 URL、发布包 SHA-256 与仓库内文件 SHA-256 记录在 `release-assets.json`。发布构建在任何文件缺失或哈希变化时都会失败。

## LGPL 可替换性与源码

Qt、FluidSynth 和 libsndfile 以独立动态库随 PyInstaller onedir 目录发布，用户可以在接口兼容的前提下替换这些库。FFmpeg 是由 KeyRhythm 通过命令行调用的独立程序。对应上游源码、构建脚本和配置可从上表链接及 `release-assets.json` 中记录的版本取得；不得对许可证允许的逆向工程和替换施加额外限制。

## SoundFont 说明

GeneralUser GS License v2.0 允许将音色库用于软件项目，同时原作者在许可证中说明部分历史样本来源无法做到 100% 追溯。许可证原文已原样包含在 `licenses/GeneralUser-GS-2.0.txt`。如果发布者计划进行高风险商业发行，应自行完成额外权利审查或替换为具有所需来源保证的 SoundFont。
