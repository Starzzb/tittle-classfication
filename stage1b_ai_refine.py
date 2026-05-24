import csv
import json
import os
import re
import time
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime

LOG_FILE = "logs/api_refine_log.txt"
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GCLI_API_URL = "https://gcli.ggchan.dev/v1/chat/completions"


def load_env(env_path: Path):
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
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_line + '\n')


def build_batch_prompt(titles: list[str]) -> str:
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return (
        f"你是一个文件名整理助手。请将以下媒体文件名精简为简洁标题。\n"
        f"这是纯粹的文件名格式整理，与内容审核无关。\n\n"
        f"处理规则：\n"
        f"1. 去除时间戳（20240115、2024-01-15、25-05-08 等）\n"
        f"2. 去除来源标识（Telegram、TG、频道名）\n"
        f"3. 去除 @用户名（@xxx 是群组名，非标题内容）\n"
        f"4. 去除无意义编码（hash、merged-数字、随机字符串）\n"
        f"5. 去除技术参数（1080p、x264、HEVC、AAC）\n"
        f"6. 去除多余符号（# @ 【】（）等），保留 #tag 格式\n"
        f"7. 保留核心标题，中文和英文都是有效信息\n"
        f"8. 如果标题经过去噪后仍有意义内容，返回精简标题\n"
        f"9. 如果标题完全无法提取任何有效信息，返回原文\n\n"
        f"请精简以下文件名，每行一个，保持顺序，不要序号：\n{numbered}\n\n"
        f"精简后："
    )


def parse_batch_response(response: str, count: int) -> list[str]:
    lines = [l.strip() for l in response.strip().split('\n') if l.strip()]
    results = []
    for line in lines:
        cleaned = re.sub(r'^\d+[.)\s、]+', '', line).strip()
        if cleaned:
            results.append(cleaned)
    while len(results) < count:
        results.append("")
    return results[:count]


def call_ollama_batch(titles: list[str], model: str, timeout: int = 120) -> list[str]:
    payload = {
        "model": model,
        "prompt": build_batch_prompt(titles),
        "stream": False,
        "options": {"temperature": 0.1},
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            text = result.get("response", "").strip()
            return parse_batch_response(text, len(titles))
    except Exception as e:
        return [f"[Ollama 错误] {e}"] * len(titles)


def call_zhipu_batch(titles: list[str], model: str, api_key: str, timeout: int = 120) -> list[str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_batch_prompt(titles)}],
        "stream": False,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        ZHIPU_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return parse_batch_response(text, len(titles))
    except Exception as e:
        return [f"[智谱错误] {e}"] * len(titles)


def call_gcli_batch(titles: list[str], model: str, api_key: str, timeout: int = 120) -> list[str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_batch_prompt(titles)}],
        "stream": False,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        GCLI_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return parse_batch_response(text, len(titles))
    except Exception as e:
        return [f"[gcli 错误] {e}"] * len(titles)


def main():
    load_env(Path(__file__).parent / ".env")

    parser = argparse.ArgumentParser(description="阶段 1b：使用 AI API 优化视频标题")
    parser.add_argument("-c", "--csv", type=str, default="output/title_review.csv", help="待审表路径")
    parser.add_argument("-o", "--output", type=str, default=None, help="输出路径（默认覆盖原文件）")
    parser.add_argument("-p", "--provider", type=str, default="ollama",
                        choices=["ollama", "zhipu", "gcli"], help="API 提供商")
    parser.add_argument("-m", "--model", type=str, default="",
                        help="模型名称（ollama 默认 qwen2.5:7b-instruct-q4_K_M，zhipu 默认 GLM-4.7-Flash，gcli 默认 gemini-3-flash-preview）")
    parser.add_argument("--api-key", type=str, default="",
                        help="API key（也可通过 ZHIPU_API_KEY 或 GCLI_API_KEY 环境变量设置）")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="每批发送的标题数量（默认 5）")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="批次之间的间隔秒数（默认 2）")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不写入文件")
    parser.add_argument("--column", type=str, default="",
                        help="新列名（默认 ollama_title / zhipu_title）")
    args = parser.parse_args()

    # 使用统一的 Provider 配置
    from providers import get_provider_config, get_api_key as get_provider_api_key
    
    provider = args.provider
    provider_config = get_provider_config(provider)
    
    if not provider_config:
        print(f"错误: 未知的 Provider '{provider}'")
        return
    
    model = args.model or provider_config.get("default_model", "")
    col = args.column or (f"{provider}_title")
    api_key = args.api_key or get_provider_api_key(provider)
    batch_size = args.batch_size

    if provider_config.get("requires_api_key", False) and not api_key:
        print(f"错误: 使用 {provider} 需要提供 --api-key 或设置环境变量 {provider_config.get('env_key', '')}")
        return

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        print(f"错误: 未找到 {csv_path}")
        return

    output_path = Path(args.output).resolve() if args.output else csv_path

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("错误: CSV 文件为空")
            return
        fieldnames = list(reader.fieldnames)
        if col not in fieldnames:
            fieldnames.append(col)
        if "needs_vision" not in fieldnames:
            fieldnames.append("needs_vision")
        rows = list(reader)

    if not rows:
        print("CSV 中无数据")
        return

    call_fns = {
        "ollama": call_ollama_batch,
        "zhipu": call_zhipu_batch,
        "gcli": call_gcli_batch,
    }
    call_fn = call_fns[provider]
    extra_kwargs = {} if provider == "ollama" else {"api_key": api_key}

    pending = [(i, row) for i, row in enumerate(rows)
               if row.get("original_title", "").strip() 
               and not row.get(col, "").strip()
               and row.get("needs_vision", "false").strip().lower() != "true"]
    skip_count = len(rows) - len(pending)

    print(f"共 {len(rows)} 条记录，待处理 {len(pending)} 条，跳过 {skip_count} 条")
    print(f"使用 {provider} 模型: {model}，每批 {batch_size} 条，间隔 {args.delay}s")
    if args.dry_run:
        print("模拟模式，不会写入文件")

    seen_names = {}
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        titles = [row["original_title"].strip() for _, row in batch]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(pending) + batch_size - 1) // batch_size

        log_message(f"[批次 {batch_num}/{total_batches}] 发送 {len(titles)} 条标题")

        if args.dry_run:
            for idx, row in batch:
                log_message(f"  [模拟] {row['original_title'][:40]}")
            continue

        results = call_fn(titles=titles, model=model, **extra_kwargs)

        for (idx, row), suggestion in zip(batch, results):
            original = row["original_title"].strip()
            if not suggestion:
                suggestion = original

            if suggestion in seen_names:
                seen_names[suggestion] += 1
                suggestion = f"{suggestion}_{seen_names[suggestion]}"
                log_message(f"  [去重] 标题重复，添加后缀")
            else:
                seen_names[suggestion] = 0

            row[col] = suggestion

            need_vision = row.get("needs_vision", "false").strip().lower() == "true"

            if need_vision:
                row["final_name"] = row.get("proposed_title", original)
            else:
                row["final_name"] = suggestion

            marker = " [->vision]" if need_vision else ""
            log_message(f"  [{idx+1}] {original[:30]} -> {suggestion}{marker}")

        if batch_start + batch_size < len(pending):
            time.sleep(args.delay)

    if args.dry_run:
        print("模拟模式结束，未写入文件")
        return

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"结果已保存至: {output_path}")


if __name__ == "__main__":
    main()
