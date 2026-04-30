from datetime import datetime, UTC
import pandas as pd
import requests
from openai import OpenAI
from pymongo import MongoClient
from diffusers import StableDiffusionXLPipeline
import torch
import cloudinary
import cloudinary.uploader
import io
from dotenv import load_dotenv
import os
import json, re

load_dotenv()

# === 0. 環境變數 ===
MONGODB_URI      = "mongodb+srv://FYP_user:Fyp2526@cluster0.kgrbc7r.mongodb.net/?appName=Cluster0"
NEWS_API_KEY     = "ee56a89c0e5c45bd80366c8dc5fcedab"
DEEPSEEK_API_KEY = "sk-06b62597f676476bb552d1be846d56ad"
CLOUDINARY_CLOUD_NAME = "dng3getvr"
CLOUDINARY_API_KEY    = "125743662316769"
CLOUDINARY_API_SECRET = "rJ9_AzHW86RguiPxpIS6Oi78TJM"

# === 1. Mongo 連線 ===
mongo_client = MongoClient(MONGODB_URI)
db           = mongo_client["fyp-news"]
articles_col = db["articles"]

# === 2. DeepSeek Client ===
client = OpenAI(
    api_key  = DEEPSEEK_API_KEY,
    base_url = "https://api.deepseek.com",
)

# === 3. SDXL + 貓咪 LoRA 初始化（GenCatPhoto.py）===
print("start download/reload model")
pipe = StableDiffusionXLPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype     = torch.float16,
    use_safetensors = True,
).to("cuda")
pipe.load_lora_weights("ChaosMon/corgy_CatText2Image_LoRA")
print("model loaded!")

os.makedirs("./Output", exist_ok=True)

# === 4. Cloudinary 初始化 ===
USE_CLOUDINARY = all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])
if USE_CLOUDINARY:
    cloudinary.config(
        cloud_name = CLOUDINARY_CLOUD_NAME,
        api_key    = CLOUDINARY_API_KEY,
        api_secret = CLOUDINARY_API_SECRET,
    )
    print("[Cloudinary] 已設定 ✅")
else:
    print("[Cloudinary] 未設定，圖片只存本地")

# === 5. 讀 JSON 世界觀 + 角色 + 魔法 ===
file_paths = {
    "worldview":  "/Code/GenNews/FYP.worldviews.json", 
    "characters": "/Code/GenNews/FYP.characters.json",
    "core_magic": "/Code/GenNews/FYP.core_magic.json",
}

worldview_data  = pd.read_json(file_paths["worldview"]).to_dict("records")[0]
characters_data = pd.read_json(file_paths["characters"]).to_dict("records")
core_magic_data = pd.read_json(file_paths["core_magic"]).to_dict("records")

integrated_worldview = {
    "世界設定": worldview_data,
    "核心角色": characters_data,
    "魔法元素": core_magic_data,
}

WORLDVIEW_DESCRIPTION = f"""
你需要完全掌握以下完整的世界觀設定，包括世界背景、角色和魔法元素，後續任務必須嚴格遵循這些設定：

【世界設定】
{integrated_worldview['世界設定']}

【核心角色】
{integrated_worldview['核心角色']}

【魔法元素】
{integrated_worldview['魔法元素']}
"""

# === 6. 建立新聞改寫 prompt ===
def build_worldview_prompt(title: str, content: str) -> str:
    content = content or ""
    return f"""
請根據以下世界觀改寫並評論一篇新聞：

世界觀設定：
{WORLDVIEW_DESCRIPTION}

=== 原始新聞標題 ===
{title}

=== 原始新聞內容（英文）===
{content}

任務：
1. 用繁體中文寫一篇世界觀視角新聞／評論。
2. 保持核心事實（時間、地點、人物、事件）不要亂改。
3. 可以加少量背景解釋和各式吐槽。
4. 文章開頭不要重複標題，直接由正文開始。

請以 JSON 格式回傳，格式如下：
{{
  "title": "繁體中文世界觀標題（唔超過20字）",
  "content": "完整文章內容（HTML格式，用<p>分段）"
}}
只輸出 JSON，不要其他文字。
"""

# === 7. 拉新聞 ===
def fetch_top_news(country="us", category="technology", page_size=5) -> pd.DataFrame:
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params  = {
            "country":  country,
            "category": category,
            "pageSize": page_size,
            "language": "en",
            "apiKey":   NEWS_API_KEY,
        },
        timeout = 30,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json().get("articles", []))

# === 8. DeepSeek 改寫新聞 ===
def rewrite_with_llm_worldview(row):
    title = row.get("title") or ""
    content = (row.get("content") or "") + "\n" + (row.get("description") or "")
    prompt = build_worldview_prompt(title, content)
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一位嚴守指示的寫作助理。只輸出合法 JSON，不要 markdown code block。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
    )
    raw = resp.choices[0].message.content.strip()
    # 清除可能有嘅 ```json ``` 包裹
    raw = re.sub(r"^```json\s*|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
        return result.get("title", ""), result.get("content", raw)
    except json.JSONDecodeError:
        # fallback：如果 JSON 解析失敗，原始內容當 content，title 用英文
        return title, raw

# === 9. DeepSeek 生成圖片 Prompt ===
def build_image_prompt(title: str, worldview_content: str) -> str:
    snippet = (worldview_content or title)[:200].replace("\n", " ")
    resp = client.chat.completions.create(
        model       = "deepseek-chat",
        messages    = [
            {"role": "system", "content": "你是一位 Stable Diffusion 提示詞專家。你的輸出只能是英文 prompt，不能有任何中文或解釋。"},
            {"role": "user",   "content": f"""
根據以下世界觀新聞內文，寫一段 Stable Diffusion XL 的圖片生成 prompt。
風格：漂浮島嶼、永遠春天、貓咪居民、Studio Ghibli 風格、水彩插畫、溫暖色調。
新聞標題：{title}
內文摘要：{snippet}
要求：英文 prompt，逗號分隔，結尾加：Studio Ghibli style, watercolor illustration, pastel colors, soft lighting
只輸出 prompt，不要解釋
"""},
        ],
        temperature = 0.7,
        max_tokens  = 200,
    )
    return resp.choices[0].message.content.strip()

# === 10. 圖片生成 + Cloudinary 上傳（GenCatPhoto.py 邏輯）===
def generate_and_upload_image(title: str, worldview_content: str) -> str | None:
    try:
        print("  [圖片] 生成 prompt...")
        image_prompt = build_image_prompt(title, worldview_content)
        print(f"  [圖片] Prompt: {image_prompt[:80]}...")

        negative_prompt = (
            "low quality, blurry, pixelated, distorted, deformed, extra limbs, missing limbs, "
            "text, watermark, logo, signature, human, person, crowd, modern objects, cars, buildings, "
            "realistic style, photorealistic, dark, gloomy, horror, scary, dull colors, overexposed, underexposed, "
            "artifacts, noise, grainy, low resolution, oversaturated, unnatural poses"
        )
        print("  [圖片] SDXL 生成中（約需 30–60 秒）...")
        image = pipe(
            prompt              = image_prompt,
            negative_prompt     = negative_prompt,
            num_inference_steps = 40,
            guidance_scale      = 8,
            height              = 1024,
            width               = 1024,
        ).images[0]

        output_dir  = os.path.join(os.getcwd(), "Output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "text2image_output.png")
        image.save(output_path)
        print(f"  [圖片] 本地備份：Output/text2image_output.png")

        if USE_CLOUDINARY:
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_bytes = buffered.getvalue()
            result = cloudinary.uploader.upload(
                img_bytes,
                folder         = "fyp-news",
                resource_type  = "image",
                format         = "webp",
                transformation = [{"width": 1024, "height": 576, "crop": "fill", "quality": "auto"}],
            )
            url = result["secure_url"]
            print(f"  [圖片] ✅ Cloudinary URL: {url}")
            return url
        return None

    except Exception as e:
        print(f"  [圖片] ❌ 失敗，略過：{e}")
        return None

# === 11. 寫入 MongoDB ===
def save_articles_to_mongo(df: pd.DataFrame):
    docs = []
    now = datetime.now(UTC)
    for _, row in df.iterrows():
        doc = {
            "title":               row.get("cat_title") or row.get("title"),
            "originalTitle":       row.get("title"),
            "source":              (row.get("source") or {}).get("name")
                                   if isinstance(row.get("source"), dict)
                                   else row.get("source"),
            "originalDescription": row.get("description"),
            "worldviewContent":    row.get("cat_worldview"),
            "url":                 row.get("url"),
            "category":            row.get("category", "general"),      # ← 新增
            "categoryLabel":       row.get("categoryLabel", "世界新聞"), # ← 新增
            "createdAt":           now,
        }
        if row.get("imageUrl"):
            doc["imageUrl"] = row["imageUrl"]
        docs.append(doc)
    if docs:
        articles_col.insert_many(docs)
        print(f"  [MongoDB] ✅ 寫入 {len(docs)} 篇文章")

        
# === 12. main 流程 ===
CATEGORIES = [
    ("technology",   "科技"),
    ("entertainment","遊戲"),
    ("general",      "生活"),
]

def main():
    results = []

    for api_cat, label in CATEGORIES:
        df_news = fetch_top_news(category=api_cat, page_size=3)
        print(f"[NewsAPI] {label}（{api_cat}）：抓取 {len(df_news)} 篇\n")

        for i, (_, row) in enumerate(df_news.iterrows(), 1):
            title = row.get("title") or ""
            print(f"─── [{i}] {title[:55]}")

            worldview_title, worldview_text = rewrite_with_llm_worldview(row)
            print(f"  [DeepSeek] ✅ → {worldview_title[:30]}")

            image_url = generate_and_upload_image(worldview_title, worldview_text)

            row_dict = row.to_dict()
            row_dict["cat_title"]      = worldview_title
            row_dict["cat_worldview"]  = worldview_text
            row_dict["imageUrl"]       = image_url
            row_dict["category"]       = api_cat   # ← 新增
            row_dict["categoryLabel"]  = label     # ← 新增
            results.append(row_dict)

    save_articles_to_mongo(pd.DataFrame(results))
    print(f"\n[{datetime.now()}] Generated and saved {len(results)} articles")

if __name__ == "__main__":
    main()