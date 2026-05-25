"""
音频字幕生成工具
从视频中提取音频，使用MiMo模型理解内容，生成SRT字幕文件
"""
import os
import sys
import json
import time
import base64
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# 导入Provider模块
from providers import call_audio_api, get_api_key

LOG_FILE = "logs/audio_subtitle_log.txt"

# 支持的视频格式
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.m4v', '.ts'}


def load_env(env_path: Path):
    """加载.env文件"""
    if not env_path.exists():
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())


def log_message(message: str):
    """写入日志并打印"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    sys.stdout.buffer.write((log_line + '\n').encode('utf-8', errors='replace'))
    sys.stdout.buffer.flush()
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_line + '\n')


def is_video_file(file_path: str) -> bool:
    """判断是否为视频文件"""
    return Path(file_path).suffix.lower() in VIDEO_EXTENSIONS


def get_video_duration(video_path: str) -> float:
    """获取视频时长（秒）"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        log_message(f"[错误] 获取视频时长失败: {e}")
    return 0.0


def extract_audio(video_path: str, output_path: str, start_time: float = None, 
                  end_time: float = None) -> bool:
    """
    从视频提取音频
    
    Args:
        video_path: 视频路径
        output_path: 输出音频路径
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
    
    Returns:
        是否成功
    """
    try:
        cmd = ["ffmpeg", "-y", "-i", video_path]
        
        if start_time is not None:
            cmd.extend(["-ss", str(start_time)])
        if end_time is not None:
            cmd.extend(["-to", str(end_time)])
        
        cmd.extend(["-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0 and Path(output_path).exists()
    except Exception as e:
        log_message(f"[错误] 提取音频失败: {e}")
        return False


def get_audio_base64(audio_path: str) -> str:
    """将音频文件转为Base64编码（带data:audio/wav;base64,前缀）"""
    with open(audio_path, 'rb') as f:
        audio_data = f.read()
    b64_str = base64.b64encode(audio_data).decode('utf-8')
    return f"data:audio/wav;base64,{b64_str}"


def format_timestamp(seconds: float) -> str:
    """将秒数转为SRT时间戳格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(segments: list, output_path: str):
    """
    生成SRT字幕文件
    
    Args:
        segments: 字幕段列表 [{"index": 1, "start": 0, "end": 30, "text": "..."}]
        output_path: 输出文件路径
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            f.write(f"{seg['index']}\n")
            f.write(f"{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")


def process_video(video_path: str, args) -> bool:
    """
    处理单个视频，生成字幕
    
    Args:
        video_path: 视频路径
        args: 命令行参数
    
    Returns:
        是否成功
    """
    video_path = Path(video_path)
    if not video_path.exists():
        log_message(f"[错误] 视频文件不存在: {video_path}")
        return False
    
    if not is_video_file(str(video_path)):
        log_message(f"[错误] 不支持的视频格式: {video_path.suffix}")
        return False
    
    log_message(f"[处理] {video_path.name}")
    
    # 获取视频时长
    duration = get_video_duration(str(video_path))
    if duration <= 0:
        log_message(f"[错误] 无法获取视频时长: {video_path.name}")
        return False
    
    log_message(f"  时长: {duration:.1f}秒 ({duration/60:.1f}分钟)")
    
    # 创建临时目录
    tmp_dir = Path("logs/_audio_tmp")
    tmp_dir.mkdir(exist_ok=True)
    
    # 输出字幕路径
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    srt_path = output_dir / f"{video_path.stem}.srt"
    
    # 检查是否已存在
    if srt_path.exists() and not args.force:
        log_message(f"  [跳过] 字幕文件已存在: {srt_path.name}")
        return True
    
    # 模拟运行
    if args.dry_run:
        segments_count = int(duration // args.segment_duration) + 1
        log_message(f"  [模拟] 将生成 {segments_count} 段字幕 -> {srt_path.name}")
        return True
    
    # 分段处理
    segments = []
    segment_start = 0
    segment_index = 1
    
    while segment_start < duration:
        segment_end = min(segment_start + args.segment_duration, duration)
        
        log_message(f"  [分段 {segment_index}] {format_timestamp(segment_start)} -> {format_timestamp(segment_end)}")
        
        # 提取该段音频
        segment_audio = str(tmp_dir / f"segment_{segment_index}.wav")
        if not extract_audio(str(video_path), segment_audio, segment_start, segment_end):
            log_message(f"  [错误] 提取音频段失败")
            segment_start = segment_end
            segment_index += 1
            continue
        
        # 转Base64
        audio_b64 = get_audio_base64(segment_audio)
        
        # 调用API
        description = call_audio_api(
            audio_b64=audio_b64,
            prompt=args.prompt,
            model=args.model,
            timeout=args.timeout
        )
        
        # 清理临时文件
        try:
            os.remove(segment_audio)
        except:
            pass
        
        # 添加到字幕段
        segments.append({
            "index": segment_index,
            "start": segment_start,
            "end": segment_end,
            "text": description
        })
        
        log_message(f"  [结果] {description[:50]}...")
        
        segment_start = segment_end
        segment_index += 1
        
        # 批次间隔
        if segment_start < duration:
            time.sleep(args.delay)
    
    # 生成SRT文件
    if segments:
        generate_srt(segments, str(srt_path))
        log_message(f"  [完成] 字幕已保存: {srt_path.name} ({len(segments)}段)")
        return True
    else:
        log_message(f"  [警告] 无有效字幕段")
        return False


def process_folder(folder_path: str, args):
    """
    批量处理文件夹中的视频
    
    Args:
        folder_path: 文件夹路径
        args: 命令行参数
    """
    folder_path = Path(folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        log_message(f"[错误] 目录不存在: {folder_path}")
        return
    
    # 查找所有视频文件
    video_files = []
    for ext in VIDEO_EXTENSIONS:
        video_files.extend(folder_path.glob(f"*{ext}"))
    
    if not video_files:
        log_message(f"[警告] 目录中未找到视频文件: {folder_path}")
        return
    
    log_message(f"[批量处理] 找到 {len(video_files)} 个视频文件")
    
    success_count = 0
    fail_count = 0
    
    for i, video_file in enumerate(sorted(video_files), 1):
        log_message(f"\n[{i}/{len(video_files)}] 处理: {video_file.name}")
        if process_video(str(video_file), args):
            success_count += 1
        else:
            fail_count += 1
    
    log_message(f"\n[汇总] 成功: {success_count}, 失败: {fail_count}, 总计: {len(video_files)}")


def main():
    # 加载环境变量
    load_env(Path(__file__).parent / ".env")
    
    parser = argparse.ArgumentParser(
        description="音频字幕生成工具 - 从视频提取音频并使用AI生成字幕"
    )
    
    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-v", "--video", help="单个视频文件路径")
    input_group.add_argument("-d", "--dir", help="批量处理目录路径")
    
    # 输出参数
    parser.add_argument("-o", "--output", default="subtitles", help="输出目录（默认: subtitles）")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的字幕文件")
    
    # 音频处理参数
    parser.add_argument("--segment-duration", type=int, default=30, help="分段时长（秒，默认: 30）")
    
    # 模型参数
    parser.add_argument("--model", default="mimo-v2.5", help="模型名称（默认: mimo-v2.5）")
    parser.add_argument("--prompt", default=None, help="自定义提示词")
    parser.add_argument("--timeout", type=int, default=120, help="API超时时间（秒）")
    parser.add_argument("--delay", type=float, default=1.0, help="分段间隔（秒）")
    
    # 其他参数
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际调用API")
    
    args = parser.parse_args()
    
    # 检查API Key
    if not get_api_key("mimo"):
        print("错误: 缺少 MIMO_API_KEY，请在.env文件中设置")
        return
    
    print("=" * 60)
    print("音频字幕生成工具")
    print("=" * 60)
    print(f"模型: {args.model}")
    print(f"分段时长: {args.segment_duration}秒")
    print(f"输出目录: {args.output}")
    if args.dry_run:
        print("[模拟模式] 不会实际调用API")
    print("=" * 60)
    
    start_time = time.time()
    
    if args.video:
        # 处理单个视频
        process_video(args.video, args)
    elif args.dir:
        # 批量处理目录
        process_folder(args.dir, args)
    
    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f}秒")


if __name__ == "__main__":
    main()
