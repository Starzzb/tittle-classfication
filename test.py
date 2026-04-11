# test_load.py
from transformers import AutoTokenizer, AutoModel
import torch

local_path = "./models/bert-base-chinese"

print("🔍 正在加载模型...")
tokenizer = AutoTokenizer.from_pretrained(local_path)
model = AutoModel.from_pretrained(local_path)

print("✅ 模型加载成功！")
print(f"📊 参数量: {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M")

# 简单推理测试
text = "视频标题分类测试"
inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=50)

with torch.no_grad():
    outputs = model(**inputs)
    print(f"🎯 输出维度: {outputs.last_hidden_state.shape}")
    print("✨ 一切正常，可以开始微调了！")