# 视频标题批量标准化重命名工具

## 📋 目录

- [项目简介](#项目简介)
- [核心功能](#核心功能)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [快速开始](#快速开始)
- [阶段一：扫描与生成](#阶段一扫描与生成)
- [阶段二：核对与重命名](#阶段二核对与重命名)
- [参数详解](#参数详解)
- [高级功能](#高级功能)
- [常见问题](#常见问题)
- [最佳实践](#最佳实践)

---

## 项目简介

本工具是一套**双阶段视频文件批量重命名系统**，专为本地视频库管理设计。通过智能分词与关键词提取，将杂乱的视频文件名转换为**标准化、可检索、语义清晰**的格式，同时保证操作的安全性与可逆性。

**适用场景**：
- 整理下载目录中的大量视频文件
- 为视频库建立统一命名规范
- 为后续AI分类/标签系统准备数据
- 批量清理历史遗留的混乱文件名

---

## 核心功能

| 功能模块 | 特性描述 |
|---------|---------|
| 🔍 **智能扫描** | 递归遍历指定目录，支持10+种视频格式，自动跳过损坏/无权限目录 |
| 🧠 **语义分析** | 基于 Jieba 分词 + TF-IDF 算法，自动提取标题核心关键词 |
| 📝 **安全预览** | 双阶段设计，先生成待审表，人工确认后再执行，零风险操作 |
| 🛡️ **冲突避让** | 自动检测文件名冲突，智能追加序号（`_1`, `_2`），防止覆盖 |
| 🔄 **增量模式** | 支持多次扫描追加记录，适合分批处理大型视频库 |
| 🚫 **目录排除** | 灵活排除特定目录（按名称/路径），避免扫描系统文件夹 |
| 📊 **详细日志** | 生成执行日志与错误报告，便于审计与问题排查 |

---

## 环境要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.8+ | 推荐 3.10+ |
| 操作系统 | Windows / macOS / Linux | 全平台兼容 |
| 磁盘空间 | ≥ 100MB | 用于安装依赖与缓存 |
| 权限要求 | 目标目录读写权限 | 必需 |

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

**或使用 pip**：
```bash
pip install uv
```

### 2. 克隆或下载项目文件

将以下文件保存到同一目录（例如 `D:\video-renamer\`）：
- `stage1_extract_propose.py`
- `stage2_apply_rename.py`

### 3. 创建虚拟环境并安装依赖

```powershell
# 进入项目目录
cd D:\video-renamer

# 创建虚拟环境（自动检测 Python 版本）
uv venv --python 3.10

# 激活虚拟环境（Windows）
.\.venv\Scripts\activate

# 安装依赖
uv pip install jieba
```

> 💡 **提示**：使用 `uv run` 命令可自动激活环境，无需手动执行 `activate`。

---

## 快速开始

### 典型工作流程

```powershell
# 步骤1：扫描目录并生成待审表
uv run python stage1_extract_propose.py -d "F:\Videos"

# 步骤2：用文本编辑器打开 CSV，核对并修改
notepad title_review.csv

# 步骤3：模拟运行，预览结果
uv run python stage2_apply_rename.py --dry-run

# 步骤4：确认无误，执行重命名
uv run python stage2_apply_rename.py
```

**执行时间参考**：
- 100 个视频：约 5-10 秒
- 1,000 个视频：约 30-60 秒
- 10,000 个视频：约 5-10 分钟

---

## 阶段一：扫描与生成

### 功能说明

递归扫描指定目录中的所有视频文件，提取文件名，通过分词算法生成标准化建议名称，输出为 CSV 待审表。

### 基本用法

```powershell
# 扫描单个目录
uv run python stage1_extract_propose.py -d "F:\Download"

# 扫描并指定输出文件
uv run python stage1_extract_propose.py -d "F:\Download" -o "my_review.csv"

# 排除特定目录
uv run python stage1_extract_propose.py -d "F:\Download" --exclude-dir "temp"

# 排除多个目录
uv run python stage1_extract_propose.py -d "F:\Download" \
  --exclude-dir "temp" \
  --exclude-dir "cache" \
  --exclude-dir "F:\Download\broken"

# 追加模式（保留旧记录）
uv run python stage1_extract_propose.py -d "E:\Movies" -a
```

### 参数说明

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--target-dir` | `-d` | **必需** | - | 要扫描的视频目录路径（支持相对/绝对路径） |
| `--output` | `-o` | 可选 | `title_review.csv` | 输出待审表文件名 |
| `--append` | `-a` | 可选 | `False` | 启用追加模式，在现有 CSV 末尾添加新记录 |
| `--exclude-dir` | - | 可选（可多次） | - | 排除的目录名或绝对路径 |

### 输出文件结构

生成的 `title_review.csv` 包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| `original_path` | 视频文件绝对路径 | `F:\Videos\abc.mp4` |
| `original_title` | 原始文件名（不含扩展名） | `Python入门教程` |
| `proposed_title` | 算法生成的建议名称 | `[Python_入门_教程]_Python入门教程` |
| `review_status` | 审核状态（默认"待审核"） | `待审核` |
| `final_name` | 最终采用的名称（默认同 proposed_title） | `[Python_入门_教程]_Python入门教程` |

### 命名规则

算法生成的新名称格式为：
```
[关键词1_关键词2_关键词3]_原始文件名.扩展名
```

**关键词提取逻辑**：
1. 使用 TF-IDF 算法对文件名分词并计算权重
2. 过滤停用词（的、了、在、如何等）
3. 过滤单字（长度 ≤ 1）
4. 取权重最高的前 3 个词作为前缀
5. 移除非法字符（`<>:"/\|?*`）

**示例**：
```
原始：Python入门教程：30分钟学会基础语法.mp4
新名：[Python_入门_教程]_Python入门教程：30分钟学会基础语法.mp4

原始：小米14开箱！这配置太顶了.mkv
新名：[小米_开箱_配置]_小米14开箱！这配置太顶了.mkv
```

---

## 阶段二：核对与重命名

### 功能说明

读取阶段一生成的 CSV 待审表，仅对标记为"已确认"的记录执行安全重命名，自动处理冲突与异常。

### 基本用法

```powershell
# 模拟运行（推荐首次执行）
uv run python stage2_apply_rename.py --dry-run

# 正式执行
uv run python stage2_apply_rename.py

# 指定自定义 CSV 路径
uv run python stage2_apply_rename.py -c "E:\work\review.csv"

# 模拟运行 + 指定 CSV
uv run python stage2_apply_rename.py -c "E:\work\review.csv" --dry-run
```

### 人工核对流程

1. **打开 CSV 文件**
   ```powershell
   # 使用记事本
   notepad title_review.csv
   
   # 或使用 VS Code（推荐）
   code title_review.csv
   ```

2. **编辑审核状态**
   - 将需要重命名的行，`review_status` 列改为 **`已确认`**
   - 保持不需要的行为"待审核"或直接删除该行
   - 可修改 `final_name` 列自定义最终名称

3. **保存文件**
   - **编码必须为 UTF-8 with BOM**（Excel 兼容性）
   - 保持 CSV 格式，不要修改列名

4. **模拟验证**
   ```powershell
   uv run python stage2_apply_rename.py --dry-run
   ```
   检查终端输出，确认所有变更符合预期

5. **执行重命名**
   ```powershell
   uv run python stage2_apply_rename.py
   ```

### 参数说明

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--csv` | `-c` | 可选 | `title_review.csv` | 待审表文件路径 |
| `--dry-run` | - | 可选 | `False` | 模拟模式，仅打印不执行 |

### 执行结果解读

**终端输出示例**：
```text
读取审核文件: D:\video-renamer\title_review.csv
[成功] Python入门教程.mp4 -> [Python_入门_教程]_Python入门教程.mp4
[冲突解决] 小米14开箱.mkv -> [小米_开箱_配置]_小米14开箱_1.mkv
[跳过] 名称未变更: 已处理.avi

============================================================
执行摘要
============================================================
待审记录总数: 150
标记为'已确认': 120
✅ 重命名成功: 118
⚠️  名称未变更: 2
🔄 冲突已避让: 3
❌ 执行失败: 0
============================================================
详细日志: D:\video-renamer\rename_log.txt
```

**状态码说明**：
| 状态 | 含义 | 处理建议 |
|------|------|---------|
| ✅ 成功 | 文件已重命名 | 无需操作 |
| ⚠️ 跳过 | 新旧名称相同或状态非"已确认" | 检查 CSV 状态列 |
| 🔄 冲突 | 目标名称已存在，自动追加序号 | 检查是否有重复文件 |
| ❌ 失败 | 权限不足/文件占用/路径错误 | 查看日志文件详情 |

### 日志文件

执行后生成 `rename_log.txt`，包含时间戳与详细操作记录：
```text
[2024-04-11 14:30:15] [成功] Python入门教程.mp4 -> [Python_入门_教程]_Python入门教程.mp4
[2024-04-11 14:30:16] [冲突解决] 小米14开箱.mkv -> [小米_开箱_配置]_小米14开箱_1.mkv
[2024-04-11 14:30:17] [警告] 源文件已移动或删除: F:\Videos\deleted.mp4
```

---

## 参数详解

### 阶段一完整参数表

```powershell
uv run python stage1_extract_propose.py \
  -d "F:\Videos" \                    # 必需：扫描目录
  -o "review.csv" \                   # 可选：输出文件名
  -a \                                # 可选：追加模式
  --exclude-dir "temp" \              # 可选：排除目录名
  --exclude-dir "cache" \             # 可选：可多次使用
  --exclude-dir "F:\Videos\broken"    # 可选：排除绝对路径
```

### 阶段二完整参数表

```powershell
uv run python stage2_apply_rename.py \
  -c "review.csv" \                   # 可选：CSV 路径
  --dry-run                           # 可选：模拟模式
```

---

## 高级功能

### 1. 自定义关键词数量

编辑 `stage1_extract_propose.py`，修改顶部配置：
```python
TOP_KEYWORDS = 5  # 默认 3，改为 5 可提取更多关键词
```

### 2. 自定义停用词表

在 `load_stopwords()` 函数中添加自定义词汇：
```python
def load_stopwords() -> set:
    return {
        "的", "了", "在", 
        "你的词1",  # 添加此行
        "你的词2",  # 添加此行
        # ...
    }
```

### 3. 强制保留特定关键词

修改 `process_title()` 函数，添加白名单逻辑：
```python
force_keywords = {"教程", "评测", "开箱"}
# 确保这些词永远出现在前缀中
```

### 4. 批量处理多个目录

创建批处理脚本 `batch_scan.bat`（Windows）：
```batch
@echo off
set SCRIPT=stage1_extract_propose.py

uv run python %SCRIPT% -d "F:\Videos" -o "review.csv"
uv run python %SCRIPT% -d "G:\Movies" -a -o "review.csv"
uv run python %SCRIPT% -d "H:\Downloads" -a -o "review.csv"

echo 所有目录扫描完成！
pause
```

### 5. 仅处理特定格式

编辑 `VIDEO_EXTENSIONS` 集合：
```python
VIDEO_EXTENSIONS = {'.mp4', '.mkv'}  # 仅处理 MP4 和 MKV
```

### 6. 生成统计报告

在阶段一结束后添加统计代码：
```python
# 按目录统计
from collections import Counter
dir_counts = Counter(Path(r['original_path']).parent for r in records)
print("目录分布:", dir_counts.most_common(10))
```

---

## 常见问题

### Q1：提示"文件或目录损坏且无法读取"

**原因**：目标目录包含损坏的文件夹或无权限访问的系统目录。

**解决**：
```powershell
# 使用排除参数跳过问题目录
uv run python stage1_extract_propose.py -d "F:\" --exclude-dir "F:\Download\love"
```

### Q2：CSV 在 Excel 中打开乱码

**原因**：编码不是 UTF-8 with BOM。

**解决**：
1. 用 VS Code 打开 CSV
2. 右下角点击编码 → "通过编码保存"
3. 选择 "UTF-8 with BOM"
4. 重新用 Excel 打开

### Q3：重命名后文件"消失"了

**原因**：文件仍在原目录，只是名称变了。

**解决**：
- 在资源管理器中按"修改时间"排序
- 或搜索新名称中的关键词

### Q4：提示"权限不足"或"文件被占用"

**原因**：
- 视频正在被播放器打开
- 资源管理器预览窗格锁定文件
- 杀毒软件实时扫描

**解决**：
1. 关闭所有播放器
2. 关闭资源管理器预览窗格
3. 以管理员身份运行终端
4. 重启电脑后重试

### Q5：如何撤销重命名？

**方法 1**：从 CSV 的 `original_title` 列手动还原

**方法 2**：执行前备份目录
```powershell
robocopy "F:\Videos" "F:\Videos_Backup" /E /NFL /NDL /NJH /NJS
```

**方法 3**：使用版本控制（适合技术人员）
```bash
git init
git add *.mp4
# 执行重命名后
git diff --name-only  # 查看变更
git checkout -- .     # 撤销所有变更
```

### Q6：想提取所有分词，不只前3个

修改 `process_title()` 函数：
```python
def process_title(original: str, stopwords: set) -> str:
    words = jieba.lcut(original)
    valid_words = [w for w in words if w not in stopwords and len(w) > 1]
    prefix = "_".join(valid_words[:10])  # 改为前10个，或移除 [:10]
    # ...
```

### Q7：扫描速度太慢

**优化方案**：
1. 排除无关目录（`--exclude-dir`）
2. 仅扫描特定子目录，而非整个磁盘
3. 关闭杀毒软件实时防护（临时）
4. 使用 SSD 而非机械硬盘

### Q8：支持网络驱动器吗？

**支持**，但需注意：
- 确保有读写权限
- 网络延迟可能导致速度较慢
- 建议使用 UNC 路径（`\\server\share`）而非映射驱动器

---

## 最佳实践

### 1. 分批处理大型视频库

```powershell
# 第1批：扫描 F:\Videos\A-M
uv run python stage1_extract_propose.py -d "F:\Videos\A-M" -o "batch1.csv"

# 第2批：扫描 F:\Videos\N-Z（追加模式）
uv run python stage1_extract_propose.py -d "F:\Videos\N-Z" -a -o "batch1.csv"

# 合并后统一核对
notepad batch1.csv
```

### 2. 建立命名规范文档

在项目中创建 `NAMING_RULES.md`：
```markdown
# 视频命名规范

格式：[关键词1_关键词2_关键词3]_原始标题.ext

示例：
✅ [Python_教程_入门]_Python基础语法讲解.mp4
✅ [原神_攻略_4.5]_新角色强度分析.mkv
❌ 教程.mp4  (关键词不足)
❌ [a_b_c_d_e_f]_标题.mp4  (关键词过多)
```

### 3. 定期增量扫描

```powershell
# 每周五扫描新增视频
uv run python stage1_extract_propose.py -d "F:\Videos" -a -o "weekly_review.csv"
```

### 4. 集成到自动化流程

创建 PowerShell 脚本 `auto_rename.ps1`：
```powershell
param($TargetDir)

# 阶段一
python stage1_extract_propose.py -d $TargetDir

# 自动确认所有记录（谨慎使用！）
$csv = Import-Csv title_review.csv
$csv | ForEach-Object { $_.review_status = "已确认" }
$csv | Export-Csv title_review.csv -NoTypeEncoding -Encoding UTF8

# 阶段二
python stage2_apply_rename.py --dry-run
Write-Host "模拟完成，按任意键继续执行..."
pause
python stage2_apply_rename.py
```

### 5. 质量检查清单

执行前确认：
- [ ] 已备份重要数据
- [ ] 已运行 `--dry-run` 并检查输出
- [ ] CSV 编码为 UTF-8 with BOM
- [ ] 无视频文件正在被占用
- [ ] 磁盘空间充足（重命名不占空间，但需预留日志空间）
- [ ] 已排除系统目录与临时文件夹

---

## 技术支持

**问题反馈**：
- 检查 `scan_errors.log` 和 `rename_log.txt`
- 提供终端完整输出
- 提供问题 CSV 行的截图（脱敏敏感信息）

**性能优化建议**：
- 10,000+ 视频：建议使用 SSD 并排除无关目录
- 100,000+ 视频：分批处理，每批 ≤ 20,000 个文件
- 网络驱动器：使用本地缓存或映射为网络驱动器

---

## 更新日志

### v1.0.0（当前版本）
- ✅ 双阶段安全重命名
- ✅ Jieba 分词 + TF-IDF 关键词提取
- ✅ 目录排除功能
- ✅ 增量追加模式
- ✅ 冲突自动避让
- ✅ 详细日志系统

---

**祝您使用愉快！如有建议或需求，欢迎反馈。** 🎬