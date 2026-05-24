# stage2_apply_rename.py
import csv
import argparse
from pathlib import Path
from datetime import datetime

# ================= 配置区 =================
DEFAULT_CSV = "output/title_review.csv"
LOG_FILE = "logs/rename_log.txt"
# ==========================================

def log_message(message: str, log_path: Path):
    """写入日志文件并打印到控制台"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(log_line + '\n')

def main():
    parser = argparse.ArgumentParser(description="阶段二：根据已核对的待审表执行安全重命名")
    parser.add_argument("-c", "--csv", type=str, default=DEFAULT_CSV, 
                        help=f"已核对的待审表路径（默认: {DEFAULT_CSV}）")
    parser.add_argument("--dry-run", action="store_true", 
                        help="模拟运行：只打印将要执行的操作，不实际重命名")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    log_path = Path(LOG_FILE)
    
    if not csv_path.exists():
        print(f"错误: 未找到审核文件 {csv_path}")
        print("请先运行 stage1_extract_propose.py 生成待审表。")
        return

    print(f"读取审核文件: {csv_path}")
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        tasks = list(reader)

    if not tasks:
        print("[警告] 待审表为空，无需执行。")
        return

    # 统计计数器
    stats = {"confirmed": 0, "success": 0, "skip": 0, "conflict": 0, "error": 0}
    
    for task in tasks:
        status = task.get("review_status", "").strip()
        
        # 仅处理标记为"已确认"的记录
        if status != "已确认":
            stats["skip"] += 1
            continue
            
        stats["confirmed"] += 1
        
        # 解析路径（强制绝对路径）
        original_path = Path(task["original_path"]).resolve()
        final_name = task.get("final_name", "").strip() or task["original_title"]
        
        # 校验源文件是否存在
        if not original_path.exists():
            log_message(f"[警告] 源文件已移动或删除: {original_path}", log_path)
            stats["error"] += 1
            continue
        
        # 构建新路径（保持在原目录）
        ext = original_path.suffix
        new_path = original_path.parent / (final_name + ext)
        
        # 跳过无需变更的文件
        if new_path == original_path:
            log_message(f"[跳过] 名称未变更: {original_path.name}", log_path)
            stats["skip"] += 1
            continue
        
        # 冲突检测与自动避让
        if new_path.exists():
            counter = 1
            original_new_path = new_path
            while new_path.exists():
                new_path = original_path.parent / f"{final_name}_{counter}{ext}"
                counter += 1
            log_message(f"[冲突解决] {original_path.name} -> {new_path.name}", log_path)
            stats["conflict"] += 1
        
        # 执行重命名（或模拟）
        if args.dry_run:
            log_message(f"[模拟] {original_path.name} -> {new_path.name}", log_path)
        else:
            try:
                original_path.rename(new_path)
                log_message(f"[成功] {original_path.name} -> {new_path.name}", log_path)
                stats["success"] += 1
            except PermissionError:
                log_message(f"[失败] 权限不足或文件被占用: {original_path.name}", log_path)
                stats["error"] += 1
            except OSError as e:
                log_message(f"[失败] {original_path.name}: {e}", log_path)
                stats["error"] += 1
            except Exception as e:
                log_message(f"[失败] {original_path.name}: {type(e).__name__}: {e}", log_path)
                stats["error"] += 1

    # 输出执行摘要
    print(f"\n{'='*60}")
    print(f"执行摘要")
    print(f"{'='*60}")
    print(f"待审记录总数: {len(tasks)}")
    print(f"标记为'已确认': {stats['confirmed']}")
    print(f"[成功] 重命名成功: {stats['success']}")
    print(f"[跳过] 名称未变更: {stats['skip']}")
    print(f"[冲突] 冲突已避让: {stats['conflict']}")
    print(f"[失败] 执行失败: {stats['error']}")
    print(f"{'='*60}")
    print(f"详细日志: {log_path.resolve()}")
    
    if args.dry_run:
        print(f"\n[提示] 当前为模拟模式，未执行实际重命名。")
        print(f"   确认无误后，移除 --dry-run 参数再次运行。")

if __name__ == "__main__":
    main()