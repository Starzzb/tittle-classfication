# stage1_extract_propose.py
import argparse
import re
import csv
import os
import warnings
from pathlib import Path
import jieba
import jieba.analyse

# ================= 配置区 =================
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.m4v', '.ts'}
TOP_KEYWORDS = 5
LOG_FILE = "scan_errors.log"
# ==========================================

# 过滤非关键依赖警告
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

def load_stopwords() -> set:
    return {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", 
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", 
        "着", "没有", "看", "好", "自己", "这", "那", "啊", "呢", "吧", 
        "哦", "呀", "哇", "嗯", "哎", "啦", "吗", "！", "？", "。", 
        "，", "、", "；", "：", "“", "”", "（", "）", "【", "】", "《", "》"
    }

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def process_title(original: str, stopwords: set) -> str:
    if not original.strip():
        return "未命名"
    try:
        keywords = jieba.analyse.extract_tags(original, topK=TOP_KEYWORDS * 2)
        valid_kw = [k for k in keywords if k not in stopwords and len(k.strip()) > 1]
        prefix = "_".join(valid_kw[:TOP_KEYWORDS]) if valid_kw else "未分类"
        return sanitize_filename(f"[{prefix}]_{original}")
    except Exception:
        return sanitize_filename(original)

def should_skip_dir(dir_path: Path, exclude_names: set, exclude_paths: set) -> bool:
    """判断目录是否应该被跳过"""
    dir_name = dir_path.name
    dir_abs = str(dir_path.resolve())
    
    # 1. 按目录名排除（如排除所有名为 "love" 的文件夹）
    if dir_name in exclude_names:
        return True
    # 2. 按绝对路径排除（如只排除 "F:\Download\love"）
    if dir_abs in exclude_paths:
        return True
    # 3. 按路径包含关系排除（如排除所有含 "temp" 的路径）
    if any(exclude in dir_abs for exclude in exclude_paths if '*' not in exclude):
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="阶段一：递归扫描视频文件，支持排除指定目录")
    parser.add_argument("-d", "--target-dir", type=str, required=True, help="指定要扫描的视频目录路径")
    parser.add_argument("-o", "--output", type=str, default="title_review.csv", help="输出待审表路径")
    parser.add_argument("-a", "--append", action="store_true", help="启用追加模式")
    parser.add_argument("--exclude-dir", action="append", default=[], 
                        help="排除的目录名或路径（可多次使用，如 --exclude-dir love --exclude-dir 'F:\\test'）")
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    if not target_dir.is_dir():
        print(f"错误: 指定的目录不存在 -> {target_dir}")
        return

    # 解析排除规则
    exclude_names = set()
    exclude_paths = set()
    for ex in args.exclude_dir:
        ex_path = Path(ex)
        if ex_path.is_absolute():
            exclude_paths.add(str(ex_path.resolve()))
        else:
            # 相对路径或纯目录名
            exclude_names.add(ex)
            exclude_paths.add(str(ex_path.resolve()))

    print(f"开始递归扫描: {target_dir}")
    if exclude_names or exclude_paths:
        print(f"🚫 排除规则: 目录名={exclude_names}, 路径={exclude_paths}")
    
    jieba.initialize()
    
    records = []
    stopwords = load_stopwords()
    scanned_count = 0
    
    # ✅ 使用 os.walk 实现剪枝遍历
    for root, dirs, files in os.walk(target_dir, followlinks=False):
        root_path = Path(root)
        
        # 🔥 关键：原地修改 dirs 列表，实现目录剪枝
        # 复制列表避免遍历中修改导致的错误
        for d in dirs[:]:
            dir_path = root_path / d
            if should_skip_dir(dir_path, exclude_names, exclude_paths):
                dirs.remove(d)  # 从遍历队列中移除，不会进入该子目录
                print(f"  ⏭️  跳过目录: {dir_path}")
        
        # 处理当前目录下的文件
        for file_name in files:
            file_path = root_path / file_name
            if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                try:
                    original_name = file_path.stem
                    proposed_name = process_title(original_name, stopwords)
                    records.append({
                        "original_path": str(file_path.resolve()),
                        "original_title": original_name,
                        "proposed_title": proposed_name,
                        "review_status": "待审核",
                        "final_name": proposed_name
                    })
                    scanned_count += 1
                    if scanned_count % 100 == 0:
                        print(f"  已处理: {scanned_count} 个视频...", end='\r')
                except Exception as e:
                    with open(LOG_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"[文件处理错误] {e}: {file_path}\n")
                    continue

    # 写入 CSV
    output_path = Path(args.output)
    file_exists = output_path.exists()
    write_header = not (args.append and file_exists)
    mode = 'a' if args.append else 'w'
    
    try:
        with open(output_path, mode, encoding='utf-8-sig', newline='') as f:
            fieldnames = ["original_path", "original_title", "proposed_title", "review_status", "final_name"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerows(records)
            
        print(f"\n✅ 扫描完成。")
        print(f"📊 统计: 新增 {len(records)} 条记录")
        print(f"📁 结果已保存至: {output_path.resolve()}")
    except PermissionError:
        print(f"\n❌ 错误: 无法写入文件 {output_path}，请检查是否被其他程序占用。")

if __name__ == "__main__":
    main()