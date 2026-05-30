"""文件路径解析工具 - 处理Stage2重命名后的路径回退"""

import re
from pathlib import Path

# 项目支持的媒体扩展名
_MEDIA_EXT = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts",
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff",
}


def _strip_bracket_prefix(name: str) -> str:
    """去除文件名开头的 [关键词]_ 前缀"""
    return re.sub(r"^\[[^\]]*\]_?", "", name, count=1)


def resolve_media_path(original_path: str, final_name: str = "", original_title: str = "") -> str:
    """
    解析媒体文件的实际路径（三级回退）。

    Stage2重命名后，CSV中的 original_path 可能指向旧文件名。
    此函数按优先级尝试三种方式找到文件：

    1. 直接用 original_path
    2. 用 final_name 在同目录下拼路径
    3. 在同目录下搜索：文件名去掉 [关键词]_ 前缀后与 original_title 匹配

    Args:
        original_path: CSV中记录的原始路径
        final_name: Stage1b/Stage1c写入的最终文件名（不含扩展名）
        original_title: 原始文件名（含扩展名，如 video.mp4）

    Returns:
        解析后的文件路径（str），找不到则返回空字符串 ""
    """
    if not original_path:
        return ""

    p = Path(original_path)
    if p.exists():
        return str(p)

    # 回退1: 用 final_name 在同目录下拼路径
    if final_name:
        candidate = p.parent / f"{final_name}{p.suffix}"
        if candidate.exists():
            return str(candidate)

    # 回退2: 按 original_title 的 stem 在同目录下搜索（去掉 [关键词]_ 前缀后匹配）
    if original_title:
        target_stem = Path(original_title).stem  # e.g. "video"
        try:
            for f in p.parent.iterdir():
                if not f.is_file() or f.suffix.lower() not in _MEDIA_EXT:
                    continue
                # 去掉 [关键词]_ 前缀后比较 stem
                clean_stem = _strip_bracket_prefix(f.stem)
                if clean_stem == target_stem:
                    return str(f)
        except OSError:
            pass

    return ""
