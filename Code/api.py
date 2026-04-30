import os, re, markdown
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
import certifi

app = Flask(__name__)
CORS(app)

# === MongoDB 連線 ===
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://FYP_user:Fyp2526@cluster0.kgrbc7r.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["fyp-news"]
articles_col = db["articles"]

# === 輔助函數 ===
def extract_title(text: str) -> str:
    """從 markdown 內文抽取第一個 # 標題"""
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line).strip()
    return ""

def extract_excerpt(text: str, max_len: int = 100) -> str:
    """抽取第一段純文字作摘要"""
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            clean = re.sub(r"[*_`>]", "", line)
            return clean[:max_len] + ("..." if len(clean) > max_len else "")
    return ""

def extract_category(text: str) -> str:
    """從第一行抽取 CATEGORY: xxx"""
    if not text:
        return "世界新聞"
    first_line = text.strip().split('\n')[0]
    if first_line.startswith("CATEGORY:"):
        return first_line.replace("CATEGORY:", "").strip()
    return "世界新聞"

def serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    doc["id"]  = doc["_id"]

    worldview = doc.get("worldviewContent") or ""

    # 移除 CATEGORY 行 + --- 分隔線
    lines = worldview.strip().split('\n')
    category = doc.get("categoryLabel") or "世界新聞"
    body_start = 0
    if lines and lines[0].startswith("CATEGORY:"):
        category   = lines[0].replace("CATEGORY:", "").strip()
        body_start = 1
        if len(lines) > 1 and lines[1].strip() == "---":
            body_start = 2

    body = '\n'.join(lines[body_start:]).strip()

    doc["title"]         = extract_title(body) or doc.get("title") or "未命名新聞"
    doc["content"]       = markdown.markdown(body)
    doc["excerpt"]       = extract_excerpt(body)
    doc["author"]        = doc.get("source") or "永春花谷特派員"
    doc["categoryLabel"] = category
    doc["emoji"]         = "🐱"
    doc["tags"]          = doc.get("tags") or ["新聞", "群島動態"]
    doc["imageUrl"]      = doc.get("imageUrl") or ""

    # createdAt 轉字串
    if doc.get("createdAt"):
        doc["createdAt"] = str(doc["createdAt"])

    return doc

# === API 路由 ===
@app.route("/api/news", methods=["GET"])
def get_news():
    limit = int(request.args.get("limit", 20))
    docs  = list(articles_col.find().sort("createdAt", -1).limit(limit))
    return jsonify([serialize(d) for d in docs])

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=True)