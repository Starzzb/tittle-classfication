具体使用说明在 readme.md

常用命令：

  # 启动 GUI
  uv run title-classifier gui

  # 扫描目录，生成待审 CSV
  uv run title-classifier scan -d "F:\Videos"

  # 扫描单个文件
  uv run title-classifier scan -d "F:\Videos\video.mp4"

  # 追加模式（不覆盖已有 CSV）
  uv run title-classifier scan -d "F:\Videos" -a

  # AI 优化标题（可选）
  uv run title-classifier refine -p gcli

  # 音频识别生成字幕（可选）
  uv run title-classifier audio -p mimo

  # 视觉识别（YOLO + VLM）
  uv run title-classifier vision --use-yolo -p gcli

  # 视觉识别（全面分析，三个 YOLO 模型）
  uv run title-classifier vision --use-yolo --comprehensive -p gcli

  # 使用 CLIP 预分类
  uv run title-classifier vision --use-clip --use-yolo -p gcli

  # 预览重命名（不执行）
  uv run title-classifier rename --dry-run

  # 执行重命名
  uv run title-classifier rename

  # 模型下载
  uv run python scripts/download_models.py     # 一键下载全部
  uv run python scripts/download_clip.py       # 仅 CLIP
  uv run python scripts/download_yolo_models.py # 仅 YOLO

  # 重建虚拟环境
  uv sync

常用参数：

  scan:
    -d, --dir          目标目录或文件（必需）
    -o, --output       输出 CSV 路径
    -a, --append       追加模式
    --exclude-dir      排除目录
    --force            强制重新分类

  refine:
    -c, --csv          CSV 文件路径
    -p, --provider     AI Provider（gcli/zhipu/ollama）

  audio:
    -c, --csv          CSV 文件路径
    -p, --provider     AI Provider（默认 mimo）
    --all              处理所有未识别文件

  vision:
    -c, --csv          CSV 文件路径
    -p, --provider     AI Provider
    --use-yolo         启用 YOLO 检测
    --comprehensive    全面分析（detect+pose+segment）
    --yolo-model       YOLO 模型类型（detect/pose/segment）
    --use-clip         启用 CLIP 预分类
    --vlm-frames       VLM 帧数（默认 10）
    --analysis-step    采样间隔秒数（默认 2.0）
    --all              处理所有未识别文件
    --single "文件名"  仅处理指定文件

  rename:
    -c, --csv          CSV 文件路径
    --dry-run          模拟运行

配置：
  .env                       — API Key（已加入 .gitignore）
    GCLI_API_KEY             — gcli API key（视觉识别，推荐）
    MIMO_API_KEY             — MiMo API key（视觉+音频）
    ZHIPU_API_KEY            — 智谱 API key（文本优化）
  config/default.toml        — VAD/音频/字幕等参数
  config/providers.json      — 自定义 Provider

模型目录：
  models/clip/               — CLIP 模型
  models/yolo/               — YOLO 模型（detect/pose/segment）

帧选择策略（分区段覆盖）：

  视频按采样间隔（默认2秒）提取帧（上限50帧），再选出 vlm_frames 帧发送给 VLM。
  选帧采用"分区段"策略，将采样帧等分为 vlm_frames 个区段，每个区段内独立选最优帧，
  保证全视频均匀覆盖，不会因后半段置信度低而被忽略。

  示例：60秒视频，采样30帧，选10帧
    区段1 [帧0-2]  → 内部比置信度 → 选1帧（覆盖 0-6s）
    区段2 [帧3-5]  → 内部比置信度 → 选1帧（覆盖 6-12s）
    ...
    区段10 [帧27-29] → 内部比置信度 → 选1帧（覆盖 54-60s）

  区段内评分规则（全面分析模式）：
    置信度 40% + 关键点可见性 30% + 姿态变化 30%
    无人体帧 → 取区段中间帧（保证覆盖）

字幕上下文优化：

  发送给 VLM 的字幕上下文按字幕时间段去重：多个帧落入同一字幕区间时合并显示，
  避免重复发送相同字幕内容。

  示例：
    - 图1,2,3,4@4.0s-30.0s: [00:00:01 --> 00:00:31] 字幕内容...
    - 图9@48.0s: [00:00:33 --> 00:00:59] 字幕内容...
