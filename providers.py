"""
统一的 AI Provider 配置管理模块
支持自定义 Provider，自动检测可用性
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, List, Any

# 默认 Provider 注册表
DEFAULT_PROVIDERS = {
    "ollama": {
        "name": "Ollama（本地）",
        "type": "text",  # text / vision / multi
        "url": "http://localhost:11434/api/generate",
        "env_key": "",
        "default_model": "qwen2.5:7b-instruct-q4_K_M",
        "requires_api_key": False,
        "supports_1b": True,
        "supports_1c": False,
        "description": "本地运行，免费，需要安装 Ollama"
    },
    "zhipu": {
        "name": "智谱 API",
        "type": "multi",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "env_key": "ZHIPU_API_KEY",
        "default_model": "GLM-4.7-Flash",
        "requires_api_key": True,
        "supports_1b": True,
        "supports_1c": False,
        "description": "智谱GLM模型，中文理解好"
    },
    "gcli": {
        "name": "gcli API",
        "type": "multi",
        "url": "https://gcli.ggchan.dev/v1/chat/completions",
        "env_key": "GCLI_API_KEY",
        "default_model": "gemini-3-flash-preview",
        "requires_api_key": True,
        "supports_1b": True,
        "supports_1c": True,
        "description": "Google Gemini 模型，推荐使用"
    },
    "mimo": {
        "name": "小米 MiMo",
        "type": "vision",
        "url": "https://api.xiaomimimo.com/v1/chat/completions",
        "env_key": "MIMO_API_KEY",
        "default_model": "mimo-v2-omni",
        "requires_api_key": True,
        "supports_1b": False,
        "supports_1c": True,
        "description": "小米自研视觉模型"
    },
}

# 自定义 Provider 配置文件路径
CUSTOM_PROVIDERS_FILE = "providers.json"


def load_custom_providers() -> Dict[str, Any]:
    """加载自定义 Provider 配置"""
    config_path = Path(CUSTOM_PROVIDERS_FILE)
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[警告] 加载自定义 Provider 失败: {e}")
        return {}


def save_custom_providers(providers: Dict[str, Any]):
    """保存自定义 Provider 配置"""
    try:
        with open(CUSTOM_PROVIDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(providers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 保存自定义 Provider 失败: {e}")


def get_all_providers() -> Dict[str, Any]:
    """获取所有 Provider（默认 + 自定义）"""
    all_providers = dict(DEFAULT_PROVIDERS)
    custom = load_custom_providers()
    all_providers.update(custom)
    return all_providers


def get_provider_config(provider_name: str) -> Optional[Dict[str, Any]]:
    """获取指定 Provider 的配置"""
    all_providers = get_all_providers()
    return all_providers.get(provider_name)


def get_available_providers(stage: str = "1b") -> List[Dict[str, Any]]:
    """
    获取可用的 Provider 列表
    
    Args:
        stage: "1b" 或 "1c"
    
    Returns:
        可用 Provider 列表
    """
    all_providers = get_all_providers()
    available = []
    
    for name, config in all_providers.items():
        # 检查是否支持指定阶段
        if stage == "1b" and not config.get("supports_1b", False):
            continue
        if stage == "1c" and not config.get("supports_1c", False):
            continue
        
        # 检查 API Key 是否可用
        if config.get("requires_api_key", False):
            env_key = config.get("env_key", "")
            if env_key and not os.environ.get(env_key):
                continue
        
        available.append({
            "id": name,
            "name": config.get("name", name),
            "type": config.get("type", "multi"),
            "default_model": config.get("default_model", ""),
            "description": config.get("description", ""),
        })
    
    return available


def get_api_key(provider_name: str, custom_key: str = None) -> str:
    """
    获取 Provider 的 API Key
    
    Args:
        provider_name: Provider 名称
        custom_key: 自定义 API Key（优先使用）
    
    Returns:
        API Key 字符串
    """
    if custom_key:
        return custom_key
    
    config = get_provider_config(provider_name)
    if not config:
        return ""
    
    env_key = config.get("env_key", "")
    if env_key:
        return os.environ.get(env_key, "")
    
    return ""


def check_provider_availability(provider_name: str) -> Dict[str, Any]:
    """
    检查 Provider 可用性
    
    Returns:
        {
            "available": bool,
            "reason": str,  # 不可用原因
            "config": dict  # Provider 配置
        }
    """
    config = get_provider_config(provider_name)
    if not config:
        return {"available": False, "reason": f"Provider '{provider_name}' 不存在", "config": None}
    
    # 检查 API Key
    if config.get("requires_api_key", False):
        env_key = config.get("env_key", "")
        if env_key and not os.environ.get(env_key):
            return {
                "available": False,
                "reason": f"缺少环境变量 {env_key}",
                "config": config
            }
    
    return {"available": True, "reason": "", "config": config}


def add_custom_provider(name: str, config: Dict[str, Any]) -> bool:
    """
    添加自定义 Provider
    
    Args:
        name: Provider 名称（唯一标识）
        config: Provider 配置
    
    Returns:
        是否成功
    """
    # 验证必要字段
    required_fields = ["name", "url", "default_model"]
    for field in required_fields:
        if field not in config:
            print(f"[错误] 缺少必要字段: {field}")
            return False
    
    # 设置默认值
    config.setdefault("type", "multi")
    config.setdefault("env_key", "")
    config.setdefault("requires_api_key", bool(config.get("env_key")))
    config.setdefault("supports_1b", True)
    config.setdefault("supports_1c", True)
    config.setdefault("description", "")
    
    # 保存
    custom = load_custom_providers()
    custom[name] = config
    save_custom_providers(custom)
    
    return True


def remove_custom_provider(name: str) -> bool:
    """删除自定义 Provider"""
    if name in DEFAULT_PROVIDERS:
        print(f"[错误] 不能删除默认 Provider: {name}")
        return False
    
    custom = load_custom_providers()
    if name not in custom:
        print(f"[错误] 自定义 Provider 不存在: {name}")
        return False
    
    del custom[name]
    save_custom_providers(custom)
    return True


# 便捷函数
def get_providers_for_gui(stage: str = "1b") -> List[str]:
    """获取 GUI 下拉框选项列表"""
    available = get_available_providers(stage)
    return [p["id"] for p in available]


def get_provider_display_name(provider_name: str) -> str:
    """获取 Provider 显示名称"""
    config = get_provider_config(provider_name)
    if config:
        return config.get("name", provider_name)
    return provider_name


if __name__ == "__main__":
    # 测试
    print("=== 所有 Provider ===")
    for name, config in get_all_providers().items():
        print(f"  {name}: {config['name']} ({config['type']})")
    
    print("\n=== Stage1b 可用 Provider ===")
    for p in get_available_providers("1b"):
        print(f"  {p['id']}: {p['name']}")
    
    print("\n=== Stage1c 可用 Provider ===")
    for p in get_available_providers("1c"):
        print(f"  {p['id']}: {p['name']}")
