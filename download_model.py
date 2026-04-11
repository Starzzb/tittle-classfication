from transformers import AutoTokenizer, AutoModel
import os


model_name = "bert-base-chinese"
local_save_path = "./models/bert-base-chinese"

def download_and_save():
    if os.path.exists(local_save_path):
        print(f"✅ 模型已存在: {os.path.abspath(local_save_path)}")
        return

    print(f"🔄 开始下载模型: {model_name}")
    print("💡 提示：已配置国内镜像，首次下载约需 1-3 分钟...")
    
    try:
        # 下载分词器
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            # ✅ 关键：指定国内镜像源
            mirror="https://hf-mirror.com"
        )
        tokenizer.save_pretrained(local_save_path)
        
        # 下载模型权重
        model = AutoModel.from_pretrained(
            model_name,
            mirror="https://hf-mirror.com"
        )
        model.save_pretrained(local_save_path)
        
        print(f"✅ 下载成功！路径: {os.path.abspath(local_save_path)}")
        print(f"📦 模型大小: {sum(os.path.getsize(os.path.join(local_save_path, f)) for f in os.listdir(local_save_path) if f.endswith('.bin')) / 1024 / 1024:.1f} MB")
        
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        print("💡 备选方案：使用 ModelScope 手动下载（见下方说明）")

if __name__ == "__main__":
    download_and_save()