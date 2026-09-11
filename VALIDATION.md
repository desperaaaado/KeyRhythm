# KeyRhythm 1.0 实现与验收记录

最后更新：2026-08-17

## 本次正式构建已通过

| 项目 | 环境 | 结果 |
| --- | --- | --- |
| 单元与 Qt 交互测试 | Python 3.11.15 x64 | 38/38 通过 |
| 发布资产审计 | `release-assets.json` | FFmpeg、FluidSynth、libsndfile、SoundFont、图标和许可证哈希全部通过 |
| FluidSynth 真实渲染 | FluidSynth 2.6.0 + GeneralUser GS 1.471 | MIDI 60 渲染峰值 `0.045985`，不是正弦回退或静音 |
| FFmpeg | 随包 LGPL x64 构建 | `ffmpeg -version` 启动通过，MP3/WAV/FLAC/M4A 标准化路径可用 |
| Basic Pitch 冻结 worker 自检 | `KeyRhythmWorker.exe --self-test` | ONNX 模型、FFmpeg、FluidSynth 和 SoundFont 全部可定位并加载 |
| Basic Pitch 冻结 worker 实际分析 | 内置合法练习曲 | 完成 beat、transcription、melody selection，生成 schema v3、16 音符，`playable=true` |
| 冻结 GUI | `QT_QPA_PLATFORM=offscreen` | 项目 dist 和隔离安装目录均保持运行 10 秒，无启动崩溃 |
| 安装文件完整性 | NSIS 3.12 按用户安装 | GUI、worker、FFmpeg、FluidSynth、libsndfile、SoundFont 7 个关键项存在 |
| 安装与卸载 | 项目内隔离目录 | 静默安装、启动、自检、卸载成功；安装目录删除，外部用户数据标记保留 |
| PyInstaller | Python 3.11 x64 | 双可执行文件 onedir 构建成功，带应用图标和 1.0.0 版本资源 |
| 安装器 | NSIS 3.12 | 生成约 176 MiB 的无需管理员权限安装器，无编译警告 |
| 便携包 | ZIP | 生成约 244 MiB 的完整离线包 |
| 动态映射与迁移 | schema v2→v3 | 端点、单音、稀疏/密集音域、重复音、和弦冲突、备份和 revision 测试通过 |
| 游戏视觉反馈 | 4/6/8/17 键 | 键帽按下/释放、Perfect、Miss、暂停清理和三种窗口尺寸渲染通过 |
| 画布性能 | 5,000 音符、1280×600、180 帧 | 历史实测平均 4.81 ms，P95 5.41 ms，通过 8 ms 门槛 |
| 音频输出探针 | Windows WASAPI，48 kHz | 历史实测设备报告延迟 22.0 ms，2 秒内 0 xrun、0 队列溢出、0 削波 |

发布构建详情和最终文件哈希分别见 `dist/release-report.json` 与 `dist/SHA256SUMS.txt`。

## 用户数据安全

- 源码或项目 `dist` 内运行：使用项目根目录 `data`，现有 D 盘曲库保持不变。
- 从安装位置或普通便携目录运行：使用 `%LOCALAPPDATA%\KeyRhythm`。
- `KEYRHYTHM_DATA_DIR` 始终拥有最高优先级。
- 安装器只删除 `%LOCALAPPDATA%\Programs\KeyRhythm` 下的程序文件；卸载脚本不删除用户曲库、谱面、成绩、设置和日志。

## 仍需发布者或独立环境签收

下列项目依赖发布者身份、额外硬件、合法测试内容或独立 Windows 环境，本机自动化不能替代：

- 使用发布者自己的 Authenticode 证书签名 `KeyRhythm.exe`、`KeyRhythmWorker.exe` 和最终安装器；当前产物功能完整但会显示“未知发布者”。
- 在未安装 Python、FFmpeg、FluidSynth 且没有本项目源码的干净 Windows 10/11 x64 虚拟机，手工走完安装、四格式导入、游玩、校谱、升级、卸载、重装流程。
- 用真实音频回环设备验证物理按键到扬声器 P95 不超过 35 ms；PortAudio 报告延迟不能替代该测量。
- 连续播放 30 分钟，记录累计漂移、回调负载和 xrun。
- 使用至少 20 首具有合法测试权限的多类型歌曲完成人工谱面质量抽检。
- 如果用于高风险商业发行，针对 GeneralUser GS 许可证中披露的历史样本来源不确定性完成额外权利审查，或更换 SoundFont。

这些项目不会阻止安装包在其他 Windows x64 电脑离线运行，但在对外宣称经过签名、商业权利完全审计或达到物理延迟 SLA 之前不能标记为已签收。
