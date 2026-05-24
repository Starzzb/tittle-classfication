具体使用说明在 readme.md

项目结构：
  stage1_extract_propose.py  — 阶段一：扫描目录，提取关键词，标记 needs_vision（支持视频+图片）
  stage1b_ai_refine.py       — 阶段1b（可选）：AI 批量精简标题
  stage1c_vision_refine.py   — 阶段1c：视觉识别提取关键词（支持CLIP、关键帧检测、embedding检测）
  stage1c_frame_selector.py  — 人体检测模块（UHD 超轻量模型）
  stage1c_clip_classifier.py — CLIP 分类模块（支持多标签、embedding检测）
  stage2_apply_rename.py     — 阶段二：读取 CSV，执行重命名
  renamecsv.py               — 辅助工具，批量修改 CSV 审核状态
  gui.py                     — 图形界面（支持全部功能）

模型文件：
  models/human_detection/ultratinyod_res_anc8_w128_64x64_loese_distill.onnx  — UHD 人体检测模型
  models/clip/                                                              — CLIP 模型目录

API 支持：
  stage1b: ollama（本地）/ zhipu / gcli
  stage1c: mimo / gcli

配置：
  .env                       — 存放 API Key（已加入 .gitignore）
    ZHIPU_API_KEY            — 智谱 API key
    MIMO_API_KEY             — 小米 MiMo API key
    GCLI_API_KEY             — gcli API key（OpenAI 兼容）

工作流：
  1. stage1  扫描 → CSV（含 needs_vision）
  2. stage1b AI 清洗 → final_name（有意义的标题，needs_vision=false）
  3. stage1c 视觉识别 → final_name（无意义的标题，needs_vision=true）
  4. stage2  执行重命名

Stage1b 新功能（v5.0）：
  - 只处理 needs_vision=false 的标题（跳过需要视觉识别的）
  - GUI 支持预览和编辑 AI 优化结果
  - 双击可修改优化结果
  - 右键菜单：采用原标题、编辑、删除
  - 用户确认后才写入 final_name

命令工作流：
uv run python stage1_extract_propose.py -d "F:\Videos"                     # 必需：扫描目录

# 如果文件已有中括号标签，想重新提取原始标题：
uv run python stage1_extract_propose.py -d "F:\Videos" --force-reclassify -o "review_reclassify.csv"

#1b可以跳过，我给优化了（GUI中可预览编辑）

uv run python stage1c_vision_refine.py                                     # 默认启用人体检测

uv run python renamecsv.py                                                 # 直接添加已确认

uv run python stage2_apply_rename.py

新功能（v5.0）：
  CLIP 预分类：
    --use-clip                    启用 CLIP 本地预分类
    --clip-threshold 0.25         CLIP 置信度阈值
    --clip-frames 5               CLIP 分析的视频帧数
    --vlm-frames 3                送入云端 VLM 的帧数
    --multi-label                 多标签模式（默认）
    --single-label                单标签模式

  关键帧检测：
    --keyframe-threshold 30.0     关键帧差异阈值（越低越敏感）
    --max-keyframes 8             最大关键帧数

  Embedding 变化检测：
    --use-embedding-detection     使用 embedding 检测变化（默认）
    --no-embedding-detection      禁用 embedding 检测
    --embedding-threshold 0.75    Embedding 相似度阈值（稳健值）

常用参数（stage1）：
  --force-reclassify     强制重分类：处理所有文件，有中括号提取原始标题，没有也正常处理
  --exclude-dir          排除目录
  -a                     追加模式

常用参数（stage1c）：
  --no-frame-selector    禁用人体检测（使用固定时间点提取帧）
  --max-image-size 640   调整图片压缩大小
  --conf-threshold 0.3   降低人体检测阈值（更敏感）
  --retry-errors         重试之前失败的行
  --single "文件名"       仅处理指定文件
  --timestamp "00:01:30" 指定固定时间点（覆盖自适应策略）
