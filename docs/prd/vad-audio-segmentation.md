# PRD: VAD 音频分段系统与视觉识别字幕集成

**Labels:** `ready-for-agent`

---

## Problem Statement

当前视频标题分类工具的音频处理模块存在以下问题：

1. **音频分段质量差**：旧的能量阈值分段方式产生大量碎片（0.1-0.4秒的短段），同一句话被切成多段，导致语音识别结果不准确
2. **API拒绝转录无法恢复**：长音频段被API拒绝后直接丢弃，没有任何重试机制
3. **视觉识别缺乏音频上下文**：VLM分析视频帧时不知道每帧对应的语音内容，无法利用音频信息辅助理解
4. **音频处理日志不在GUI中显示**：音频识别的日志输出到CLI控制台，而视觉识别的日志显示在GUI运行日志框内，体验不一致
5. **字幕后处理缺失**：API返回的转录内容直接写入SRT，没有过滤无效内容（时间戳列表、拒绝响应等），也没有拆分过长的字幕段

## Solution

实现一套基于 Silero VAD 的三层音频分段策略，配合字幕后处理、API拒绝自动重试、VLM字幕上下文集成，以及GUI日志重定向，全面提升音频转录质量和视觉识别准确率。

---

## User Stories

1. As a 用户，我希望音频分段能自动识别语音和静音的边界，以便每段音频都是完整的语句
2. As a 用户，我希望VAD检测到的碎片化语音段能自动合并，以便减少API调用次数
3. As a 用户，我希望长音频段在语义停顿处断开，以便每段不超过模型的输入窗口限制
4. As a 用户，我希望纯静音段和噪音段被自动过滤，以便不浪费API调用
5. As a 用户，我希望被API拒绝的长音频段能自动按10秒切片重试，以便尽可能多地获取转录内容
6. As a 用户，我希望字幕后处理能过滤掉无效内容（时间戳列表、拒绝响应、分析报告等），以便SRT文件只包含有效的转录文本
7. As a 用户，我希望字幕后处理能拆分过长的字幕段，以便每段字幕的显示时间不超过10秒
8. As a 用户，我希望字幕后处理能格式化说话人标签，以便SRT文件中的标签格式统一
9. As a 用户，我希望视觉识别时VLM能知道每帧对应的字幕时间段，以便更准确地理解视频内容
10. As a 用户，我希望音频处理的日志能显示在GUI的运行日志框内，以便在一个地方查看所有处理进度
11. As a 用户，我希望能在GUI中配置VAD参数（最小时长、最小静音、合并间隙等），以便根据不同视频调整分段效果
12. As a 用户，我希望能在GUI中配置字幕后处理参数（最大时长、最大字符数等），以便控制字幕的显示效果
13. As a 用户，我希望能在GUI中禁用字幕后处理，以便在需要时获取原始的API转录结果
14. As a 用户，我希望音频识别标签页能独立于视觉识别标签页，以便分别配置和运行
15. As a 用户，我希望扫描命令支持选择单个视频文件，以便快速处理单个文件而不需要扫描整个目录
16. As a 用户，我希望配置文件中的音频配置能正确加载到GUI，以便GUI显示的配置与实际运行的配置一致
17. As a 用户，我希望VAD分段的三层策略（微合并→语义打包→静音过滤）能自动处理各种音频场景，以便无需手动调整参数
18. As a 用户，我希望微合并能消除换气和短暂停顿导致的碎片，以便同一句话不被切成多段
19. As a 用户，我希望语义打包能在长停顿处断开，以便每段音频有清晰的语义边界
20. As a 用户，我希望静音过滤能跳过语音占比低于40%的段，以便不处理纯噪音或环境音
21. As a 用户，我希望字幕后处理的配置能直接从配置文件读取，以便不受GUI变量覆盖的影响
22. As a 用户，我希望VLM prompt中包含每帧对应的字幕时间戳和内容，以便VLM能结合语音信息理解画面
23. As a 用户，我希望每帧字幕上下文只在有对应字幕时显示，以便没有语音的帧不会被错误地标记
24. As a 用户，我希望音频识别完成后CSV中的audio_recognized字段能正确更新，以便后续流程知道哪些文件已完成音频识别
25. As a 用户，我希望SRT文件能自动复制到视频所在目录，以便字幕文件与视频文件在同一位置

---

## Implementation Decisions

### Module 1: VAD 三层分段策略（`audio.py` — `_get_vad_segments`）

**三层策略**：
- **第一层（微合并）**：将间隙小于 `merge_gap`（默认0.8秒）的相邻VAD语音段合并，消除换气/停顿碎片
- **第二层（语义打包）**：将微合并后的段打包成不超过 `max_chunk`（默认25秒）的块，在 `long_gap`（默认2秒）以上的长停顿处断开
- **第三层（静音过滤）**：过滤掉时长小于 `min_duration`（默认1秒）或语音占比小于 `min_speech_ratio`（默认40%）的块

**配置参数**（`config/default.toml` 的 `[audio.vad]` 节）：
- `merge_gap`、`min_keep_duration`、`max_chunk`、`long_gap`、`min_duration`、`min_speech_ratio`

### Module 2: API 拒绝自动重试（`audio.py` — 处理拒绝分支）

当API返回拒绝响应时，按10秒为单位切片重试：
- 每片独立提取音频并调用API
- 成功的子块写入segments列表
- 失败的子块跳过，不递归拆分
- 最短子块0.5秒以下直接忽略

### Module 3: 字幕后处理（`subtitle_postprocessor.py`）

**过滤规则**：
- 时间戳列表（API返回异常）
- 拒绝响应（"rejected"、"无法"、"无法转录"）
- 安全拒绝（"很抱歉"、"无法处理这个请求"）
- 长分析报告（>500字符且包含分析关键词）

**拆分逻辑**：
- 按空行和句子边界拆分
- 按字符数比例分配时间戳
- 最小持续时间0.5秒

**配置来源**：直接从 `config/default.toml` 的 `[audio.postprocess]` 读取，不依赖GUI变量

### Module 4: VLM 字幕上下文集成（`vision.py`）

**新增方法**：
- `_parse_audio_srt_with_timestamps()`：解析SRT返回 `[{start, end, text}]`
- `_match_frame_to_subtitles()`：将帧时间戳匹配到字幕段
- `_build_per_frame_subtitle_context()`：构建每帧字幕上下文字符串

**Prompt 增强**：
```
【各帧对应音频转录时间段】
- 图1@6.0s: [00:00:05 --> 00:00:15] 你好世界
- 图2@20.0s: (无对应字幕)
```

**调用链修改**：
- `process_and_save()` 解析SRT带时间戳
- `process_video()` 传递 `subtitle_segments`
- `_process_video_comprehensive()` 提取帧时间戳并构建上下文
- `_build_comprehensive_prompt()` 接收 `per_frame_subtitle` 参数

### Module 5: GUI 日志重定向（`app.py`）

新增 `GUILogHandler` 类，将 Python logging 输出重定向到GUI的 `log_text` widget：
- `audio.py` 使用 `logger.info()` 输出日志
- `GUILogHandler` 将日志同时写入GUI和控制台
- 音频处理日志与视觉识别日志在同一个"运行日志"区域显示

### Module 6: GUI 配置管理（`app.py`）

- 新增"Stage1c 音频识别"标签页，独立配置VAD参数和字幕后处理
- 移除视觉识别标签页的冗余音频配置区域
- 字幕后处理配置直接从配置文件读取，不受GUI变量覆盖影响
- 支持"仅检测VAD"调试模式

### Module 7: 扫描命令增强（`scanner.py`）

- `scan` 命令的 `-d` 参数支持单个文件路径
- 自动判断是文件还是目录

### Module 8: VLM prompt 添加每帧字幕时间戳上下文（`vision.py`）

- 每帧对应字幕时间段显示在 prompt 中
- 无对应字幕的帧标记为"(无对应字幕)"
- 帮助 VLM 理解画面与语音的关联

---

## Testing Decisions

### 测试原则

- 只测试外部行为，不测试实现细节
- 测试应能在无网络环境下运行（mock API调用）
- 测试应覆盖边界情况（空音频、纯静音、超长段等）

### 已有测试（`tests/test_audio.py`）

- `TestZCR`：过零率计算
- `TestSpectralCentroid`：频谱重心计算
- `TestSpectralEntropy`：频谱熵计算
- `TestAnalyzeFrameFeatures`：帧特征分析
- `TestClassifyFrame`：帧分类
- `TestBuildFrameFeatureMap`：帧级特征图
- `TestEnhancedAdaptiveSegment`：增强型自适应分段
- `TestMergeStrategies`：合并策略

### 需要新增的测试

- VAD三层分段策略的集成测试
- API拒绝重试逻辑的单元测试
- 字幕后处理的过滤和拆分测试
- VLM字幕上下文构建的单元测试
- SRT解析和帧匹配的单元测试

### 测试参考

现有测试使用 `pytest`，通过构造 numpy 数组模拟音频数据，通过构造字典列表模拟分段结果。

---

## Out of Scope

1. **VAD模型本身的训练或微调**：使用预训练的 Silero VAD 模型
2. **实时音频流处理**：仅处理已录制的视频文件
3. **多语言语音识别**：仅支持中文转录
4. **音频降噪**：不处理音频质量，依赖API的降噪能力
5. **字幕翻译**：不涉及翻译功能
6. **视频编辑功能**：不涉及视频裁剪、合并等操作
7. **多用户协作**：单用户本地工具
8. **云端部署**：本地运行工具

---

## Further Notes

### 配置参数参考

```toml
[audio]
skip_silence = true
volume_threshold = 0.01

[audio.vad]
enabled = true
min_speech_ms = 150
min_silence_ms = 80
merge_gap = 0.8
min_keep_duration = 1.0
max_chunk = 25.0
long_gap = 2.0
min_duration = 1.0
min_speech_ratio = 0.4

[audio.postprocess]
enabled = true
max_subtitle_duration = 10
max_subtitle_chars = 100
filter_invalid = true
format_text = true
```

### 处理流程图

```
视频文件
  ↓ ffmpeg 提取音频 (16kHz, 单声道, float32)
  ↓
Silero VAD 检测语音段
  ↓ 第一层：微合并（间隙 < 0.8秒合并）
  ↓ 第二层：语义打包（长停顿 > 2秒断开，最大块 25秒）
  ↓ 第三层：静音过滤（时长 < 1秒跳过，语音占比 < 40%跳过）
  ↓
逐段调用 MiMo API 语音转录
  ↓ 被拒绝的段按10秒切片自动重试
  ↓
字幕后处理（可选）
  ↓ 拆分长字幕、过滤无效内容
  ↓
生成 SRT 字幕文件
```

### 依赖

- `silero-vad>=5.1.0`：VAD模型
- `torch>=2.0.0`：PyTorch（Silero VAD 依赖）
- `numpy>=1.24.0`：音频数据处理
