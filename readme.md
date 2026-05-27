# 视频/图片标题批量标准化重命名工具

## 目录

- [项目简介](#项目简介)
- [核心功能](#核心功能)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [快速开始](#快速开始)
- [CLI命令详解](#cli命令详解)
- [GUI使用说明](#gui使用说明)
- [YOLO视觉分析](#yolo视觉分析)
- [音频字幕集成](#音频字幕集成)
- [AI Provider 配置](#ai-provider-配置)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [更新日志](#更新日志)

---

## 项目简介

本工具是一套**三阶段媒体文件批量重命名系统**，专为本地视频/图片库管理设计。通过智能分词、AI 清洗和视觉识别，将杂乱的文件名转换为**标准化、可检索、语义清晰**的格式，同时保证操作的安全性与可逆性。

**适用场景**：
- 整理下载目录中的大量视频/图片文件
- 为媒体库建立统一命名规范
- 为后续 AI 分类/标签系统准备数据
- 批量清理历史遗留的混乱文件名

---

## 设计理念

工具好不好用，还是要看用工具的人，这个东西简洁明了，模型，提示词什么的你都可以自己换，符合你自己视频分类的需求。我的需求就是把自己的小学习资料加个名字列数据库好分类。这个东西就是一个处理框架，基本上就是最后的视觉大模型发挥主要的作用。中间的clip数据太少很难使用，人体检测模型可以替换。我在https://github.com/PINTO0309/PINTO_model_zoo 这个仓库扒拉的检测模型。可以自己查看一下。不过应该没人闲得无聊逛这些私人公共仓库吧（心虚）。最后就是这个东西是匹配个人需求的东西，你当然可以修改给自己使用。

---

## 核心功能

| 功能模块 | 特性描述 |
|---------|---------|
| **YOLO 视觉分析** | 集成 YOLOv8，支持检测、姿态估计、实例分割 |
| **视频全面分析** | 每2秒采样，智能选择10帧代表性帧给VLM |
| **姿态分析** | 17个关键点，识别跪姿、站立、坐姿等动作 |
| **智能帧选择** | 基于姿态变化、置信度、关键点可见性选择最佳帧 |
| **关键词提取** | 聚焦穿着、姿势、行为，水印博主名最优先 |
| **SRT字幕生成** | 视觉描述写入SRT开头，支持音频字幕追加 |
| **final_name渐进填充** | 每个阶段都有值，不会出现空值问题 |
| **AI优化预览** | Stage1b支持预览表格，右键编辑、采用原标题 |
| **批量确认** | Stage2支持一键确认所有记录 |
| **音频字幕** | 可选功能，使用MiMo API生成音频字幕 |
| 智能扫描 | 递归遍历指定目录，支持 10+ 种视频格式和 7 种图片格式 |
| 语义分析 | 基于 Jieba 分词 + TF-IDF 算法，自动提取标题核心关键词 |
| 无意义检测 | 程序自动识别 hash、Telegram 来源、IMG_xxx 等无意义标题 |
| CLIP 预分类 | 使用 OpenCLIP 进行本地预分类，支持多标签输出 |
| 智能压缩 | 自动压缩图片/视频帧，避免 API 传输过大文件 |
| 安全预览 | 三阶段设计，先生成待审表，人工确认后再执行，零风险操作 |
| 冲突避让 | 自动检测文件名冲突，智能追加序号（`_1`, `_2`），防止覆盖 |

---

## 环境要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.10+ | 推荐 3.12 |
| 操作系统 | Windows / macOS / Linux | 全平台兼容 |
| 磁盘空间 | >= 500MB | 包含模型文件和依赖 |
| 权限要求 | 目标目录读写权限 | 必需 |
| ffmpeg | 全局 PATH | 用于视频帧提取和音频处理 |

---

## 安装步骤

### 1. 安装 uv（Python 包管理器）

**Windows（PowerShell）**：
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux**：
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 克隆项目

```bash
git clone https://github.com/Starzzb/title-classifier.git
cd title-classifier
```

### 3. 创建虚拟环境并安装依赖

```powershell
uv venv --python 3.12
uv sync
```

### 4. 下载模型文件

#### 4.1 YOLO 模型（推荐）

YOLO 模型会在首次使用时自动下载到 `models/yolo/` 目录。

如需手动下载：
```powershell
uv run python scripts/download_yolo_models.py
```

**可用模型**：
| 模型 | 大小 | 功能 |
|------|------|------|
| `yolov8n.pt` | 6MB | 人体检测 |
| `yolov8n-pose.pt` | 7MB | 姿态估计 |
| `yolov8n-seg.pt` | 7MB | 实例分割 |

#### 4.2 UHD 人体检测模型（备选）

模型文件已包含在项目中：`models/human_detection/ultratinyod_res_anc8_w128_64x64_loese_distill.onnx`

#### 4.3 CLIP 模型（可选）

CLIP 模型会在首次使用时自动下载到 `models/clip/` 目录。

### 5. 配置 AI API

在项目根目录创建 `.env` 文件：

```env
# gcli API（用于视觉识别，推荐）
GCLI_API_KEY=your_gcli_key_here

# 小米 MiMo API（用于视觉识别和音频字幕）
MIMO_API_KEY=your_mimo_key_here

# 智谱 API（用于文本优化）
ZHIPU_API_KEY=your_zhipu_key_here
```

---

## 快速开始

### CLI 命令方式

```powershell
# 步骤1：扫描目录并生成待审表
uv run title-classifier scan -d "F:\Videos"

# 步骤2：（可选）AI 优化标题
uv run title-classifier refine -p gcli

# 步骤3：视觉识别提取关键词（使用YOLO全面分析）
uv run title-classifier vision --use-yolo --yolo-model pose -p gcli

# 步骤4：（可选）启用音频字幕
uv run title-classifier vision --use-yolo --yolo-model pose -p gcli --audio

# 步骤5：预览重命名结果
uv run title-classifier rename --dry-run

# 步骤6：执行重命名
uv run title-classifier rename
```

### GUI 方式

```powershell
# 启动图形界面
uv run title-classifier gui
```

---

## CLI命令详解

### scan 命令 - 扫描目录

```powershell
uv run title-classifier scan -d "F:\Videos" [选项]
```

| 参数 | 说明 |
|------|------|
| `-d, --dir` | 目标目录（必需） |
| `-o, --output` | 输出文件路径 |
| `--output-dir` | 输出目录（默认 data/output） |
| `-a, --append` | 追加模式 |
| `--exclude-dir` | 排除的目录 |
| `--force` | 强制重新分类 |

### refine 命令 - AI优化标题

```powershell
uv run title-classifier refine [选项]
```

| 参数 | 说明 |
|------|------|
| `-c, --csv` | CSV文件路径 |
| `-p, --provider` | AI Provider（gcli/zhipu/ollama） |

### vision 命令 - 视觉识别

```powershell
uv run title-classifier vision [选项]
```

| 参数 | 说明 |
|------|------|
| `-c, --csv` | CSV文件路径 |
| `-p, --provider` | AI Provider |
| `--use-yolo` | 使用YOLO检测 |
| `--yolo-model` | YOLO模型类型（detect/pose/segment，可多选） |
| `--yolo-conf` | YOLO置信度阈值（默认0.5） |
| `--use-clip` | 使用CLIP预分类 |
| `--vlm-frames` | VLM帧数（默认10） |
| `--analysis-step` | 采样间隔秒数（默认2.0） |
| `--audio` | 生成音频字幕 |
| `--all` | 处理所有未识别文件 |

### rename 命令 - 执行重命名

```powershell
uv run title-classifier rename [选项]
```

| 参数 | 说明 |
|------|------|
| `-c, --csv` | CSV文件路径 |
| `--dry-run` | 模拟运行 |

### gui 命令 - 启动图形界面

```powershell
uv run title-classifier gui
```

---

## GUI使用说明

### 启动 GUI

```powershell
uv run title-classifier gui
```

### 功能标签页

| 标签页 | 功能 |
|--------|------|
| **Stage1 扫描** | 扫描目录，生成待审表 |
| **Stage1b AI优化** | AI优化标题，支持预览编辑 |
| **Stage1c 视觉识别** | YOLO/UHD检测 + VLM识别 |
| **Stage2 重命名** | 执行重命名操作 |

### Stage1b 预览编辑功能

- **加载CSV**：加载CSV到预览表格
- **AI优化**：调用AI优化标题，自动加载结果
- **右键菜单**：
  - 编辑：双击或右键编辑优化结果
  - 采用原标题：使用原始文件名
  - 采用建议标题：使用分词建议
  - 删除：从预览中移除
- **确认写入**：将优化结果写入CSV

### Stage1c 视觉识别选项

- **检测器选择**：YOLO（默认）或 UHD
- **YOLO模型多选**：detect、pose、segment
- **分析参数**：采样间隔、VLM帧数
- **选项**：处理所有文件、生成音频字幕

### Stage2 批量操作

- **一键确认所有记录**：将所有记录设置为"已确认"
- **一键清空final_name**：清空所有final_name

---

## YOLO视觉分析

### 功能说明

YOLOv8 是一个多功能视觉分析模型，支持：

1. **目标检测**（detect）：检测人体位置和边界框
2. **姿态估计**（pose）：17个关键点，识别动作姿态
3. **实例分割**（segment）：像素级人体区域分割

### 视频全面分析模式

当使用 `--use-yolo` 时，启用视频全面分析模式：

1. **高密度采样**：默认每2秒采样一帧
2. **姿态分析**：记录每帧的姿态、置信度、关键点
3. **智能帧选择**：选择10帧代表性帧
4. **视频摘要**：生成姿态分布、变化时间线
5. **VLM增强**：将YOLO上下文传给VLM

### 使用示例

```powershell
# 使用YOLO姿态估计
uv run title-classifier vision --use-yolo --yolo-model pose -p gcli

# 使用YOLO全面分析（检测+姿态+分割）
uv run title-classifier vision --use-yolo --yolo-model detect pose segment -p gcli

# 自定义采样间隔
uv run title-classifier vision --use-yolo --analysis-step 1.0 -p gcli

# 增加VLM帧数
uv run title-classifier vision --use-yolo --vlm-frames 15 -p gcli
```

### 输出示例

**关键词格式**（水印博主名最优先）：
```
Sexy Yuki, 黑色丝袜, 红色羽毛装饰, 黑色蕾丝内衣, 跪姿, 蹲姿, 弯腰, 坐姿
```

**final_name格式**：
```
[Sexy Yuki_黑色丝袜_红色羽毛装饰_黑色蕾丝内衣_跪姿_蹲姿_弯腰_坐姿]_原文件名.mp4
```

---

## 音频字幕集成

### 功能说明

音频字幕功能使用 MiMo API 进行语音识别，生成 SRT 字幕文件。

### 使用方法

```powershell
# 启用音频字幕（追加到SRT文件）
uv run title-classifier vision --use-yolo --yolo-model pose -p gcli --audio
```

### SRT文件格式

```srt
0
00:00:00,000 --> 00:00:01,000
【视频描述】这是一个在现代室内拍摄的视频...
【关键词】Sexy Yuki, 黑色丝袜, 红色羽毛装饰
【姿态分析】主要姿态：跪姿/蹲姿，姿态变化7次，人体出现86%

1
00:00:00,000 --> 00:00:30,000
（音频字幕内容）
```

### SRT文件命名

SRT文件名使用与 final_name 相同的格式：
```
[Sexy Yuki_黑色丝袜_红色羽毛装饰_跪姿_弯腰]_test_video.srt
```

---

## AI Provider 配置

### 内置 Provider

| Provider | 默认模型 | 环境变量 | 支持阶段 |
|----------|---------|---------|----------|
| `ollama` | qwen2.5:7b-instruct-q4_K_M | - | 1b, 1c |
| `zhipu` | GLM-4.7-Flash | ZHIPU_API_KEY | 1b, 1c |
| `gcli` | gemini-3-flash-preview | GCLI_API_KEY | 1b, 1c |
| `mimo` | mimo-v2.5 | MIMO_API_KEY | 1c, audio |

### 自定义 Provider

创建 `config/providers.json` 文件添加自定义 Provider：

```json
{
  "my_provider": {
    "name": "我的Provider",
    "type": "multi",
    "url": "https://api.example.com/v1/chat/completions",
    "env_key": "MY_API_KEY",
    "default_model": "my-model",
    "requires_api_key": true,
    "supports_1b": true,
    "supports_1c": true,
    "supports_audio": false,
    "description": "自定义Provider描述"
  }
}
```

---

## 项目结构

```
title-classifier/
├── src/
│   └── title_classifier/
│       ├── __init__.py          # 版本信息
│       ├── __main__.py          # CLI入口
│       │
│       ├── core/
│       │   ├── scanner.py       # 文件扫描
│       │   ├── refiner.py       # AI优化
│       │   ├── vision.py        # 视觉识别
│       │   └── renamer.py       # 重命名
│       │
│       ├── detectors/
│       │   ├── base.py          # 检测器基类
│       │   ├── uhd.py           # UHD人体检测
│       │   ├── yolo.py          # YOLO检测
│       │   └── clip.py          # CLIP分类
│       │
│       ├── providers/
│       │   ├── __init__.py      # Provider管理
│       │   └── base.py          # Provider基类
│       │
│       ├── utils/
│       │   ├── video.py         # 视频工具
│       │   ├── image.py         # 图片工具
│       │   ├── audio.py         # 音频工具
│       │   └── stats.py         # 标签统计
│       │
│       └── gui/
│           └── app.py           # 图形界面
│
├── config/
│   └── default.toml             # 默认配置
│
├── models/
│   ├── clip/                    # CLIP模型
│   ├── human_detection/         # UHD模型
│   └── yolo/                    # YOLO模型
│
├── scripts/
│   ├── download_clip.py
│   └── download_yolo_models.py
│
├── tests/                       # 测试文件
├── test/                        # 测试数据
├── data/
│   ├── output/                  # 输出目录
│   └── subtitles/               # SRT字幕目录
│
├── pyproject.toml
└── .env
```

---

## 常见问题

### Q1：YOLO模型下载失败

```powershell
# 使用国内镜像下载
uv run python scripts/download_yolo_models.py
```

### Q2：CSV 在 Excel 中打开乱码

1. 用 VS Code 打开 CSV
2. 右下角点击编码 -> "通过编码保存"
3. 选择 "UTF-8 with BOM"

### Q3：关键词不包含博主名

确保 VLM 提示词中水印博主名字为最高优先级。当前版本已默认设置。

### Q4：SRT文件名格式不对

SRT文件名使用 final_name 格式，确保先运行 vision 命令生成 final_name。

### Q5：如何撤销重命名？

```powershell
# 执行前备份目录
robocopy "F:\Videos" "F:\Videos_Backup" /E /NFL /NDL /NJH /NJS
```

---

## 更新日志

### v6.0.0（当前版本）

**重大更新：项目规范化重构**
- 项目结构重构为 Python 包（src/title_classifier）
- CLI 命令统一为 `title-classifier` 命令
- 配置文件分离到 config/ 目录
- 测试框架完善

**重大更新：YOLO视觉分析集成**
- 集成 YOLOv8，支持检测、姿态估计、实例分割
- 视频全面分析模式，每2秒采样一帧
- 智能帧选择，基于姿态变化、置信度、关键点可见性
- 视频摘要生成，包含姿态分布、变化时间线

**重大更新：关键词提取优化**
- 水印博主名字设为最优先级
- 聚焦穿着、姿势、行为三个维度
- 过滤诈骗网址，只保留博主昵称

**重大更新：final_name渐进式填充**
- 阶段1（scanner）：final_name = proposed_title
- 阶段1c（vision）：final_name = [关键词]_原文件名
- 每个阶段都有值，不会出现空值问题

**重大更新：SRT字幕生成功能**
- 视觉描述写入SRT开头
- SRT文件名使用final_name格式
- 支持音频字幕追加（--audio参数）

**重大更新：GUI功能完善**
- Stage1b：AI优化结果预览表格，支持右键编辑
- Stage1c：YOLO/UHD检测器选择，YOLO模型多选
- Stage2：批量确认、批量清空功能
- 所有Provider显示完整

**其他改进**
- 修复YOLO模型多选参数问题
- 添加analysis-step采样间隔参数
- 添加vlm-frames VLM帧数参数
- 添加--all处理所有文件参数
- 添加--audio音频字幕参数

### v5.0.0
- CLIP 本地预分类，支持多标签输出
- 关键帧检测，基于帧差异自动检测视频关键帧
- 人体区域检测，专注人物穿着变化
- Embedding 变化检测，基于 CLIP embedding 相似度检测穿着变化
- 多帧 VLM，支持送入多帧给云端 VLM
- Stage1b AI优化支持预览编辑

### v4.0.0
- 支持图片文件（.jpg, .jpeg, .png, .bmp, .webp, .gif, .tiff）
- 人体检测预处理默认启用（UHD 超轻量模型）
- 新增智能压缩、水印优先功能

### v3.0.0
- 新增阶段 1c：视觉理解提取关键词
- 新增 gcli API 支持

### v2.0.0
- 新增阶段 1b：AI 优化标题
- 新增自动跳过已分类文件

### v1.0.0
- 双阶段安全重命名
- Jieba 分词 + TF-IDF 关键词提取

---

## 许可证

MIT License

---

**如有建议或需求，欢迎反馈！**
