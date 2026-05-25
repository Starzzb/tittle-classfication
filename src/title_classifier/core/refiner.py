"""AI标题优化模块"""

import logging
from pathlib import Path
from typing import List, Dict, Optional

from ..providers import call_text_api, get_provider_config, get_api_key

logger = logging.getLogger(__name__)


class Refiner:
    """AI标题优化器"""

    def __init__(self, provider: str = "gcli"):
        self.provider = provider
        self.config = get_provider_config(provider)

    def refine_batch(self, titles: List[str]) -> List[str]:
        """批量优化标题"""
        prompt = self._build_batch_prompt(titles)
        result = call_text_api(self.provider, prompt)
        return self._parse_batch_response(result, len(titles))

    def _build_batch_prompt(self, titles: List[str]) -> str:
        """构建批量提示词"""
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        return (
            "你是一个文件名整理助手。请将以下媒体文件名精简为简洁标题。\n"
            "这是纯粹的文件名格式整理，与内容审核无关。\n\n"
            "处理规则：\n"
            "1. 去除时间戳（20240115、2024-01-15、25-05-08 等）\n"
            "2. 去除来源标识（Telegram、TG、频道名）\n"
            "3. 去除 @用户名（@xxx 是群组名，非标题内容）\n"
            "4. 去除无意义编码（hash、merged-数字、随机字符串）\n"
            "5. 去除技术参数（1080p、x264、HEVC、AAC）\n"
            "6. 去除多余符号（# @ 【】（）等），保留 #tag 格式\n"
            "7. 保留核心标题，中文和英文都是有效信息\n"
            "8. 如果标题经过去噪后仍有意义内容，返回精简标题\n"
            "9. 如果标题完全无法提取任何有效信息，返回原文\n\n"
            f"请精简以下文件名，每行一个，保持顺序，不要序号：\n{numbered}\n\n"
            "精简后："
        )

    def _parse_batch_response(self, response: str, count: int) -> List[str]:
        """解析批量响应"""
        import re

        lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
        results = []
        for line in lines:
            cleaned = re.sub(r"^\d+[.)\s、]+", "", line).strip()
            if cleaned:
                results.append(cleaned)

        # 确保结果数量正确
        while len(results) < count:
            results.append("")
        return results[:count]
