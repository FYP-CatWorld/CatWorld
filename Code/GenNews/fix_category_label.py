# fix_category_label.py
from pymongo import MongoClient
import certifi
import os

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://FYP_user:Fyp2526@cluster0.kgrbc7r.mongodb.net/?appName=Cluster0")
mongo_client  = MongoClient(MONGODB_URI)
db = mongo_client["fyp-news"]
articles_col = db["articles"]

result = articles_col.update_many(          # ← 改用 articles_col
    {"categoryLabel": {"$exists": False}},
    [{"$set": {"categoryLabel": {
        "$switch": {
            "branches": [
                {"case": {"$eq": ["$category", "game"]},       "then": "遊戲"},
                {"case": {"$eq": ["$category", "gaming"]},     "then": "遊戲"},
                {"case": {"$eq": ["$category", "technology"]}, "then": "科技"},
                {"case": {"$eq": ["$category", "tech"]},       "then": "科技"},
                {"case": {"$eq": ["$category", "life"]},       "then": "生活"},
            ],
            "default": "生活"
        }
    }}}]
)

print(f"Updated: {result.modified_count} documents")
mongo_client.close() 