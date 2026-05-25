"""音频处理工具"""

import base64
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts"}


def is_video_file(file_path: str) -> bool:
    """判断是否为视频文件"""
    return Path(file_path).suffix.lower() in VIDEO_EXTENSIONS


def extract_audio(
    video_path: str,
    output_path: str,
    start_time: float = None,
    end_time: float = None,
) -> bool:
    """从视频提取音频"""
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
        logger.error(f"提取音频失败: {e}")
        return False


def get_audio_base64(audio_path: str) -> str:
    """获取音频的base64编码"""
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        return base64.b64encode(audio_data).decode("utf-8")
    except Exception as e:
        logger.error(f"读取音频失败: {e}")
        return ""


def generate_srt_from_segments(segments: list, output_path: str) -> bool:
    """从分段生成SRT字幕文件"""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start = format_time(seg["start"])
                end = format_time(seg["end"])
                text = seg["text"]
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        return True
    except Exception as e:
        logger.error(f"生成SRT失败: {e}")
        return False


def format_time(seconds: float) -> str:
    """将秒数转换为SRT时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class AudioProcessor:
    """音频处理器"""

    def __init__(self, provider: str = "mimo"):
        self.provider = provider

    def process_video(self, video_path: str, output_srt: str = None, segment_duration: float = 30.0) -> Optional[str]:
        """处理视频，生成字幕"""
        from ..providers import call_audio_api

        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"视频文件不存在: {video_path}")
            return None

        # 获取视频时长
        duration = self._get_duration(str(video_path))
        if duration <= 0:
            logger.error("无法获取视频时长")
            return None

        # 分段处理
        segments = []
        current_time = 0.0

        while current_time < duration:
            end_time = min(current_time + segment_duration, duration)

            # 提取音频段
            audio_path = video_path.parent / f"{video_path.stem}_audio_{current_time:.0f}.wav"
            if not extract_audio(str(video_path), str(audio_path), current_time, end_time):
                current_time = end_time
                continue

            # 获取base64
            audio_b64 = get_audio_base64(str(audio_path))
            if not audio_b64:
                current_time = end_time
                continue

            # 调用API
            prompt = f"请转录这段音频的内容，时间范围：{current_time:.1f}s - {end_time:.1f}s"
            result = call_audio_api(audio_b64, prompt=prompt, model="mimo-v2.5")

            if result and not result.startswith("[ERROR]"):
                segments.append({
                    "start": current_time,
                    "end": end_time,
                    "text": result,
                })

            # 清理临时文件
            try:
                audio_path.unlink()
            except:
                pass

            current_time = end_time

        # 生成SRT
        if segments:
            if output_srt is None:
                output_srt = str(video_path.parent / f"{video_path.stem}.srt")
            if generate_srt_from_segments(segments, output_srt):
                return output_srt

        return None

    def _get_duration(self, video_path: str) -> float:
        """获取视频时长"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"获取视频时长失败: {e}")
        return 0.0
