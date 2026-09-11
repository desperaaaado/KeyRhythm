# KeyRhythm 具体实现方案

> 文档版本：1.3  
> 目标平台：Windows 10/11  
> 项目定位：可安装、离线可用的 Windows 1.0 版本  
> 首版技术栈：Python 3.11 x64 桌面应用  
> 文档目的：作为后续 Codex 实施、拆分任务和验收的唯一基线

> 1.3 发布状态（2026-08-17）：FFmpeg、FluidSynth、SoundFont、Basic Pitch 模型及 Python/Qt 运行时已经随包提供；NSIS 按用户安装器、固定资产哈希审计、冻结 worker 自检、安装/卸载和用户数据保留验收已实现。安装包目前未做商业 Authenticode 签名，真实物理回环、30 分钟连续运行、20 首合法曲目人工抽检和独立干净虚拟机仍属于发布者签收项。

## 1. 项目目标

KeyRhythm 是一款使用电脑键盘模拟音乐演奏的单机音乐游戏。应用维护一个本地歌曲曲库；歌曲进入曲库时离线分析节拍和旋律并生成谱面，游玩时直接加载已经生成的谱面，因此不需要在演奏过程中等待 AI 分析。

玩家可以：

- 在本地曲库中按标题、艺术家和标签搜索歌曲。
- 游玩预置歌曲，或导入自己的 MP3、WAV、FLAC、M4A 文件。
- 使用按曲目动态音高映射的“17 键旋律”或 4/6/8 键轨道模式演奏。
- 在游玩中分别调整原曲、玩家琴声和总输出音量。
- 听到自己实际按下的音符：错键会走音，提前或延后按键会在听感上错拍。
- 查看 Perfect、Good、Bad、Miss、连击和准确率。
- 对自动生成的不准确谱面进行试听和简单修改。

首版不实现：

- 捕获其他播放器正在播放的系统音频。
- Spotify、YouTube、Apple Music 等商业平台歌曲下载或音频分析。
- 在线账号、联网排行榜、多人游戏和云端曲库。
- 对任意歌曲承诺完全准确的全自动主旋律提取。

## 2. 核心产品决策

### 2.1 歌曲先入库、后游玩

所有歌曲必须先进入 KeyRhythm 曲库。导入阶段完成：

1. 校验文件和计算 SHA-256，避免重复导入。
2. 读取或填写标题、艺术家、封面和标签。
3. 使用 FFmpeg 转换为统一的 48 kHz、双声道 PCM WAV 工作文件。
4. 检测节拍、速度和候选旋律音符。
5. 生成动态 17 键旋律模式与 4/6/8 键轨道模式谱面。
6. 保存分析版本、置信度和编辑结果。

预置曲库也使用完全相同的数据结构，只是音频、谱面和元数据由开发者提前制作并随应用或独立歌曲包提供。

### 2.2 原曲与玩家琴声独立控制

音频系统固定包含三个逻辑总线：

- `backing_bus`：原曲或弱化主旋律后的练习伴奏。
- `instrument_bus`：玩家通过键盘触发的合成乐器声音。
- `master_bus`：前两条总线混合后的最终输出。

游戏界面和暂停菜单均提供三个滑块：

- 原曲音量：0–100，默认 70。
- 玩家琴声音量：0–100，默认 90。
- 总音量：0–100，默认 80。

音量数值使用感知更自然的平方曲线转换为线性增益：

```python
def slider_to_gain(value: int) -> float:
    normalized = max(0.0, min(1.0, value / 100.0))
    return normalized * normalized
```

实现约束：

- 音量滑块只改变混音增益，不得影响判定、谱面时钟或录制的成绩。
- 增益改变在 20 ms 内线性平滑，避免拖动滑块时产生爆音或拉链噪声。
- 混音时预留约 6 dB 余量；最终输出限制在 `[-1.0, 1.0]`，并记录削波次数供调试。
- 设置页保存全局默认音量；歌曲表保存可选的单曲覆盖值。
- 单曲没有覆盖值时使用全局值；点击“恢复默认”删除单曲覆盖值。
- 播放中改变音量必须立即生效，暂停、继续和重新进入歌曲后保持当前值。

### 2.3 原曲处理策略

首版始终保留原曲，默认把原曲音量降低，让玩家琴声叠加在原曲上。这条路径不依赖分轨质量，适用于所有导入歌曲。

第二阶段增加可选“练习伴奏”：

该功能不进入首版。首版始终使用原始混音；Demucs 或其他分轨方案必须在首版完成后重新评估维护状态、体积、性能和许可证，再作为实验功能单独交付。

## 3. 技术架构

### 3.1 技术选型

| 领域 | 方案 | 用途 |
|---|---|---|
| 桌面 UI | PySide6 | 曲库、导入、游戏、编辑器和设置界面 |
| 游戏绘制 | `QOpenGLWidget` + `QPainter` | 60/120 FPS 音符轨道和命中效果 |
| 音频输出 | sounddevice / PortAudio | 单一低延迟输出流和音频回调 |
| 音频文件 | FFmpeg + soundfile | 解码、转码、波形读取 |
| 琴声合成 | FluidSynth + 合法授权 SF2 | 根据 MIDI note-on/note-off 生成琴声 |
| 自动转谱 | Basic Pitch | 音频转 MIDI 音符事件 |
| 节拍分析 | librosa | BPM、onset、beat 时间点 |
| 数据库 | SQLite（标准库 `sqlite3`） | 曲库、设置、分析任务和成绩 |
| 数据模型 | dataclasses + Pydantic | 谱面、导入任务和配置校验 |
| 测试 | pytest + pytest-qt | 逻辑、数据、UI 和集成测试 |
| 打包 | PyInstaller | 生成 Windows 可运行目录和安装包输入 |

FluidSynth 必须以“无独立音频驱动”的方式运行。应用从 FluidSynth 拉取当前音频块，再与原曲混入同一个 PortAudio 回调。禁止让原曲播放器和 FluidSynth 分别打开声卡，否则二者会产生独立缓冲、延迟差和长期漂移。

### 3.2 进程与线程

应用由一个 UI 主进程和若干受控工作线程/子进程组成：

```text
PySide6 主线程
├─ 页面导航、输入事件、谱面绘制
├─ AudioEngine 控制接口
└─ AnalysisManager 任务控制

PortAudio 实时回调线程
├─ 从 backing ring buffer 读取原曲
├─ 消费键盘 note-on/note-off 事件
├─ 从 FluidSynth 拉取当前音频块
├─ 应用 backing/instrument/master 增益
└─ 写入声卡并推进唯一 sample_clock

音频预读线程
└─ 从标准化 WAV 读取数据并填充 ring buffer

分析子进程
├─ FFmpeg 标准化
├─ librosa 节拍分析
├─ Basic Pitch 转谱
└─ 通过 JSON Lines 上报进度和结果
```

约束：

- PortAudio 回调中禁止磁盘读取、日志输出、数据库访问、模型推理和阻塞锁。
- UI 与音频回调通过预分配、有界的 SPSC 环形队列传递控制事件；溢出时不得静默丢弃 note-off。
- 音量值使用预分配配置快照传入回调；回调中禁止创建 Python 对象或调整容器容量。
- 分析必须使用独立进程，防止模型推理阻塞 UI 或受 Python GIL 影响。
- 分析进程崩溃不得导致主程序退出。

### 3.3 推荐目录结构

```text
KeyRhythm/
├─ README.md
├─ pyproject.toml
├─ requirements.lock
├─ src/keyrhythm/
│  ├─ app.py
│  ├─ config.py
│  ├─ domain/
│  │  ├─ chart.py
│  │  ├─ song.py
│  │  ├─ judgement.py
│  │  └─ import_job.py
│  ├─ audio/
│  │  ├─ engine.py
│  │  ├─ backing_reader.py
│  │  ├─ synthesizer.py
│  │  ├─ mixer.py
│  │  └─ latency.py
│  ├─ analysis/
│  │  ├─ worker.py
│  │  ├─ normalize.py
│  │  ├─ beat_detection.py
│  │  ├─ transcription.py
│  │  ├─ melody_selection.py
│  │  ├─ difficulty.py
│  │  └─ stem_separation.py
│  ├─ gameplay/
│  │  ├─ clock.py
│  │  ├─ input_mapper.py
│  │  ├─ scorer.py
│  │  └─ session.py
│  ├─ library/
│  │  ├─ database.py
│  │  ├─ repository.py
│  │  └─ importer.py
│  └─ ui/
│     ├─ main_window.py
│     ├─ library_page.py
│     ├─ import_page.py
│     ├─ play_page.py
│     ├─ editor_page.py
│     └─ settings_page.py
├─ assets/
│  ├─ soundfonts/
│  ├─ icons/
│  └─ themes/
├─ migrations/
├─ tests/
└─ tools/
```

用户数据默认放在项目或程序目录下的 `data\`，也可通过 `KEYRHYTHM_DATA_DIR` 指定其他位置：

```text
<项目或程序目录>\data\
├─ keyrhythm.db
├─ settings.json
├─ library/<song_id>/
│  ├─ source.<ext>
│  ├─ normalized.wav
│  ├─ chart.json
│  ├─ cover.webp
│  └─ stems/
├─ staging/<import_job_id>/
├─ logs/
└─ models/
```

## 4. 数据模型

### 4.1 SQLite 表

`songs`：

- `id TEXT PRIMARY KEY`：UUID。
- `audio_sha256 TEXT UNIQUE NOT NULL`。
- `title TEXT NOT NULL`。
- `artist TEXT NOT NULL DEFAULT ''`。
- `duration_ms INTEGER NOT NULL`。
- `source_path TEXT NOT NULL`。
- `normalized_path TEXT NOT NULL`。
- `chart_path TEXT`。
- `cover_path TEXT`。
- `status TEXT NOT NULL`：`importing|ready|needs_review|failed`。
- `analysis_version TEXT`。
- `created_at TEXT NOT NULL`。
- `updated_at TEXT NOT NULL`。

`song_tags`：`song_id`、`tag`，组合唯一。

`song_mix_settings`：

- `song_id TEXT PRIMARY KEY`。
- `backing_volume INTEGER NULL`。
- `instrument_volume INTEGER NULL`。
- `master_volume INTEGER NULL`。
- `lead_attenuation_db REAL NULL`。

`scores`：歌曲、模式、难度、总分、准确率、最大连击、各判定数量和完成时间。

`analysis_jobs`：任务 ID、歌曲 ID、阶段、进度、错误码、错误详情和时间戳。

搜索使用 SQLite FTS5 虚拟表索引歌曲标题、艺术家和标签；若运行环境缺少 FTS5，则回退到普通 `LIKE` 搜索。

### 4.2 `chart.json`

谱面采用带版本号的 JSON，时间统一使用 48 kHz 整数采样帧，音高统一使用 MIDI 0–127：

```json
{
  "schema_version": 3,
  "song_id": "uuid",
  "audio_sha256": "hex",
  "analysis_version": "2026.1",
  "chart_revision": 1,
  "chart_sample_rate": 48000,
  "audio_offset_frames": 0,
  "duration_frames": 10340640,
  "analysis_manifest": {
    "transcriber": "basic-pitch",
    "model_version": "pinned-by-lockfile",
    "model_hash": "hex",
    "parameters": {}
  },
  "tempo": {
    "estimated_bpm": 128.0,
    "beat_frames": [0, 22500, 45000]
  },
  "notes": [
    {
      "id": "n-000001",
      "start_frame": 60000,
      "duration_frames": 15360,
      "midi_pitch": 64,
      "velocity": 92,
      "confidence": 0.87,
      "source": "basic_pitch",
      "manually_edited": false
    }
  ],
  "charts": {
    "piano": {
      "key_count": 17,
      "key_events": [{"note_id": "n-000001", "key_index": 8}],
      "key_pitch_map": [56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72],
      "mapping_algorithm": "adaptive_pitch_v1",
      "collision_drop_count": 0
    },
    "lane_4_easy": {
      "key_count": 4,
      "key_events": [{"note_id": "n-000001", "key_index": 2}],
      "key_pitch_map": [60, 62, 64, 67],
      "mapping_algorithm": "adaptive_pitch_v1",
      "collision_drop_count": 0
    },
    "lane_6_normal": {"key_count": 6, "key_events": [], "key_pitch_map": [60, 61, 62, 63, 64, 65], "mapping_algorithm": "adaptive_pitch_v1", "collision_drop_count": 0},
    "lane_8_hard": {"key_count": 8, "key_events": [], "key_pitch_map": [60, 61, 62, 63, 64, 65, 66, 67], "mapping_algorithm": "adaptive_pitch_v1", "collision_drop_count": 0}
  }
}
```

保存规则：

- 先写 `chart.json.tmp`，校验完成后使用原子替换更新正式文件。
- 每次人工保存前保留一个 `chart.backup.json`。
- 用户人工编辑的音符不得在重新分析时被静默覆盖。
- `audio_sha256` 不匹配时禁止直接游玩，提示重新关联或重新分析。
- schema v2 首次加载时备份为 `chart.backup-v2.json`，按新算法重新生成所有键位谱面并增加修订号。

## 5. 音频引擎

### 5.1 统一时间模型

音频引擎同时维护谱面帧、已渲染帧、预计 DAC 播放帧和玩家输入主机时间。PortAudio 回调提供的 `currentTime` 与 `outputBufferDacTime` 用于建立主机单调时钟到歌曲帧的映射：UI 提示使用预计播放位置，判定使用经校准的原始输入时间，绝不使用 `QTimer` 累加歌曲位置。暂停时歌曲帧冻结；跳转、重试或重新载入时递增 `session_generation`，旧输入事件和旧预读数据一律丢弃。

默认音频配置：

- 采样率：48,000 Hz。
- 声道：双声道 float32。
- 默认请求 `latency='low'`、`blocksize=0`，并记录设备实际块大小；128/256/512 仅作为诊断和兼容模式。
- 预读 ring buffer：至少 2 秒原曲数据。
- 首次进入游戏时进行输出设备检查和延迟校准。

### 5.2 键盘事件进入音频回调

1. UI 在 `keyPressEvent` 中忽略系统自动重复事件。
2. 立即读取高精度主机单调时间，创建带 `session_generation` 和序号的 `InputEvent`。
3. 将事件放入有界 SPSC 环形队列。
4. 音频回调把事件映射到当前或下一输出块；已经错过的发声位置钳制到下一可用采样点，但判定保留原始输入时间。
5. FluidSynth 先渲染到事件采样点，再发送 note-on/note-off，最后渲染块内剩余帧。
6. 判定模块使用同一主机时间到谱面帧的映射计算时间差。

这样“玩家听到的按键时间”和“系统用于计分的时间”使用同一音频时间轴。

### 5.3 音量混合

每个回调块执行：

```python
backing = backing_frames * smoothed_backing_gain
instrument = synth_frames * smoothed_instrument_gain
mixed = (backing + instrument) * smoothed_master_gain
output = limiter(mixed)
```

需要公开的控制接口：

```python
class AudioEngine:
    def load_song(self, audio_path: Path, start_frame: int = 0) -> None: ...
    def play(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def seek(self, target_frame: int) -> None: ...
    def stop(self) -> None: ...
    def submit_input(self, event: InputEvent) -> bool: ...
    def set_bus_volume(self, bus: AudioBus, value: int) -> None: ...
    def get_timeline_snapshot(self) -> AudioTimelineSnapshot: ...
    def get_diagnostics(self) -> AudioDiagnostics: ...
```

UI 每 50 ms 最多读取一次电平表，不允许音频线程主动调用 UI。

### 5.4 琴声音色

- 首版只内置一个响应快、延音适中的钢琴 SoundFont。
- SoundFont 必须允许随应用再分发，并在 `THIRD_PARTY_LICENSES.md` 标注授权。
- 音符力度来自谱面，玩家可在设置中选择“固定力度”或“使用谱面力度”。
- 长音在按键释放或目标时长结束时 note-off；设置最大延音，避免卡音。
- 切换页面、暂停、失去窗口焦点和停止歌曲时执行 all-notes-off。

## 6. 自动制谱流水线

### 6.1 阶段与进度

分析子进程按以下阶段通过 stdout 输出 JSON Lines：

```json
{"type":"progress","stage":"normalize","progress":0.4}
{"type":"progress","stage":"beat_detection","progress":1.0}
{"type":"result","chart_path":".../chart.json"}
```

阶段：

1. `validate`：格式、时长、可读性和磁盘空间。
2. `normalize`：转为 48 kHz 双声道 WAV。
3. `beat_detection`：生成 BPM 和 beat 时间。
4. `transcription`：Basic Pitch 生成候选音符。
5. `melody_selection`：清除短噪点、重叠冲突和明显离群音。
6. `difficulty_generation`：生成两种模式的难度谱面。
7. `validation`：检查时间范围、音高范围、ID 和引用完整性。
8. `commit`：使用恢复清单协调 staging 文件移动和数据库事务。

### 6.2 主旋律选择

由于目标是任意类型音乐，算法只提供“最可能的可演奏旋律”，不宣称理解歌曲的创作意图。候选音符按以下信号排序：

- Basic Pitch 置信度。
- 音符持续时间和响度。
- 与前后音符的音高连续性。
- 与强拍和 onset 的接近程度。
- 同一时刻候选音符中是否处于较突出音域。
- 是否造成超过设置上限的同时发音数量。

输出中置信度低于阈值的音符保留但标成黄色；极低置信度音符不进入简单谱面，可在编辑器中恢复。

### 6.3 难度生成

- 17 键旋律和 4/6/8 键模式均按当前难度的音域动态映射；不同音高不足键数时不合并，超过键数时按音高排名连续、单调压缩。
- 单音映射到中央键；两个及以上音高保证最低音在最左、最高音在最右，相同音高始终使用同一键位。
- 4 键简单模式只保留节拍骨架和高显著性音符，移除和弦。
- 6 键普通模式保留更多弱拍和短音符。
- 8 键困难模式尽量保留完整旋律，允许有限双音。
- 轨道映射必须减少短时间内同一只手的大跨度跳跃，并避免同一轨道出现无法完成的重叠长音。
- 自动结果生成后必须运行可玩性检查；不满足密度和冲突限制的段落标记为 `needs_review`。

## 7. 演奏、走音与节奏反馈

### 7.1 动态 17 键旋律模式

- 每首歌曲根据当前谱面音域生成 17 个动态键位和代表音高。
- 按下任何键都会立即发声，不因为“不是正确键”而屏蔽。
- 正确键按早或按晚时，同一个音会真实地早响或晚响。
- 正确键播放目标原始 MIDI 音高；错键播放当前歌曲为该键生成的代表音高，因此自然产生走音。
- 漏键时不播放玩家琴声，只保留原曲。

默认键盘布局为 `A W S E D F T G Y H U J K O L P ;`，轨道底部必须同时显示物理键、代表音名或映射音高范围。

### 7.2 音游轨道模式

- 每个目标音符拥有期望键位和目标 MIDI 音高。
- 按对轨道时播放目标 MIDI 音高。
- 命中窗口内按错轨道时，播放实际按下键在 `key_pitch_map` 中的代表音高。
- 没有可匹配目标时按键，播放一个较短、较弱的错误音，并记为 ghost input。
- 音高错误反馈不得播放过响或尖锐的固定警报声，避免破坏音乐体验。

### 7.3 判定算法

对按键事件在当前未判定音符中寻找时间距离最近的候选：

- Perfect：`abs(delta) <= 45 ms`。
- Good：`45 < abs(delta) <= 90 ms`。
- Bad：`90 < abs(delta) <= 150 ms`。
- Miss：超过 150 ms 尚未命中。

所有模式统一要求 `key_index` 相同。错键可以占用对应目标音符并判 Wrong，防止一次错误后马上补按形成双重得分。

用户延迟校准值只用于修正判定时间和画面提示，不修改音频文件或谱面原始时间。

## 8. UI 页面

### 8.1 曲库页

- 搜索框、标签过滤、最近导入和最近游玩。
- 歌曲卡显示封面、标题、艺术家、时长、分析状态和是否需要校谱。
- 操作：游玩、编辑谱面、重新分析、打开所在目录、删除。
- 删除受管理歌曲时二次确认，并明确将删除音频副本和缓存。

### 8.2 导入页

- 支持拖放和文件选择。
- 显示标题/艺术家编辑、是否启用分轨、分析阶段、进度、耗时和取消按钮。
- 取消后清理 staging；原始用户文件不得删除。
- 导入成功后进入谱面预览，而不是立即开始游戏。

### 8.3 游戏页

- 中央显示下落音符、判定线和当前应按键。
- 顶部显示进度、分数、连击和准确率。
- 右侧或底部常驻显示原曲、琴声两个快速音量滑块；总音量放在暂停菜单。
- 滑块变化只显示整数 0–100，并即时传给 AudioEngine。
- 暂停菜单包含继续、重试、重新校准、返回曲库。

### 8.4 简易校谱器

- 横向时间轴、波形、beat 网格和钢琴卷帘。
- 支持试听、循环选区、添加、删除、移动、改变音高和时长。
- 低置信度音符着色。
- 支持原始混音试听。
- 保存前验证音符边界和轨道引用；提供撤销/重做。

### 8.5 设置与校准

- 输出设备、buffer size、全局三路音量。
- 键位绑定和测试琴键。
- 画面提示偏移和判定偏移。
- 模型缓存大小、清理缓存和重新下载模型入口。
- 显示实时输出延迟、xrun 次数和削波警告。

## 9. 错误处理与边界情况

- 不支持或损坏的音频：保留导入任务错误信息，不创建歌曲记录。
- 磁盘空间不足：在标准化和分轨前预估空间并拒绝开始。
- 分析模型缺失：已有歌曲和已有谱面仍可播放；新导入任务明确失败并提示安装分析组件。MIDI 导入仍属于后续扩展。
- 音频设备被拔出：暂停游戏，执行 all-notes-off，提示重新选择设备。
- 窗口失焦：自动暂停并关闭所有正在响的玩家音符。
- 键盘 ghosting：设置页提供多键测试，并提示普通键盘可能无法识别某些组合。
- 谱面版本过旧：先备份，再执行显式迁移；迁移失败保持只读打开。
- 用户源文件移动：因默认复制到受管理曲库，不影响已经导入的歌曲。
- 过长歌曲：分析分窗口执行；播放器以 ring buffer 流式读取，不把整首 float32 音频载入内存。

## 10. 开发阶段

### 阶段 0：依赖、音频与打包验证

交付：Python 3.11 x64 依赖锁、最小 PyInstaller 构建、手写谱面音频纵切片、实际延迟与 xrun 报告。若 Python 回调无法满足门槛，保留 Python `AudioEngine` 接口并将回调、环形队列、混音和 FluidSynth 集成迁入 C++ 扩展。阶段 0 未通过不得开始大规模 UI 开发。

### 阶段 A：音频和判定技术样机

交付：

- 播放一首标准化 WAV。
- 固定音高键盘和 FluidSynth 发声。
- 原曲、琴声、总音量三路实时调节。
- 使用 sample clock 绘制手写谱面并完成判定。
- 延迟校准和基本调试指标。

此阶段必须先证明“按键声音、背景音乐和判定使用同一时间轴”，否则不得开始大规模 UI 开发。

### 阶段 B：曲库与自动制谱

交付：

- SQLite 曲库和本地搜索。
- 文件导入、SHA-256 去重、FFmpeg 标准化。
- librosa + Basic Pitch 分析流水线。
- `chart.json` 生成、加载和版本校验。
- 导入任务进度、取消和失败恢复。

### 阶段 C：完整玩法

交付：

- 固定音高与 4/6/8 键轨道模式。
- 难度生成、提示动画、计分、连击和结果页。
- 全局及单曲混音设置。
- 暂停、重试、跳转前的音频状态清理。

### 阶段 D：校谱与稳定性

交付：

- 简易钢琴卷帘编辑器。
- 置信度标记、试听和循环区间。
- 预置免版税样例歌曲制作流程。

### 阶段 E：打包与稳定性

交付：

- PyInstaller Windows 构建。
- FFmpeg、FluidSynth、模型和 SoundFont 授权清单。
- 首次启动检查、日志轮转和崩溃诊断信息。
- 安装、升级与用户数据保留测试。

## 11. 测试与验收标准

### 11.1 音频

- 参考 Windows 设备上，按键到听到琴声的 P95 延迟不超过 35 ms。
- 连续播放五分钟，谱面与音频累计偏移不超过 30 ms。
- 拖动任意音量滑块时无明显爆音、卡顿或时钟跳变。
- 原曲设为 0 时玩家琴声仍正常；琴声设为 0 时原曲和判定仍正常；总音量设为 0 时无输出但游戏继续推进。
- 暂停、恢复、重试和失焦后无残留长音。
- backing 和 instrument 同时满幅时不出现不可控削波；调试日志可定位削波次数。

### 11.2 判定和发声

- 使用合成输入事件验证 ±45、±90、±150 ms 边界。
- 17/4/6/8 键模式错一个键时，输出 MIDI 音高与当前歌曲该键的 `key_pitch_map` 一致。
- 轨道模式按错轨道时，输出音高偏移和判定结果一致。
- 提前、延后和漏按分别能在琴声时机或缺失上听见差异。
- 修改音量不改变同一输入序列的最终得分。

### 11.3 导入和谱面

- MP3、WAV、FLAC、M4A 样例均能导入。
- 相同内容不同文件名不会重复入库。
- 取消和崩溃不会留下 `ready` 状态的半成品歌曲。
- `chart.json` 保存、备份、重新打开和迁移保持数据一致。
- 使用至少 20 首不同类型歌曲做人工可玩性检查；低质量段落能被标记并通过编辑器修正。

### 11.4 性能

- 游戏过程中 UI 目标 60 FPS，支持设置为 120 FPS；音频不得因 UI 短暂掉帧而中断。
- 音频回调无磁盘 I/O 和数据库 I/O，并在压力测试中无持续 xrun。
- 长歌曲以流式读取播放，内存使用不随歌曲总时长线性增长。

## 12. 后续扩展方向

完成首版后再按优先级评估：

1. MIDI 文件作为高准确度谱面导入源。
2. 多种 SoundFont、吉他或合成器音色。
3. 用户分享只包含谱面的歌曲包，不自动分享无授权音频。
4. 已知曲目的音频指纹识别与外部播放同步。
5. 经单独可行性验证后的分轨练习伴奏。
6. WASAPI 系统音频捕获；未知歌曲必须接受缓冲分析延迟。
7. 云端曲库、账号和排行榜。

## 13. 实施时必须遵守的边界

- 先完成阶段 0 的依赖、打包和低延迟统一时间模型验证，再实现自动制谱和复杂界面。
- 自动制谱始终允许人工修正，不以“AI 必须完全准确”为前提。
- 原曲、琴声、总音量是独立参数，并且绝不进入计分计算。
- 不通过录音、抓流或非官方工具获取商业平台歌曲。
- 预置曲目、SoundFont、图标、模型和所有二进制依赖必须记录许可证。
- 删除、重分析和谱面迁移前必须保留用户数据或要求明确确认。

## 14. 完成定义

当用户能够完成以下完整流程时，个人原型视为完成：

1. 启动 KeyRhythm，在曲库中搜索并选择一首预置歌曲。
2. 分别调节原曲和玩家琴声音量并立即听到差异。
3. 选择固定音高或音游轨道模式完成一局游戏。
4. 正确按键听到正确旋律，错键听到走音，错拍听到时机偏差。
5. 查看成绩并重新游玩。
6. 导入一首本地歌曲，等待自动制谱完成。
7. 在编辑器中修正至少一个音符并保存。
8. 使用修正后的谱面游玩，退出并重新启动后歌曲、谱面和音量设置仍然存在。
