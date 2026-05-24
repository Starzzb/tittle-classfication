"""
人体检测预处理模块
使用 UHD (Ultra-lightweight Human Detection) 模型从视频中找到包含人体的帧
"""

import subprocess
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime

# 模型配置
MODEL_DIR = Path(__file__).parent / "models" / "human_detection"
DEFAULT_MODEL = "ultratinyod_res_anc8_w128_64x64_loese_distill.onnx"

# 全局 session 缓存
_session_cache: Dict[str, ort.InferenceSession] = {}


def log_message(message: str):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)


def load_model(model_path: str = None) -> ort.InferenceSession:
    """
    加载 ONNX 模型（带缓存）
    
    Args:
        model_path: 模型路径，如果为 None 则使用默认路径
    
    Returns:
        ONNX Runtime 会话
    """
    if model_path is None:
        model_path = str(MODEL_DIR / DEFAULT_MODEL)
    
    if model_path in _session_cache:
        return _session_cache[model_path]
    
    log_message(f"[人体检测] 加载模型: {model_path}")
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    _session_cache[model_path] = session
    log_message(f"[人体检测] 模型加载完成")
    
    return session


def preprocess_frame(frame_bgr: np.ndarray) -> np.ndarray:
    """
    预处理帧图像为模型输入格式
    1. BGR -> RGB
    2. Resize 到 64x64 (INTER_NEAREST)
    3. 归一化到 [0, 1]
    4. 转换为 CHW 格式
    
    Args:
        frame_bgr: BGR 格式的帧图像
    
    Returns:
        预处理后的张量 [1, 3, 64, 64]
    """
    img_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(img_rgb, (64, 64), interpolation=cv2.INTER_NEAREST)
    arr = resized.astype(np.float32) / 255.0
    chw = np.transpose(arr, (2, 0, 1))
    return chw[np.newaxis, ...]


def sigmoid_np(x: np.ndarray) -> np.ndarray:
    """数值稳定的 sigmoid"""
    x_clip = np.clip(x, -80.0, 80.0)
    return 1.0 / (1.0 + np.exp(-x_clip))


def softplus_np(x: np.ndarray) -> np.ndarray:
    """数值稳定的 softplus"""
    return np.log1p(np.exp(-np.abs(x))) + np.maximum(x, 0.0)


def decode_detections(raw_out: np.ndarray, anchors: np.ndarray, 
                      conf_thresh: float = 0.5) -> List[Dict]:
    """
    解码模型原始输出为检测结果
    
    Args:
        raw_out: 模型原始输出 [1, C, H, W]
        anchors: anchor 尺寸 [N, 2]
        conf_thresh: 置信度阈值
    
    Returns:
        检测结果列表 [{"score": float, "bbox": [cx, cy, w, h]}, ...]
    """
    if raw_out.ndim == 3:
        raw_out = raw_out[None, ...]
    
    b, c, h, w = raw_out.shape
    na = anchors.shape[0]
    per_anchor = c // na
    
    # 重塑为 [B, A, H, W, per_anchor]
    pred = raw_out.reshape(b, na, per_anchor, h, w).transpose(0, 1, 3, 4, 2)
    
    # 提取各分量
    tx = pred[..., 0]
    ty = pred[..., 1]
    tw = pred[..., 2]
    th = pred[..., 3]
    obj = pred[..., 4]
    
    # 计算置信度
    obj_sig = sigmoid_np(obj)
    
    # 生成网格坐标
    gy, gx = np.meshgrid(np.arange(h, dtype=np.float32), 
                         np.arange(w, dtype=np.float32), indexing="ij")
    gx = gx.reshape(1, 1, h, w)
    gy = gy.reshape(1, 1, h, w)
    
    # 计算边界框中心
    pw = anchors[:, 0].reshape(1, na, 1, 1)
    ph = anchors[:, 1].reshape(1, na, 1, 1)
    
    cx = (sigmoid_np(tx) + gx) / float(w)
    cy = (sigmoid_np(ty) + gy) / float(h)
    bw = pw * softplus_np(tw)
    bh = ph * softplus_np(th)
    
    # 筛选高置信度检测
    detections = []
    for i in range(b):
        mask = obj_sig[i] >= conf_thresh
        if not np.any(mask):
            continue
        
        scores = obj_sig[i][mask]
        cx_flat = cx[i][mask]
        cy_flat = cy[i][mask]
        bw_flat = bw[i][mask]
        bh_flat = bh[i][mask]
        
        for j in range(len(scores)):
            detections.append({
                "score": float(scores[j]),
                "bbox": [float(cx_flat[j]), float(cy_flat[j]), 
                        float(bw_flat[j]), float(bh_flat[j])]
            })
    
    return detections


def non_max_suppression(detections: List[Dict], iou_thresh: float = 0.5) -> List[Dict]:
    """
    非极大值抑制
    
    Args:
        detections: 检测结果列表
        iou_thresh: IoU 阈值
    
    Returns:
        NMS 后的检测结果
    """
    if not detections:
        return []
    
    # 按置信度降序排序
    detections = sorted(detections, key=lambda x: x["score"], reverse=True)
    
    keep = []
    while detections:
        best = detections.pop(0)
        keep.append(best)
        
        remaining = []
        for det in detections:
            # 计算 IoU
            cx1, cy1, w1, h1 = best["bbox"]
            cx2, cy2, w2, h2 = det["bbox"]
            
            x1_min, y1_min = cx1 - w1/2, cy1 - h1/2
            x1_max, y1_max = cx1 + w1/2, cy1 + h1/2
            x2_min, y2_min = cx2 - w2/2, cy2 - h2/2
            x2_max, y2_max = cx2 + w2/2, cy2 + h2/2
            
            inter_x_min = max(x1_min, x2_min)
            inter_y_min = max(y1_min, y2_min)
            inter_x_max = min(x1_max, x2_max)
            inter_y_max = min(y1_max, y2_max)
            
            inter_area = max(0, inter_x_max - inter_x_min) * max(0, inter_y_max - inter_y_min)
            area1 = w1 * h1
            area2 = w2 * h2
            union_area = area1 + area2 - inter_area
            
            iou = inter_area / union_area if union_area > 0 else 0
            
            if iou < iou_thresh:
                remaining.append(det)
        
        detections = remaining
    
    return keep


def decode_decoded_output(detections: np.ndarray, conf_thresh: float = 0.5) -> List[Dict]:
    """
    解码已解码的检测结果 [1, N, 6] -> 检测列表
    每行: [score, class_id, cx, cy, w, h]
    
    Args:
        detections: 模型输出 [1, N, 6]
        conf_thresh: 置信度阈值
    
    Returns:
        检测结果列表
    """
    results = []
    for det in detections[0]:
        score, cls_id, cx, cy, w, h = det[:6]
        if score >= conf_thresh:
            results.append({
                "score": float(score),
                "bbox": [float(cx), float(cy), float(w), float(h)]
            })
    return results


def detect_human(frame_path: str, session: ort.InferenceSession, 
                 conf_threshold: float = 0.5) -> Dict:
    """
    检测帧中是否有人
    
    Args:
        frame_path: 帧图像路径
        session: ONNX Runtime 会话
        conf_threshold: 置信度阈值
    
    Returns:
        {
            "has_human": bool,
            "max_confidence": float,
            "detections": list
        }
    """
    # 读取图像（使用 numpy 支持中文路径）
    data = np.fromfile(frame_path, dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        log_message(f"[人体检测] 无法读取图像: {frame_path}")
        return {"has_human": False, "max_confidence": 0.0, "detections": []}
    
    # 预处理
    input_tensor = preprocess_frame(frame)
    
    # 运行推理
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: input_tensor})
    
    # 解析输出（模型已内置后处理，输出 [1, N, 6]）
    raw_output = outputs[0]
    
    if raw_output.ndim == 3 and raw_output.shape[2] == 6:
        # 已解码输出 [1, N, 6]
        detections = decode_decoded_output(raw_output, conf_threshold)
    else:
        # 原始输出（需要后处理）- 备用逻辑
        log_message(f"[人体检测] 警告: 未预期的输出形状 {raw_output.shape}")
        detections = []
    
    # NMS
    detections = non_max_suppression(detections, iou_thresh=0.5)
    
    # 计算最大置信度
    max_conf = max([d["score"] for d in detections]) if detections else 0.0
    
    return {
        "has_human": len(detections) > 0,
        "max_confidence": max_conf,
        "detections": detections
    }


def crop_human_region(frame_path: str, bbox: list, padding: float = 0.15) -> Optional[np.ndarray]:
    """
    裁剪人体区域
    
    Args:
        frame_path: 帧图像路径
        bbox: 边界框 [cx, cy, w, h] (归一化坐标 0-1)
        padding: 边界框扩展比例（避免裁剪过紧，默认0.15）
    
    Returns:
        裁剪后的人体区域图像（BGR numpy数组），失败返回None
    """
    try:
        # 读取图像
        data = np.fromfile(frame_path, dtype=np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        
        h, w = frame.shape[:2]
        cx, cy, bw, bh = bbox
        
        # 转换为像素坐标并扩展
        x1 = int((cx - bw/2 - padding * bw) * w)
        y1 = int((cy - bh/2 - padding * bh) * h)
        x2 = int((cx + bw/2 + padding * bw) * w)
        y2 = int((cy + bh/2 + padding * bh) * h)
        
        # 边界检查
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        # 检查裁剪区域是否有效
        if x2 <= x1 or y2 <= y1:
            return None
        
        crop = frame[y1:y2, x1:x2]
        
        # 检查裁剪区域大小（太小则无效）
        if crop.shape[0] < 10 or crop.shape[1] < 10:
            return None
        
        return crop
    except Exception as e:
        log_message(f"[人体裁剪] 失败: {e}")
        return None


def detect_and_crop_human(frame_path: str, session: ort.InferenceSession,
                         conf_threshold: float = 0.5, padding: float = 0.15) -> Dict:
    """
    检测人体并裁剪区域（便捷函数）
    
    Args:
        frame_path: 帧图像路径
        session: ONNX Runtime 会话
        conf_threshold: 置信度阈值
        padding: 边界框扩展比例
    
    Returns:
        {
            "has_human": bool,
            "max_confidence": float,
            "human_crop": np.ndarray or None,
            "bbox": list or None
        }
    """
    result = detect_human(frame_path, session, conf_threshold)
    
    human_crop = None
    bbox = None
    
    if result["has_human"] and result["detections"]:
        # 取最高置信度的检测结果
        best_det = max(result["detections"], key=lambda x: x["score"])
        bbox = best_det["bbox"]
        
        # 裁剪人体区域
        human_crop = crop_human_region(frame_path, bbox, padding)
    
    return {
        "has_human": result["has_human"],
        "max_confidence": result["max_confidence"],
        "human_crop": human_crop,
        "bbox": bbox
    }


def get_video_duration(video_path: str) -> float:
    """
    获取视频时长（秒）
    
    Args:
        video_path: 视频路径
    
    Returns:
        视频时长（秒），失败返回 0.0
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        log_message(f"[视频信息] 获取时长失败: {e}")
    return 0.0


def safe_timestamp(timestamp_seconds: float, duration: float, margin: float = 2.0) -> float:
    """
    安全的时间戳：确保不超过视频时长
    
    Args:
        timestamp_seconds: 目标时间点（秒）
        duration: 视频时长（秒）
        margin: 距离末尾的安全距离（秒）
    
    Returns:
        安全的时间点
    """
    if duration <= 0:
        return timestamp_seconds
    
    # 如果视频比目标时间短，使用视频四分之一位置
    max_safe = max(0, duration - margin)
    if max_safe <= 0:
        return 0.0
    
    return min(timestamp_seconds, max_safe)


def get_adaptive_step(duration: float, max_retries: int = 3, min_step: float = 2.0, max_step: float = 10.0) -> float:
    """
    根据视频时长自适应调整步长
    
    Args:
        duration: 视频时长（秒）
        max_retries: 最大重试次数
        min_step: 最小步长
        max_step: 最大步长
    
    Returns:
        自适应步长
    """
    if duration <= 0:
        return min_step
    
    # 目标：在 max_retries 次内覆盖视频前 1/3
    target_coverage = duration / 3
    step = target_coverage / max_retries
    
    # 限制在合理范围内
    return max(min_step, min(max_step, step))


def extract_frame_at_timestamp(video_path: str, output_path: str, 
                               timestamp_seconds: float, duration: float = 0.0) -> bool:
    """
    在指定时间点提取帧
    
    Args:
        video_path: 视频路径
        output_path: 输出帧路径
        timestamp_seconds: 时间点（秒）
        duration: 视频时长（秒），0表示自动获取
    
    Returns:
        是否成功
    """
    # 获取视频时长（如果未提供）
    if duration <= 0:
        duration = get_video_duration(video_path)
    
    # 安全处理时间戳
    safe_ts = safe_timestamp(timestamp_seconds, duration)
    if safe_ts != timestamp_seconds:
        log_message(f"[帧提取] 时间点调整: {timestamp_seconds:.1f}s -> {safe_ts:.1f}s (视频时长: {duration:.1f}s)")
    
    # 将秒数转换为 HH:MM:SS.mmm 格式
    hours = int(safe_ts // 3600)
    minutes = int((safe_ts % 3600) // 60)
    seconds = safe_ts % 60
    timestamp = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", timestamp, "-i", video_path,
             "-frames:v", "1", "-q:v", "2", output_path],
            capture_output=True, timeout=15
        )
        return result.returncode == 0 and Path(output_path).exists()
    except Exception as e:
        log_message(f"[人体检测] 帧提取失败: {e}")
        return False


def find_human_frame(video_path: str, session: ort.InferenceSession,
                     step_seconds: float = 5.0, max_retries: int = 3,
                     conf_threshold: float = 0.5,
                     tmp_dir: str = "logs/_frame_selector_tmp") -> Dict:
    """
    从视频中找到第一帧包含人体的画面
    
    Args:
        video_path: 视频路径
        session: ONNX Runtime 会话
        step_seconds: 每次跳过的秒数（默认5秒，会根据视频时长自适应调整）
        max_retries: 最大重试次数
        conf_threshold: 置信度阈值
        tmp_dir: 临时目录
    
    Returns:
        {
            "found": bool,
            "frame_path": str or None,
            "timestamp": float or None,
            "max_confidence": float,
            "detections": list,
            "attempts": int
        }
    """
    tmp_path = Path(tmp_dir)
    tmp_path.mkdir(parents=True, exist_ok=True)
    
    # 使用简单文件名避免特殊字符问题
    import hashlib
    video_hash = hashlib.md5(video_path.encode()).hexdigest()[:8]
    
    # 获取视频时长
    duration = get_video_duration(video_path)
    log_message(f"[人体检测] 视频时长: {duration:.1f}s")
    
    # 自适应步长
    adaptive_step = get_adaptive_step(duration, max_retries)
    log_message(f"[人体检测] 自适应步长: {adaptive_step:.1f}s (原始设置: {step_seconds:.1f}s)")
    
    for attempt in range(max_retries):
        timestamp = attempt * adaptive_step
        
        log_message(f"[人体检测] 尝试 {attempt + 1}/{max_retries}: 提取帧 @ {timestamp:.1f}s")
        
        # 提取帧（使用简单文件名避免特殊字符）
        frame_path = str(tmp_path / f"frame_{video_hash}_{attempt}.jpg")
        if not extract_frame_at_timestamp(video_path, frame_path, timestamp, duration):
            log_message(f"[人体检测] 帧提取失败 @ {timestamp:.1f}s")
            continue
        
        # 检测人体
        result = detect_human(frame_path, session, conf_threshold)
        
        log_message(f"[人体检测] 检测结果: has_human={result['has_human']}, "
                    f"max_confidence={result['max_confidence']:.2f}, "
                    f"detections={len(result['detections'])}")
        
        if result["has_human"]:
            # 记录检测到的部位信息
            for i, det in enumerate(result["detections"]):
                log_message(f"[人体检测]   检测 {i+1}: 置信度={det['score']:.2f}, "
                          f"位置=[{det['bbox'][0]:.2f}, {det['bbox'][1]:.2f}, "
                          f"{det['bbox'][2]:.2f}, {det['bbox'][3]:.2f}]")
            
            return {
                "found": True,
                "frame_path": frame_path,
                "timestamp": timestamp,
                "max_confidence": result["max_confidence"],
                "detections": result["detections"],
                "attempts": attempt + 1
            }
        
        # 清理临时文件
        try:
            Path(frame_path).unlink()
        except:
            pass
    
    log_message(f"[人体检测] 达到最大重试次数 ({max_retries})，未检测到人体")
    return {
        "found": False,
        "frame_path": None,
        "timestamp": None,
        "max_confidence": 0.0,
        "detections": [],
        "attempts": max_retries
    }


def get_detection_summary(detections: List[Dict]) -> str:
    """
    生成检测结果摘要
    
    Args:
        detections: 检测结果列表
    
    Returns:
        摘要字符串
    """
    if not detections:
        return "未检测到人体"
    
    count = len(detections)
    max_score = max(d["score"] for d in detections)
    
    return f"检测到 {count} 个人体，最高置信度 {max_score:.2f}"


if __name__ == "__main__":
    """测试代码"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python stage1c_frame_selector.py <视频路径> [模型路径]")
        sys.exit(1)
    
    video_path = sys.argv[1]
    model_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(video_path).exists():
        print(f"错误: 视频文件不存在: {video_path}")
        sys.exit(1)
    
    # 加载模型
    session = load_model(model_path)
    
    # 查找有人帧
    result = find_human_frame(video_path, session, 
                              step_seconds=2.0, 
                              max_retries=3, 
                              conf_threshold=0.5)
    
    print("\n" + "=" * 50)
    print("检测结果:")
    print("=" * 50)
    print(f"找到有人帧: {result['found']}")
    if result['found']:
        print(f"帧路径: {result['frame_path']}")
        print(f"时间点: {result['timestamp']:.1f}s")
        print(f"最大置信度: {result['max_confidence']:.2f}")
        print(f"检测数量: {len(result['detections'])}")
        print(f"尝试次数: {result['attempts']}")
        print(f"摘要: {get_detection_summary(result['detections'])}")
    else:
        print("未检测到人体")
