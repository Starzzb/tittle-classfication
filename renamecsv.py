import pandas as pd

# 1. 读取 CSV 文件
df = pd.read_csv('output/title_review.csv')

# 2. 将某一列全部改为同样的文本（比如将 "列名" 这一列全部改为 "新文本"）
df['review_status'] = '已确认'

# 3. 保存回 CSV（index=False 表示不保存行号）
df.to_csv('output/title_review.csv', index=False)