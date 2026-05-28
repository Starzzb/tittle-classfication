"""检测器模块"""

from .base import BaseDetector
from .yolo import YOLODetector
from .clip import CLIPClassifier

__all__ = ["BaseDetector", "YOLODetector", "CLIPClassifier"]
