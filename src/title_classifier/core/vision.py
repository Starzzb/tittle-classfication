"""视觉识别模块"""

import csv
import json
import os
import re
import logging
from pathlib import Path
from typing import Union, List, Dict, Optional

import cv2
import numpy as np

from ..providers import get_provider_config, get_api_key, call_vision_api
from ..detectors import UHDDetector, YOLODetector, CLIPClassifier
from ..utils.video import get_video_duration, extract_frame, extract_multiple_frames, detect_keyframes
from ..utils.image import compress_image, image_to_base64
from ..utils.stats import TagStatistics

logger = logging.getLogger(__name__)


class VisionProcessor:
    """视觉处理器"""

    def __init__(
        self,
        provider: str = "gcli",
        use_yolo: bool = False,
        yolo_model: str = "detect",
        yolo_conf: float = 0.5,
        use_clip: bool = False,
        clip_threshold: float = 0.25,
        max_image_size: int = 800,
        vlm_frames: int = 5,
    ):
        self.provider = provider
        self.use_yolo = use_yolo
        self.yolo_model = yolo_model
        self.yolo_conf = yolo_conf
        self.use_clip = use_clip
        self.clip_threshold = clip_threshold
        self.max_image_size = max_image_size
        self.vlm_frames = vlm_frames

        self.provider_config = get_provider_config(provider)
        self.model = self.provider_config.get("default_model", "") if self.provider_config else ""
        self.api_key = get_api_key(provider)

        self.uhd_detector = None
        self.yolo_detector = None
        self.clip_classifier = None
        self.tag_stats = None

    def initialize(self) -> bool:
        """初始化检测器"""
        # 初始化标签统计
        self.tag_stats = TagStatistics()

        # 初始化检测器
        if self.use_yolo:
            self.yolo_detector = YOLODetector(
                model_type=self.yolo_model,
                confidence=self.yolo_conf,
            )
            if not self.yolo_detector.load_model():
                logger.error("YOLO模型加载失败")
                return False
        else:
            self.uhd_detector = UHDDetector()
            if not self.uhd_detector.load_model():
                logger.error("UHD模型加载失败")
                return False

        # 初始化CLIP
        if self.use_clip:
            self.clip_classifier = CLIPClassifier(tag_stats=self.tag_stats)
            if not self.clip_classifier.load_model():
                logger.warning("CLIP模型加载失败，将使用纯云端VLM")
                self.use_clip = False
                self.clip_classifier = None

        return True

    def process_video(self, video_path: str, title: str) -> Dict:
        """处理视频"""
        duration = get_video_duration(video_path)
        logger.info(f"视频模式: {title[:30]} (时长: {duration:.1f}s)")

        # 提取帧
        frames = self._extract_frames(video_path)
        if not frames:
            return {"error": "无法提取帧"}

        # YOLO姿态分析
        yolo_results = []
        if self.use_yolo and self.yolo_detector:
            yolo_results = self._analyze_poses(frames)

        # 智能帧选择
        selected_frames = self._select_frames(frames, yolo_results)

        # 构建YOLO上下文
        yolo_context = None
        if yolo_results:
            yolo_context = self._build_yolo_context(yolo_results, selected_frames)

        # 调用VLM
        result = self._call_vlm(selected_frames, title, yolo_context)

        return {
            "description": result.get("description", ""),
            "keywords": result.get("keywords", ""),
            "yolo_results": yolo_results,
            "selected_frames": selected_frames,
        }

    def process_image(self, image_path: str, title: str) -> Dict:
        """处理图片"""
        logger.info(f"图片模式: {title[:30]}")

        # 压缩图片
        compressed_path = str(Path(image_path).parent / f"{Path(image_path).stem}_compressed.jpg")
        if not compress_image(image_path, compressed_path, max_size=self.max_image_size):
            compressed_path = image_path

        # CLIP分类
        if self.use_clip and self.clip_classifier:
            clip_result = self.clip_classifier.classify(compressed_path, threshold=self.clip_threshold)
            if clip_result["avg_confidence"] >= self.clip_threshold:
                return {
                    "description": f"[CLIP] {clip_result['tags']}",
                    "keywords": clip_result["tags"],
                    "source": "clip_only",
                }

        # 调用VLM
        image_b64 = image_to_base64(compressed_path, max_size=self.max_image_size)
        result = call_vision_api(
            self.provider, image_b64, title,
            model=self.model, api_key=self.api_key,
        )

        # 清理临时文件
        if compressed_path != image_path and Path(compressed_path).exists():
            try:
                Path(compressed_path).unlink()
            except:
                pass

        return self._parse_vision_response(result)

    def _extract_frames(self, video_path: str) -> List[str]:
        """提取视频帧"""
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp())
        frames = []

        # 关键帧检测
        keyframes = detect_keyframes(video_path, str(tmp_dir), max_frames=8, max_size=self.max_image_size)
        frames.extend(keyframes)

        # 均匀采样补充
        if len(frames) < self.vlm_frames:
            extra = extract_multiple_frames(
                video_path, str(tmp_dir),
                n_frames=self.vlm_frames - len(frames),
                max_size=self.max_image_size,
            )
            for f in extra:
                if f not in frames:
                    frames.append(f)

        return frames

    def _analyze_poses(self, frames: List[str]) -> List[Dict]:
        """分析姿态"""
        results = []
        for frame_path in frames:
            data = np.fromfile(frame_path, dtype=np.uint8)
            frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if frame is not None:
                pose_result = self.yolo_detector.estimate_pose(frame)
                results.append(pose_result)
            else:
                results.append({"has_person": False})
        return results

    def _select_frames(self, frames: List[str], yolo_results: List[Dict]) -> List[str]:
        """智能帧选择"""
        if not yolo_results:
            return frames[:self.vlm_frames]

        # 计算每帧得分
        scored = []
        prev_pose = None

        for i, (frame, result) in enumerate(zip(frames, yolo_results)):
            score = 0.0

            if result.get("has_person"):
                # 置信度得分
                conf = result.get("max_confidence", 0)
                score += conf * 40

                # 关键点可见性得分
                visible = result.get("poses", [{}])[0].get("visible_count", 0)
                score += (visible / 17) * 30

                # 姿态多样性得分
                current_pose = tuple(result.get("poses", [{}])[0].get("pose_analysis", []))
                if prev_pose and current_pose != prev_pose:
                    score += 30
                prev_pose = current_pose

            scored.append((i, score))

        # 按得分排序
        scored.sort(key=lambda x: x[1], reverse=True)
        selected_indices = [i for i, _ in scored[:self.vlm_frames]]
        selected_indices.sort()

        return [frames[i] for i in selected_indices if i < len(frames)]

    def _build_yolo_context(self, yolo_results: List[Dict], selected_frames: List[str]) -> str:
        """构建YOLO上下文"""
        context_lines = []

        frames_with_person = [r for r in yolo_results if r.get("has_person")]
        if frames_with_person:
            # 统计姿态分布
            pose_counts = {}
            for r in frames_with_person:
                poses = r.get("poses", [{}])[0].get("pose_analysis", ["未知"])
                for pose in poses:
                    pose_counts[pose] = pose_counts.get(pose, 0) + 1

            main_pose = max(pose_counts, key=pose_counts.get) if pose_counts else "未知"
            context_lines.append(f"- 视频中检测到人体，主要姿态：{main_pose}")

            avg_visible = sum(r.get("poses", [{}])[0].get("visible_count", 0) for r in frames_with_person) / len(frames_with_person)
            avg_conf = sum(r.get("max_confidence", 0) for r in frames_with_person) / len(frames_with_person)
            context_lines.append(f"- 平均可见关键点：{avg_visible:.1f}/17，平均置信度：{avg_conf:.2f}")

        return "\n".join(context_lines) if context_lines else ""

    def _call_vlm(self, frames: List[str], title: str, yolo_context: str = None) -> Dict:
        """调用VLM"""
        prompt = self._build_vision_prompt(title, len(frames), yolo_context)

        if len(frames) > 1:
            images_b64 = [image_to_base64(f, max_size=self.max_image_size) for f in frames]
            result = call_vision_api(
                self.provider, images_b64, prompt,
                model=self.model, api_key=self.api_key,
            )
        else:
            image_b64 = image_to_base64(frames[0], max_size=self.max_image_size)
            result = call_vision_api(
                self.provider, image_b64, prompt,
                model=self.model, api_key=self.api_key,
            )

        return self._parse_vision_response(result)

    def _build_vision_prompt(self, title: str, n_frames: int, yolo_context: str = None) -> str:
        """构建VLM提示词"""
        yolo_section = ""
        if yolo_context:
            yolo_section = f"\n【视频预分析结果】\n{yolo_context}\n"

        if n_frames > 1:
            return (
                f'这是媒体文件 "{title}" 的{n_frames}个关键帧截图，用于文件管理归类。请进行纯技术性视觉分析：\n'
                f"{yolo_section}\n"
                f"1. 描述：综合所有帧，客观描述画面中的可见元素（场景、人物穿着、人物动作、水印等）\n"
                f"2. 关键词：提取 4-8 个关键词，用逗号分隔\n\n"
                f"【关键词提取规则】\n"
                f"- 第一优先级：可见文字/水印中的名称（个人昵称/艺名，非@开头的频道名）\n"
                f"- 第二优先级：人物穿着、人物行为，可见物体\n\n"
                f"注意：@开头的频道名/群组名不需要提取。水印中的广告内容不必提取\n\n"
                f"请始终返回结果，即使只能识别部分内容也请描述。严格按以下格式返回：\n"
                f"描述：xxx\n"
                f"关键词：xxx, xxx, xxx"
            )
        else:
            return (
                f'这是媒体文件 "{title}" 的截图，用于文件管理归类。请进行纯技术性视觉分析：\n'
                f"{yolo_section}\n"
                f"1. 描述：客观描述画面中的可见元素（场景、人物穿着、人物动作、水印等）\n"
                f"2. 关键词：提取 4-8 个关键词，用逗号分隔\n\n"
                f"【关键词提取规则】\n"
                f"- 第一优先级：可见文字/水印中的名称（个人昵称/艺名，非@开头的频道名）\n"
                f"- 第二优先级：人物穿着、人物行为，可见物体\n\n"
                f"注意：@开头的频道名/群组名不需要提取。水印中的广告内容不必提取\n\n"
                f"请始终返回结果，即使只能识别部分内容也请描述。严格按以下格式返回：\n"
                f"描述：xxx\n"
                f"关键词：xxx, xxx, xxx"
            )

    def _parse_vision_response(self, response: str) -> Dict:
        """解析VLM响应"""
        result = {"description": "", "keywords": ""}
        desc_match = re.search(r"描述[：:]\s*(.+)", response)
        kw_match = re.search(r"关键词[：:]\s*(.+)", response)
        if desc_match:
            result["description"] = desc_match.group(1).strip()
        if kw_match:
            result["keywords"] = kw_match.group(1).strip()
        return result
