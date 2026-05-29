"""原子化 CSV 读写 — 写入中断不会损坏原文件"""

import csv
import os
import tempfile
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def atomic_write_csv(
    csv_path: str,
    rows: List[Dict],
    fieldnames: List[str],
    encoding: str = "utf-8-sig",
) -> None:
    """
    原子化写入 CSV 文件。

    写入过程：
    1. 写入同目录的临时文件（原文件不受影响）
    2. os.replace() 原子替换原文件

    即使在步骤 1 和 2 之间崩溃，原文件仍然完好。
    """
    csv_path = os.path.abspath(csv_path)
    csv_dir = os.path.dirname(csv_path) or "."

    # 确保目录存在
    os.makedirs(csv_dir, exist_ok=True)

    # 步骤 1: 写入临时文件
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=csv_dir, suffix=".tmp", prefix=".csv_"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding=encoding, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # 步骤 2: 原子替换
        os.replace(tmp_path, csv_path)

    except Exception:
        # 失败时清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_append_csv(
    csv_path: str,
    rows: List[Dict],
    fieldnames: List[str],
    encoding: str = "utf-8-sig",
) -> None:
    """
    原子化追加写入 CSV 文件。

    读取原文件内容，追加新行后原子替换。
    """
    csv_path = os.path.abspath(csv_path)

    # 如果文件已存在，先读取原有内容
    existing_rows = []
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding=encoding) as f:
                reader = csv.DictReader(f)
                existing_rows = list(reader)
        except Exception as e:
            logger.warning(f"读取现有 CSV 失败，将覆盖: {e}")

    # 合并：保留已有的，追加新的
    existing_paths = {
        row.get("original_path") for row in existing_rows if row.get("original_path")
    }
    for row in rows:
        if row.get("original_path") not in existing_paths:
            existing_rows.append(row)

    # 原子写入合并后的结果
    atomic_write_csv(csv_path, existing_rows, fieldnames, encoding)


def safe_read_csv(
    csv_path: str,
    encoding: str = "utf-8-sig",
) -> tuple:
    """
    安全读取 CSV 文件。

    Returns:
        (fieldnames, rows) — 失败时返回 ([], [])
    """
    csv_path = os.path.abspath(csv_path)
    if not os.path.exists(csv_path):
        logger.error(f"CSV 文件不存在: {csv_path}")
        return [], []

    try:
        with open(csv_path, "r", encoding=encoding) as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames) if reader.fieldnames else []
            rows = list(reader)
            return fieldnames, rows
    except Exception as e:
        logger.error(f"读取 CSV 失败: {e}")
        return [], []
