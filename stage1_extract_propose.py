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
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif', '.tiff'}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
TOP_KEYWORDS = 5
LOG_FILE = "logs/scan_errors.log"

# 无意义词黑名单（小写匹配）
BLACKLIST_WORDS = {
    "telegram", "tg", "group", "channel", "video", "mp4", "mkv",
    "hd", "fhd", "4k", "1080p", "720p", "480p", "2160p",
    "x264", "x265", "h264", "h265", "hevc", "aac", "flac",
    "bluray", "webrip", "webdl", "hdtv", "dvdrip", "brrip",
    "rarbg", "yts", "yify", "eztv",
}
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

def is_already_classified(name: str) -> bool:
    """检查是否已分类，但[未分类]不算已分类"""
    match = re.match(r'^\[([^\]]+)\]', name)
    if not match:
        return False
    tag_content = match.group(1)
    # [未分类]不算已分类，需要重新处理
    if tag_content == "未分类":
        return False
    return True

def is_meaningless_tag(tag: str) -> bool:
    """检测中括号内的标签是否是无意义的（如程序生成的hash）"""
    # 纯字母数字混合，长度>=8，且包含大小写字母和数字
    if len(tag) >= 8 and re.match(r'^[a-zA-Z0-9]+$', tag):
        has_upper = bool(re.search(r'[A-Z]', tag))
        has_lower = bool(re.search(r'[a-z]', tag))
        has_digit = bool(re.search(r'[0-9]', tag))
        if has_upper and has_lower and has_digit:
            return True
    return False

def has_chinese(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def is_needs_vision(original: str) -> bool:
    orig = original.strip()

    # 1. IMG/VID/DCIM 等设备前缀
    if re.match(r'^(IMG|VID|MOV|MP4|DCIM|P\d+)[_\-\s]?\d+', orig, re.IGNORECASE):
        return True

    # 2. Telegram 来源且无中文
    if re.search(r'(?i)telegram|(?<!\w)tg(?!\w)', orig) and not has_chinese(orig):
        cleaned = re.sub(r'(telegram|tg|@[\w]*|merged[-_]?\d*|[-_.\s\d\(\)\[\]【】]+)', '', orig, flags=re.IGNORECASE)
        cleaned = cleaned.strip('-_. ')
        if len(cleaned) < 3:
            return True

    # 3. v(数字)-Telegram-@ 模式
    if re.search(r'(?i)\bv\s*[\(\[\{]?\d+[\)\]\}]?\s*[-_]?\s*(telegram|@)', orig):
        return True

    # 4. @群组名无实质内容
    at_parts = re.findall(r'@[\w]+', orig)
    remaining = re.sub(r'@[\w]+', '', orig)
    remaining = re.sub(r'[-_.\s\d]+', '', remaining)
    remaining = re.sub(r'(telegram|tg|merged|video|mp4|mov)', '', remaining, flags=re.IGNORECASE)
    if at_parts and len(remaining) < 3:
        return True

    # 5. 纯 hex/hash
    if re.match(r'^[a-f0-9]{8,}$', orig, re.IGNORECASE):
        return True

    # 6. 去除括号后纯数字（如 (22331)、-22331、(3343)）
    stripped = re.sub(r'[\(\)\[\]【】（）\s\-_.]+', '', orig)
    if stripped.isdigit():
        return True

    # 7. 纯数字/分隔符（含括号）
    if re.match(r'^[\d\-_.\s\(\)\[\]【】（）]+$', orig):
        return True

    # 8. 中文日期格式
    if re.match(r'^\d{1,2}月\d{1,2}日(\s*[\(\（]\d+[\)\）])*\s*$', orig):
        return True

    # 9. merged-时间戳后缀
    if re.search(r'-merged-\d{10,}', orig):
        cleaned = re.sub(r'-merged-\d{10,}', '', orig)
        cleaned = re.sub(r'(telegram|tg|@[\w]+|\d+[-_.\s]*)', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip('-_. ')
        if len(cleaned) < 3:
            return True

    # 10. 无中文 + 数字+短词混合（如 3video、1 (11)、abc123）
    if not has_chinese(orig):
        # 去除括号和分隔符后，检查是否大部分是数字
        core = re.sub(r'[\(\)\[\]【】（）\-_.\s]+', '', orig)
        if core:
            digit_ratio = len(re.findall(r'\d', core)) / len(core)
            # 纯数字或数字占比>70%且无中文
            if digit_ratio > 0.7:
                return True

    # 10b. 无中文 + 数字+常见无意义词（如 3video (1)、2photo、1image）
    if not has_chinese(orig):
        if re.match(r'^\d+\s*(video|photo|image|pic|img|vid|movie|clip|file|doc)(\s*[\(\[]?\d*[\)\]]?)*$', orig, re.IGNORECASE):
            return True

    # 10c. 中文无意义标题：视频/视+数字+频 等模式
    # 如：视334频、视34频、视3频、视频 (5)、视频
    if has_chinese(orig):
        # 去除括号和分隔符
        cleaned = re.sub(r'[\(\)\[\]【】（）\s\-_.]+', '', orig)
        # 纯"视频"
        if cleaned == '视频':
            return True
        # "视" + 数字 + "频"
        if re.match(r'^视\d+频$', cleaned):
            return True
        # "视频" + 纯数字（如 视频5、视频 (5)）
        if re.match(r'^视频\d*$', cleaned):
            return True

    # 11. 无中文 + 含域名/网址模式（如 cybl.cc、sifangds.com）
    if not has_chinese(orig):
        if re.search(r'(?i)(\.cc|\.com|\.net|\.org|\.vip|\.me|\.tv|http|www)', orig):
            # 去除域名和分隔符后，剩余内容很短
            cleaned = re.sub(r'(?i)([\w]+\.(cc|com|net|org|vip|me|tv)|http[\w://]*|www\.[\w.]+)', '', orig)
            cleaned = re.sub(r'[\(\)\[\]【】（）\-_.\s\d]+', '', cleaned)
            if len(cleaned) < 3:
                return True

    # 12. 无中文 + 纯字母数字混合 >=8 位（大小写+数字）
    if not has_chinese(orig):
        alphanum = re.sub(r'[^a-zA-Z0-9]', '', orig)
        if len(alphanum) >= 8:
            has_upper = bool(re.search(r'[A-Z]', alphanum))
            has_lower = bool(re.search(r'[a-z]', alphanum))
            has_digit = bool(re.search(r'[0-9]', alphanum))
            if has_upper and has_lower and has_digit:
                return True

    # 13. 长 hex 比例
    if not has_chinese(orig):
        alphanum = re.sub(r'[^a-zA-Z0-9]', '', orig)
        if len(alphanum) > 0:
            hex_ratio = len(re.findall(r'[0-9a-fA-F]', alphanum)) / len(alphanum)
            if hex_ratio > 0.7 and len(alphanum) >= 12:
                return True

    # 14. 下划线+空格/字母开头（如 _V (1).mp4）
    if re.match(r'^_[A-Za-z]?\s*[\(\[]?\d*[\)\]]?', orig) and not has_chinese(orig):
        return True

    # 15. 短标题检测：标题过短且非#tag格式，视为无意义
    # 有效内容 = 去除括号、数字、分隔符后的核心文字
    # 如：[Pavid2eo (1)、vide2o (1)、video (1)、視頻
    if not orig.startswith('#'):
        # 去除扩展名
        name_without_ext = re.sub(r'\.[a-zA-Z0-9]+$', '', orig)
        # 去除括号、数字、分隔符，保留核心文字
        core_text = re.sub(r'[\(\)\[\]【】（）\d\-_.\s]+', '', name_without_ext)
        # 计算核心文字长度
        core_len = len(core_text)
        
        # 中文字符计数
        cn_count = len(re.findall(r'[\u4e00-\u9fff]', core_text))
        # 英文字符计数
        en_count = len(re.findall(r'[a-zA-Z]', core_text))
        
        # 判断是否过短
        is_too_short = False
        
        # 规则1：核心文字为空或只有1-2个字符
        if core_len <= 2:
            is_too_short = True
        
        # 规则2：纯中文且只有1-2个字（如"視頻"）
        if cn_count > 0 and en_count == 0 and cn_count <= 2:
            is_too_short = True
        
        # 规则3：纯英文/数字混合且长度很短（如 vide2o、Pavid2eo）
        if cn_count == 0 and core_len <= 6:
            # 额外检查：是否包含无意义模式
            # 如：video + 数字、vid + 数字等
            if re.match(r'^(vid|video|mov|mp4|img|pic)\d*$', core_text, re.IGNORECASE):
                is_too_short = True
            # 或者核心文字太短（<=4个字符）
            if core_len <= 4:
                is_too_short = True
        
        if is_too_short:
            return True

    return False

def clean_text(text: str) -> str:
    return re.sub(r'[^a-zA-Z\u4e00-\u9fff\s]', '', text)

def preprocess_title(name: str) -> str:
    s = name
    # 去除时间戳：2024-01-15 / 20240115 / 2024.01.15 / 2024_01_15 / 25-05-08 / 250508
    s = re.sub(r'\b\d{4}[-._]?\d{2}[-._]?\d{2}\b', '', s)
    s = re.sub(r'\b\d{2}[-._]\d{2}[-._]\d{2}\b', '', s)
    # 去除 @ 提及（@username，包括前面的分隔符）
    s = re.sub(r'[-_.\s]*@[A-Za-z0-9_]+', '', s)
    # 去除 UUID 类 hash（如 6330BC93-0DF7-49D8-826E-815626B4C309）
    s = re.sub(r'\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b', '', s)
    # 去除连续 6+ 位无意义 hash（纯字母或纯字母数字混合）
    s = re.sub(r'\b[A-Za-z0-9]{6,}\b', '', s)
    # 去除黑名单词（大小写不敏感）
    for word in BLACKLIST_WORDS:
        s = re.sub(re.escape(word), '', s, flags=re.IGNORECASE)
    # 去除 video-output-xxx 类前缀
    s = re.sub(r'video[-_]?output[-_]?', '', s, flags=re.IGNORECASE)
    # 去除多余分隔符和空白
    s = re.sub(r'[-_.\s]+', ' ', s).strip()
    # 去除首尾无意义单字符
    s = re.sub(r'^[.\-_\s]+|[.\-_\s]+$', '', s)
    return s if s else name

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def process_title(original: str, stopwords: set) -> str:
    if not original.strip():
        return "未命名"
    try:
        cleaned = preprocess_title(original)
        keywords = jieba.analyse.extract_tags(cleaned, topK=TOP_KEYWORDS * 2)
        valid_kw = [clean_text(k) for k in keywords if k not in stopwords and len(k.strip()) > 1]
        valid_kw = [k for k in valid_kw if k and len(k) > 1]
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
    parser.add_argument("-o", "--output", type=str, default="output/title_review.csv", help="输出待审表路径")
    parser.add_argument("-a", "--append", action="store_true", help="启用追加模式")
    parser.add_argument("--exclude-dir", action="append", default=[], 
                        help="排除的目录名或路径（可多次使用，如 --exclude-dir love --exclude-dir 'F:\\test'）")
    parser.add_argument("--force-reclassify", action="store_true", 
                        help="强制重分类：处理所有文件，有中括号的提取原始标题，没有的也正常处理")
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
        print(f"[排除] 目录名={exclude_names}, 路径={exclude_paths}")
    
    jieba.initialize()
    
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
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
                print(f"  [跳过] 目录: {dir_path}")
        
        # 处理当前目录下的文件
        for file_name in files:
            file_path = root_path / file_name
            if file_path.suffix.lower() in MEDIA_EXTENSIONS:
                try:
                    original_name = file_path.stem
                    
                    # 强制重分类模式：处理所有文件
                    if args.force_reclassify:
                        # 如果有中括号，提取后面的原始标题（包括[未分类]）
                        match = re.match(r'^\[[^\]]*\]_', original_name)
                        if match:
                            raw_title = original_name[match.end():]
                            if raw_title:
                                original_name = raw_title
                                print(f"  [重分类] {file_path.stem[:40]} -> 原始标题: {raw_title[:40]}")
                        # 没有中括号的文件也正常处理（不跳过）
                    else:
                        # 正常模式：检查是否已分类
                        skip_processing = False
                        if is_already_classified(original_name):
                            # 检查中括号标签是否无意义
                            match = re.match(r'^\[([^\]]+)\]', original_name)
                            if match and is_meaningless_tag(match.group(1)):
                                # 无意义标签，需要重新处理
                                pass
                            else:
                                skip_processing = True
                        
                        if skip_processing:
                            continue
                    
                    proposed_name = process_title(original_name, stopwords)
                    needs_vision = is_needs_vision(original_name)
                    records.append({
                        "original_path": str(file_path.resolve()),
                        "original_title": original_name,  # 使用提取后的原始标题
                        "original_filename": file_path.stem,  # 保留原始文件名
                        "proposed_title": proposed_name,
                        "review_status": "待审核",
                        "final_name": proposed_name,
                        "needs_vision": "true" if needs_vision else "false"
                    })
                    scanned_count += 1
                    if scanned_count % 100 == 0:
                        print(f"  已处理: {scanned_count} 个文件...", end='\r')
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
            fieldnames = ["original_path", "original_title", "original_filename", "proposed_title", "review_status", "final_name", "needs_vision"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerows(records)
            
        print(f"\n[完成] 扫描完成。")
        print(f"[统计] 新增 {len(records)} 条记录")
        print(f"[输出] 结果已保存至: {output_path.resolve()}")
    except PermissionError:
        print(f"\n[错误] 无法写入文件 {output_path}，请检查是否被其他程序占用。")

if __name__ == "__main__":
    main()