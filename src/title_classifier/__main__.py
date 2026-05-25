"""CLI入口点"""

import argparse
import logging
import sys
from pathlib import Path

from .core import Scanner, Refiner, VisionProcessor, Renamer


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_scan(args):
    """扫描命令"""
    scanner = Scanner(output_dir=args.output_dir)
    output = scanner.scan(
        target_dir=args.dir,
        output_file=args.output,
        append=args.append,
        exclude_dirs=args.exclude_dir,
        force_reclassify=args.force,
    )
    if output:
        print(f"[完成] 结果已保存至: {output}")


def cmd_refine(args):
    """优化命令"""
    refiner = Refiner(provider=args.provider)
    # TODO: 实现CSV读取和批量优化
    print("[待实现] AI标题优化")


def cmd_vision(args):
    """视觉识别命令"""
    processor = VisionProcessor(
        provider=args.provider,
        use_yolo=args.use_yolo,
        yolo_model=args.yolo_model,
        yolo_conf=args.yolo_conf,
        use_clip=args.use_clip,
        clip_threshold=args.clip_threshold,
        max_image_size=args.max_image_size,
        vlm_frames=args.vlm_frames,
        analysis_step=args.analysis_step,
    )

    if not processor.initialize():
        print("[错误] 初始化失败")
        return

    # TODO: 实现CSV读取和批量处理
    print("[待实现] 视觉识别")


def cmd_rename(args):
    """重命名命令"""
    renamer = Renamer(csv_path=args.csv)
    stats = renamer.rename(dry_run=args.dry_run)

    if "error" in stats:
        print(f"[错误] {stats['error']}")
        return

    print(f"\n[统计]")
    print(f"  已确认: {stats['confirmed']}")
    print(f"  成功: {stats['success']}")
    print(f"  跳过: {stats['skip']}")
    print(f"  冲突: {stats['conflict']}")
    print(f"  错误: {stats['error']}")


def cmd_gui(args):
    """GUI命令"""
    try:
        from .gui.app import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"[错误] GUI模块加载失败: {e}")
        print("请确保已安装 tkinter")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        prog="title-classifier",
        description="视频标题分类和重命名工具",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # scan 命令
    scan_cmd = subparsers.add_parser("scan", help="扫描目录")
    scan_cmd.add_argument("-d", "--dir", required=True, help="目标目录")
    scan_cmd.add_argument("-o", "--output", help="输出文件路径")
    scan_cmd.add_argument("--output-dir", default="data/output", help="输出目录")
    scan_cmd.add_argument("-a", "--append", action="store_true", help="追加模式")
    scan_cmd.add_argument("--exclude-dir", nargs="*", default=[], help="排除的目录")
    scan_cmd.add_argument("--force", action="store_true", help="强制重新分类")
    scan_cmd.set_defaults(func=cmd_scan)

    # refine 命令
    refine_cmd = subparsers.add_parser("refine", help="AI优化标题")
    refine_cmd.add_argument("-c", "--csv", default="data/output/title_review.csv", help="CSV文件路径")
    refine_cmd.add_argument("-p", "--provider", default="gcli", help="AI Provider")
    refine_cmd.set_defaults(func=cmd_refine)

    # vision 命令
    vision_cmd = subparsers.add_parser("vision", help="视觉识别")
    vision_cmd.add_argument("-c", "--csv", default="data/output/title_review.csv", help="CSV文件路径")
    vision_cmd.add_argument("-p", "--provider", default="gcli", help="AI Provider")
    vision_cmd.add_argument("--use-yolo", action="store_true", help="使用YOLO检测")
    vision_cmd.add_argument("--yolo-model", default="detect", choices=["detect", "pose", "segment"], help="YOLO模型类型")
    vision_cmd.add_argument("--yolo-conf", type=float, default=0.5, help="YOLO置信度阈值")
    vision_cmd.add_argument("--use-clip", action="store_true", help="使用CLIP预分类")
    vision_cmd.add_argument("--clip-threshold", type=float, default=0.25, help="CLIP置信度阈值")
    vision_cmd.add_argument("--max-image-size", type=int, default=800, help="图片最大尺寸")
    vision_cmd.add_argument("--vlm-frames", type=int, default=10, help="VLM帧数（全面分析模式默认10帧）")
    vision_cmd.add_argument("--analysis-step", type=float, default=2.0, help="视频分析采样间隔（秒，默认2秒）")
    vision_cmd.set_defaults(func=cmd_vision)

    # rename 命令
    rename_cmd = subparsers.add_parser("rename", help="执行重命名")
    rename_cmd.add_argument("-c", "--csv", default="data/output/title_review.csv", help="CSV文件路径")
    rename_cmd.add_argument("--dry-run", action="store_true", help="模拟运行")
    rename_cmd.set_defaults(func=cmd_rename)

    # gui 命令
    gui_cmd = subparsers.add_parser("gui", help="启动图形界面")
    gui_cmd.set_defaults(func=cmd_gui)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
