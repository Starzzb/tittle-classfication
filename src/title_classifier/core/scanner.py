"""文件扫描模块"""

import re
import csv
import logging
import warnings
from pathlib import Path
from typing import List, Dict, Set, Optional

import jieba
import jieba.analyse

logger = logging.getLogger(__name__)

# 过滤非关键依赖警告
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

# 配置
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
TOP_KEYWORDS = 5

# 无意义词黑名单
BLACKLIST_WORDS = {
    "telegram", "tg", "group", "channel", "video", "mp4", "mkv",
    "hd", "fhd", "4k", "1080p", "720p", "480p", "2160p",
    "x264", "x265", "h264", "h265", "hevc", "aac", "flac",
    "bluray", "webrip", "webdl", "hdtv", "dvdrip", "brrip",
    "rarbg", "yts", "yify", "eztv",
}


def load_stopwords() -> Set[str]:
    """加载停用词"""
    return {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
        "着", "没有", "看", "好", "自己", "这", "那", "啊", "呢", "吧",
        "哦", "呀", "哇", "嗯", "哎", "啦", "吗", "！", "？", "。",
        "，", "、", "；", "：", """, """, "（", "）", "【", "】", "《", "》",
    }


def has_chinese(text: str) -> bool:
    """检查是否包含中文"""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def is_already_classified(name: str) -> bool:
    """检查是否已分类"""
    match = re.match(r"^\[([^\]]+)\]", name)
    if not match:
        return False
    tag_content = match.group(1)
    if tag_content == "未分类":
        return False
    return True


def is_needs_vision(original: str) -> bool:
    """判断是否需要视觉识别"""
    orig = original.strip()

    # 1. IMG/VID/DCIM 等设备前缀
    if re.match(r"^(IMG|VID|MOV|MP4|DCIM|P\d+)[_\-\s]?\d+", orig, re.IGNORECASE):
        return True

    # 2. Telegram 来源且无中文
    if re.search(r"(?i)telegram|(?<!\w)tg(?!\w)", orig) and not has_chinese(orig):
        cleaned = re.sub(r"(telegram|tg|@[\w]*|merged[-_]?\d*|[-_.\s\d\(\)\[\]【】]+)", "", orig, flags=re.IGNORECASE)
        cleaned = cleaned.strip("-_. ")
        if len(cleaned) < 3:
            return True

    # 3. 纯 hex/hash
    if re.match(r"^[a-f0-9]{8,}$", orig, re.IGNORECASE):
        return True

    # 4. 去除括号后纯数字
    stripped = re.sub(r"[\(\)\[\]【】（）\s\-_.]+", "", orig)
    if stripped.isdigit():
        return True

    # 5. 纯数字/分隔符
    if re.match(r"^[\d\-_.\s\(\)\[\]【】（）]+$", orig):
        return True

    # 6. 中文日期格式
    if re.match(r"^\d{1,2}月\d{1,2}日(\s*[\(\（]\d+[\)\）])*\s*$", orig):
        return True

    # 7. 无中文 + 数字占比>70%
    if not has_chinese(orig):
        core = re.sub(r"[\(\)\[\]【】（）\-_.\s]+", "", orig)
        if core:
            digit_ratio = len(re.findall(r"\d", core)) / len(core)
            if digit_ratio > 0.7:
                return True

    # 8. 中文无意义标题
    if has_chinese(orig):
        cleaned = re.sub(r"[\(\)\[\]【】（）\s\-_.]+", "", orig)
        if cleaned == "视频":
            return True
        if re.match(r"^视\d+频$", cleaned):
            return True

    return False


class Scanner:
    """文件扫描器"""

    def __init__(self, output_dir: str = "data/output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stopwords = load_stopwords()

    def scan(
        self,
        target_dir: str,
        output_file: str = None,
        append: bool = False,
        exclude_dirs: List[str] = None,
        force_reclassify: bool = False,
    ) -> str:
        """
        扫描目录并生成待审表

        Args:
            target_dir: 目标目录
            output_file: 输出文件路径
            append: 是否追加模式
            exclude_dirs: 排除的目录列表
            force_reclassify: 是否强制重新分类

        Returns:
            输出文件路径
        """
        target_path = Path(target_dir).resolve()
        if not target_path.exists():
            logger.error(f"目录不存在: {target_path}")
            return ""

        if output_file is None:
            output_file = str(self.output_dir / "title_review.csv")

        logger.info(f"开始递归扫描: {target_path}")

        # 扫描文件
        files = self._scan_directory(target_path, exclude_dirs or [])
        logger.info(f"找到 {len(files)} 个媒体文件")

        # 处理文件
        rows = []
        for file_path in files:
            row = self._process_file(file_path, force_reclassify)
            if row:
                rows.append(row)

        # 保存结果
        if rows:
            self._save_csv(rows, output_file, append)
            logger.info(f"新增 {len(rows)} 条记录")
        else:
            logger.info("没有新文件需要处理")

        return output_file

    def _scan_directory(self, directory: Path, exclude_dirs: List[str]) -> List[Path]:
        """递归扫描目录"""
        files = []
        exclude_set = set(exclude_dirs)

        for item in directory.rglob("*"):
            # 检查是否在排除目录中
            rel_path = item.relative_to(directory)
            if any(excluded in str(rel_path) for excluded in exclude_set):
                continue

            if item.is_file() and item.suffix.lower() in MEDIA_EXTENSIONS:
                files.append(item)

        return sorted(files)

    def _process_file(self, file_path: Path, force_reclassify: bool = False) -> Optional[Dict]:
        """处理单个文件"""
        name = file_path.stem
        original_title = file_path.name

        # 检查是否已分类
        if is_already_classified(name) and not force_reclassify:
            return None

        # 分词提取关键词
        keywords = self._extract_keywords(name)

        # 判断是否需要视觉识别
        needs_vision = is_needs_vision(original_title)

        # 生成建议标题
        proposed_title = self._generate_proposed_title(keywords, name)

        return {
            "original_title": original_title,
            "original_path": str(file_path),
            "proposed_title": proposed_title,
            "keywords": ", ".join(keywords),
            "needs_vision": str(needs_vision).lower(),
            "final_name": "",
            "review_status": "待确认",
            "vision_description": "",
            "vision_keywords": "",
            "human_detected": "",
            "detection_confidence": "",
            "detection_timestamp": "",
            "detection_method": "",
            "clip_clothing": "",
            "clip_action": "",
            "clip_hairstyle": "",
            "clip_tags": "",
            "clip_tags_json": "",
            "clip_confidence": "",
            "vision_source": "",
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 清理文本
        cleaned = re.sub(r"[\(\)\[\]【】（）\-_.\s]+", " ", text)
        cleaned = cleaned.strip()

        if not cleaned:
            return []

        # 使用jieba分词
        words = jieba.cut(cleaned)
        keywords = []

        for word in words:
            word = word.strip()
            if not word or len(word) < 2:
                continue
            if word.lower() in BLACKLIST_WORDS:
                continue
            if word in self.stopwords:
                continue
            keywords.append(word)

        # 使用TF-IDF提取关键词
        try:
            tfidf_keywords = jieba.analyse.extract_tags(cleaned, topK=TOP_KEYWORDS)
            for kw in tfidf_keywords:
                if kw not in keywords and kw.lower() not in BLACKLIST_WORDS:
                    keywords.append(kw)
        except:
            pass

        return keywords[:TOP_KEYWORDS]

    def _generate_proposed_title(self, keywords: List[str], original: str) -> str:
        """生成建议标题"""
        if keywords:
            return "_".join(keywords[:3])
        return original

    def _save_csv(self, rows: List[Dict], output_file: str, append: bool = False) -> None:
        """保存CSV文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "original_title", "original_path", "proposed_title", "keywords",
            "needs_vision", "final_name", "review_status",
            "vision_description", "vision_keywords",
            "human_detected", "detection_confidence", "detection_timestamp", "detection_method",
            "clip_clothing", "clip_action", "clip_hairstyle",
            "clip_tags", "clip_tags_json", "clip_confidence", "vision_source",
        ]

        mode = "a" if append else "w"
        with open(output_path, mode, encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not append or output_path.stat().st_size == 0:
                writer.writeheader()
            writer.writerows(rows)

        logger.info(f"结果已保存至: {output_path}")
