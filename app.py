import sqlite3
import random
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
import os
import requests

from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

API_KEY = os.environ.get("API_KEY", "")
MODEL_NAME = "gemini-2.5-flash"

# Unsplash API 키 (원장님의 키를 넣어주세요!)
UNSPLASH_ACCESS_KEY = "14W3nppcnrDp-1qJbpqzxERefLjS25QFZIZ27uYEhhA"

client = genai.Client(api_key=API_KEY)

def init_db():
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT DEFAULT '종합',
            title TEXT,
            content TEXT,
            image_url TEXT,
            image_author TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def fetch_unsplash_image(query_keyword):
    try:
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        params = {"query": query_keyword, "orientation": "landscape"}
        response = requests.get("https://api.unsplash.com/photos/random", headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            image_url = data["urls"]["regular"]
            author_name = data["user"]["name"]
            author_url = data["user"]["links"]["html"]
            return image_url, author_name, author_url
    except Exception as e:
        print(f"[이미지 검색 오류]: {e}")
    
    return "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe", "Unsplash", "https://unsplash.com"

def generate_ai_article(category_name):
    prompts = {
        "AI/테크": ("AI/테크", "최근 주목받는 AI 기술과 IT 혁신 트렌드에 대한 흥미롭고 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 제목과 본문을 포함해줘.", "technology"),
        "경제/주식": ("경제/주식", "최근 주식 시장과 경제 동향, 투자 인사이트에 대한 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 제목과 본문을 포함해줘.", "stock market economy"),
        "세상이야기": ("세상이야기", "우리 주변의 따뜻한 세상 이야기나 일상 속 감동적인 트렌드에 대한 뉴스 기사를 작성해줘. 제목과 본문을 포함해줘.", "warm lifestyle people"),
        "시니어/복지": ("시니어/복지", "시니어 세대를 위한 유용한 복지 정책, 건강 관리, 은퇴 후 삶의 지혜에 대한 전문적인 뉴스 기사를 작성해줘. 제목과 본문을 포함해줘.", "senior elderly care")
    }
    
    cat_info = prompts.get(category_name, ("종합", "최신 트렌드에 대한 유익한 뉴스 기사를 작성해줘.", "news"))
    prompt = cat_info[1]
    keyword = cat_info[2]
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        text = response.text
        lines = text.split("\n", 1)
        title = lines[0].replace("#", "").strip() if len(lines) > 0 else f"{category_name} 소식"
        content = lines[1].strip() if len(lines) > 1 else text

        img_url, author_name, author_url = fetch_unsplash_image(keyword)

        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO articles (category, title, content, image_url, image_author) VALUES (?, ?, ?, ?, ?)", 
                       (category_name, title, content, img_url, f"{author_name} / Unsplash"))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[자동생성 오류] {category_name}: {e}")

def scheduled_job():
    categories = ["AI/테크", "경제/주식", "세상이야기", "시니어/복지"]
    target_cat = random.choice(categories)
    generate_ai_article(target_cat)

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_job, 'interval', hours=6)
scheduler.start()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = None):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    
    if category and category != "전체":
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE category = ? ORDER BY id DESC", (category,))
    else:
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles ORDER BY id DESC")
        
    rows = cursor.fetchall()
    conn.close()

    articles = [{
        "id": r[0], "category": r[1], "title": r[2], "content": r[3], 
        "image_url": r[4], "image_author": r[5], "created_at": r[6]
    } for r in rows]
    
    categories = ["전체", "AI/테크", "경제/주식", "세상이야기", "시니어/복지"]

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>인사이트 종합 웹진</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 850px; margin: 40px auto; padding: 20px; background: #f9f9f9; color: #333; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h1 {{ color: #2c3e50; margin: 0; }}
            .admin-link {{ display: inline-block; padding: 8px 14px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 14px; }}
            .admin-link:hover {{ background: #2980b9; }}
            
            .nav-tabs {{ display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }}
            .tab-item {{ padding: 8px 16px; background: #e2e8f0; color: #475569; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 14px; transition: 0.2s; }}
            .tab-item:hover, .tab-item.active {{ background: #3498db; color: white; }}

            .article {{ background: white; padding: 25px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); position: relative; }}
            .badge {{ display: inline-block; padding: 4px 10px; background: #e0f2fe; color: #0369a1; border-radius: 4px; font-size: 0.8em; font-weight: bold; margin-bottom: 8px; }}
            .article h2 {{ margin-top: 5px; color: #2980b9; }}
            .date {{ font-size: 0.85em; color: #888; margin-bottom: 15px; }}
            
            .article-img {{ width: 100%; max-height: 400px; object-fit: cover; border-radius: 6px; margin-bottom: 10px; }}
            .img-source {{ font-size: 0.8em; color: #666; margin-bottom: 15px; font-style: italic; }}
            
            .content {{ line-height: 1.6; white-space: pre-wrap; }}
            .delete-btn {{ position: absolute; top: 25px; right: 25px; background: #e74c3c; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; text-decoration: none; font-weight: bold; }}
            .delete-btn:hover {{ background: #c0392b; }}
        </style>
    </head>
    <body>
        <div class="header-flex">
            <h1>📰 인사이트 종합 웹진 (24시 자동운영)</h1>
            <a href="/admin" class="admin-link">⚙️ 관리자 페이지</a>
        </div>

        <div class="nav-tabs">
    """
    
    for cat in categories:
        active_class = "active" if (not category and cat == "전체") or (category == cat) else ""
        cat_param = "" if cat == "전체" else f"?category={cat}"
        html += f'<a href="/{cat_param}" class="tab-item {active_class}">{cat}</a>'
        
    html += "</div>"

    if not articles:
        html += "<p style='text-align:center; color:#777; margin-top:50px;'>등록된 기사가 없습니다. 관리자 페이지에서 뉴스를 발행해 보세요!</p>"
    else:
        for art in articles:
            cat_name = art['category'] if art['category'] else '종합'
            img_tag = f"<img src='{art['image_url']}' class='article-img'>" if art['image_url'] else ""
            source_tag = f"<div class='img-source'>📷 Photo by {art['image_author']}</div>" if art['image_author'] else ""
            
            html += f"""
            <div class="article">
                <a href="/admin/delete/{art['id']}" class="delete-btn" onclick="return confirm('정말 이 기사를 삭제하시겠습니까?');">🗑️ 삭제</a>
                <span class="badge">{cat_name}</span>
                <h2>{art['title']}</h2>
                <div class="date">발행일시: {art['created_at']}</div>
                {img_tag}
                {source_tag}
                <div class="content">{art['content']}</div>
            </div>
            """
    html += "</body></html>"
    return html

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>인사이트 웹진 관리자</title>
        <style>
            body { font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f4f6f7; }
            h1 { color: #2c3e50; }
            .box { background: white; padding: 25px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            button { background: #27ae60; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }
            button:hover { background: #219653; }
            .manual-btn { background: #2980b9; }
            .manual-btn:hover { background: #1f618d; }
            input[type="text"], select, textarea { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }
            textarea { height: 180px; resize: vertical; }
            label { font-weight: bold; color: #34495e; display: block; margin-top: 10px; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <h1>⚙️ 웹진 관리자 스튜디오 (자동 + 수동 AI 확장)</h1>
        
        <div class="box">
            <h3>🤖 AI 수동 즉시 생성 (전체 자동)</h3>
            <p>선택한 카테고리에 맞는 기사와 고화질 사진, 출처가 자동으로 발행됩니다.</p>
            <form action="/admin/create" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                </select>
                <button type="submit">🚀 지금 즉시 AI 기사 + 이미지 생성하기</button>
            </form>
        </div>

        <div class="box">
            <h3>✍️ 원장님 맞춤형 AI 글 확장 발행 (수동 프롬프트)</h3>
            <p>원하시는 제목과 대략적인 메모·키워드를 적어주시면, 제미니가 이를 바탕으로 살을 붙여 풍성하고 전문적인 기사로 확장하여 발행하고 이미지도 함께 붙여줍니다.</p>
            <form action="/admin/manual-expand" method="post">
                <label>카테고리</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                </select>

                <label>기사 제목</label>
                <input type="text" name="title" placeholder="기사 제목을 입력하세요" required>
                
                <label>핵심 내용 및 프롬프트 (메모나 키워드만 적어도 됩니다)</label>
                <textarea name="prompt" placeholder="예: 최근 금리가 인하될 가능성이 높아지면서 배당주에 대한 관심이 커지고 있다. 은퇴자들의 자산 관리 팁을 중심으로 전문적인 기사로 작성해줘." required></textarea>
                
                <button type="submit" class="manual-btn">✨ AI로 글을 확장하여 멋지게 발행하기</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/create")
def create_article(category: str = Form(...)):
    generate_ai_article(category)
    return RedirectResponse(url="/", status_code=303)

@app.post("/admin/manual-expand")
def manual_expand_article(category: str = Form(...), title: str = Form(...), prompt: str = Form(...)):
    full_prompt = f"다음 주제와 내용을 바탕으로, 전문적이고 독자들이 흥미로워할 만한 SEO 최적화 뉴스 기사 본문을 상세하고 풍성하게 작성해줘. (프롬프트 문장 자체를 그대로 출력하지 말고, 오직 기사 본문 내용만 작성해줘)\n\n[제목]: {title}\n[핵심 내용 및 요청사항]: {prompt}"
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_prompt,
        )
        content = response.text.strip()
    except Exception as e:
        content = prompt

    keyword_map = {
        "AI/테크": "technology",
        "경제/주식": "stock market economy",
        "세상이야기": "warm lifestyle people",
        "시니어/복지": "senior elderly care"
    }
    keyword = keyword_map.get(category, "news")
    
    img_url, author_name, author_url = fetch_unsplash_image(keyword)

    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO articles (category, title, content, image_url, image_author) VALUES (?, ?, ?, ?, ?)", 
                   (category, title, content, img_url, f"{author_name} / Unsplash"))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/delete/{article_id}")
def delete_article(article_id: int):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)
