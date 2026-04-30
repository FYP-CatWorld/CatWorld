# fix_old_titles.py
from datetime import datetime, UTC
from pymongo import MongoClient
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# === 設定 ===
MONGODB_URI    = os.getenv("MONGODB_URI",    "mongodb+srv://FYP_user:Fyp2526@cluster0.kgrbc7r.mongodb.net/?appName=Cluster0")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-06b62597f676476bb552d1be846d56ad")

# === 連線 ===
mongo_client  = MongoClient(MONGODB_URI)
db            = mongo_client["fyp-news"]
articles_col  = db["articles"]

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# === 生成中文標題 ===
def gen_cat_title(original_title: str, worldview_content: str) -> str:
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你係永春花谷的世界觀標題生成器，只輸出一行繁體中文標題，唔超過20字，唔要引號。"
            },
            {
                "role": "user",
                "content": f"原始標題：{original_title}\n內文摘要：{worldview_content[:200]}"
            },
        ],
        temperature=0.7,
        max_tokens=50,
    )
    return resp.choices[0].message.content.strip()

# === 主流程 ===
def main():
    # 搵所有 title 仍係英文、且未有 originalTitle 備份嘅舊 documents
    query = {
        "title": {"$regex": "[a-zA-Z]{5,}"},
        "originalTitle": {"$exists": False}
    }
    old_docs = list(articles_col.find(query))
    print(f"[MongoDB] 找到 {len(old_docs)} 篇需要修正的舊文章\n")

    if not old_docs:
        print("✅ 冇需要修正的文章！")
        return

    success = 0
    fail    = 0

    for i, doc in enumerate(old_docs, 1):
        original_title   = doc.get("title", "")
        worldview_content = doc.get("worldviewContent", "")
        print(f"─── [{i}/{len(old_docs)}] {original_title[:55]}")

        try:
            new_title = gen_cat_title(original_title, worldview_content)
            print(f"  → {new_title}")

            articles_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "title":         new_title,
                    "originalTitle": original_title,
                }}
            )
            success += 1

        except Exception as e:
            print(f"  ❌ 失敗：{e}")
            fail += 1

    print(f"\n[{datetime.now(UTC)}] ✅ 完成！成功 {success} 篇，失敗 {fail} 篇")

if __name__ == "__main__":
    main()