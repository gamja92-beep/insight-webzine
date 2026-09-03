import sqlite3
import random
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
import os
import requests
import re

from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

API_KEY = os.environ.get("API_KEY", "")
MODEL_NAME = "gemini-3.5-flash"

# Unsplash API 키
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

# Unsplash에서 서로 다른 사진을 확실하게 보장하며 2장을 따로 요청하는 함수
def fetch_unsplash_images(query_keyword, count=2):
    images = []
    seen_ids = set()
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    
    # 필요한 장수만큼 개별적으로 요청을 보내서 고유한 사진 ID를 확보합니다.
    for _ in range(count):
        try:
            params = {"query": query_keyword, "orientation": "landscape"}
            response = requests.get("https://api.unsplash.com/photos/random", headers=headers, params=params)
            
            if response.status_code == 200:
                item = response.json()
                photo_id = item.get("id")
                img_url = item["urls"]["regular"]
                author_name = item["user"]["name"]
                
                # 만약 아이디가 겹치면 한 번 더 시도
                if photo_id and photo_id not in seen_ids:
                    seen_ids.add(photo_id)
                    images.append({"url": img_url, "author": author_name})
        except Exception as e:
            print(f"[이미지 검색 오류]: {e}")
    
    # 혹시라도 부족하면 기본 이미지로 채움
    while len(images) < count:
        images.append({"url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe", "author": "Unsplash"})
    
    return images

# 마크다운 정리 및 해시태그 줄바꿈 보장 함수
def clean_and_format_content(text):
    text = re.sub(r'###\s*(.*)', r'<br><b style="font-size: 1.15em; color: #2c3e50; display: block; margin-top: 20px; margin-bottom: 10px;">📌 \1</b>', text)
    text = text.replace('**', '')
    
    hashtags = re.findall(r'(#[\w가-힣]+)', text)
    if hashtags:
        for tag in hashtags:
            text = text.replace(tag, '')
        text = text.strip()
        tag_html = "<br><br><div style='margin-top: 25px; color: #2980b9; font-weight: bold;'>" + " ".join(hashtags) + "</div>"
        text += tag_html

    return text

# 1. 상단 자동 발행 함수
def generate_ai_article(category_name):
    prompts = {
        "AI/테크": ("AI/테크", "최근 주목받는 AI 기술과 IT 혁신 트렌드에 대한 흥미롭고 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 문단은 명확히 여러 개로 나누고 소제목(### 형태)을 포함해줘. 마지막 줄에는 해시태그 5개를 #태그 형태로 붙여줘.", "technology"),
        "경제/주식": ("경제/주식", "최근 주식 시장과 경제 동향, 투자 인사이트에 대한 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 문단은 명확히 여러 개로 나누고 소제목(### 형태)을 포함해줘. 마지막 줄에는 해시태그 5개를 #태그 형태로 붙여줘.", "stock market economy"),
        "세상이야기": ("세상이야기", "우리 주변의 따뜻한 세상 이야기나 일상 속 감동적인 트렌드에 대한 뉴스 기사를 작성해줘. 문단은 명확히 여러 개로 나누고 소제목(### 형태)을 포함해줘. 마지막 줄에는 해시태그 5개를 #태그 형태로 붙여줘.", "warm lifestyle people"),
        "시니어/복지": ("시니어/복지", "시니어 세대를 위한 유용한 복지 정책, 건강 관리, 은퇴 후 삶의 지혜에 대한 전문적인 뉴스 기사를 작성해줘. 문단은 명확히 여러 개로 나누고 소제목(### 형태)을 포함해줘. 마지막 줄에는 해시태그 5개를 #태그 형태로 붙여줘.", "senior elderly care")
    }
    
    cat_info = prompts.get(category_name, ("종합", "최신 트렌드에 대한 유익한 뉴스 기사를 작성해줘.", "news"))
    prompt = cat_info[1]
    keyword = cat_info[2]
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        content = response.text.strip()
    except Exception as e:
        content = f"기사 생성 오류: {e}"

    keyword_map = {"AI/테크": "technology", "경제/주식": "stock market economy", "세상이야기": "warm lifestyle people", "시니어/복지": "senior elderly care"}
    img_keyword = keyword_map.get(category_name, "news")
    
    imgs = fetch_unsplash_images(img_keyword, count=2)
    content = clean_and_format_content(content)

    paragraphs = content.split("\n\n")
    if len(paragraphs) > 1:
        mid_idx = len(paragraphs) // 2
        mid_img_html = f"<br><img src='{imgs[1]['url']}' class='article-img'><div class='img-source'>📷 Photo by {imgs[1]['author']} / Unsplash</div><br>"
        paragraphs.insert(mid_idx, mid_img_html)
        content = "\n\n".join(paragraphs)

    lines = content.split("\n", 1)
    title = lines[0].replace("<br>", "").strip() if len(lines) > 0 else f"{category_name} 소식"
    body_content = lines[1].strip() if len(lines) > 1 else content

    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO articles (category, title, content, image_url, image_author) VALUES (?, ?, ?, ?, ?)", 
                   (category_name, title, body_content, imgs[0]['url'], f"{imgs[0]['author']} / Unsplash"))
    conn.commit()
    conn.close()

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
            
            .article-img {{ width: 100%; max-height: 400px; object-fit: cover; border-radius: 6px; margin-bottom: 5px; }}
            .img-source {{ font-size: 0.8em; color: #666; margin-bottom: 15px; font-style: italic; }}
            
            .content {{ line-height: 1.7; font-size: 1.05em; }}
            
            .btn-group {{ position: absolute; top: 25px; right: 25px; display: flex; gap: 6px; }}
            .edit-btn {{ background: #f39c12; color: white; border: none; padding: 6px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; text-decoration: none; font-weight: bold; }}
            .edit-btn:hover {{ background: #d68910; }}
            .delete-btn {{ background: #e74c3c; color: white; border: none; padding: 6px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; text-decoration: none; font-weight: bold; }}
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
                <div class="btn-group">
                    <a href="/admin/edit/{art['id']}" class="edit-btn">✏️ 수정</a>
                    <a href="/admin/delete/{art['id']}" class="delete-btn" onclick="return confirm('정말 이 기사를 삭제하시겠습니까?');">🗑️ 삭제</a>
                </div>
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
            .ai-expand-btn { background: #8e44ad; }
            .ai-expand-btn:hover { background: #732d91; }
            input[type="text"], select, textarea { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }
            textarea { height: 150px; resize: vertical; }
            label { font-weight: bold; color: #34495e; display: block; margin-top: 10px; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <h1>⚙️ 웹진 관리자 스튜디오</h1>
        
        <!-- 1. 상단: 자동화 기사 생성 -->
        <div class="box" style="border-top: 5px solid #27ae60;">
            <h3>🤖 1. 상단: AI 자동 기사 발행</h3>
            <form action="/admin/create-auto" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                </select>
                <button type="submit">🚀 즉시 자동 기사 발행하기</button>
            </form>
        </div>

        <!-- 2. 중단: 완전 수동 글 작성 -->
        <div class="box" style="border-top: 5px solid #2980b9;">
            <h3>✍️ 2. 중단: 완전 수동 글 작성</h3>
            <form action="/admin/create-manual" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목을 입력하세요" required>
                <label>기사 내용</label>
                <textarea name="content" placeholder="내용을 직접 작성하세요..." required></textarea>
                <button type="submit" class="manual-btn">📝 직접 작성한 글 발행하기</button>
            </form>
        </div>

        <!-- 3. 하단: AI 프롬프트 확장 발행 -->
        <div class="box" style="border-top: 5px solid #8e44ad;">
            <h3>✨ 3. 하단: AI 프롬프트 확장 발행 (서로 다른 2개의 고화질 이미지)</h3>
            <form action="/admin/create-ai-expand" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="기사 제목을 입력하세요" required>
                <label>AI 확장용 프롬프트 / 메모</label>
                <textarea name="prompt" placeholder="예: AI 거품론과 인프라 투자 포인트에 대해 전문적인 분석 기사로 상세히 작성해줘." required></textarea>
                <button type="submit" class="ai-expand-btn">🪄 완벽한 멀티 이미지 기사 발행하기</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/create-auto")
def create_auto(category: str = Form(...)):
    generate_ai_article(category)
    return RedirectResponse(url="/", status_code=303)

@app.post("/admin/create-manual")
def create_manual(category: str = Form(...), title: str = Form(...), content: str = Form(...)):
    keyword_map = {"AI/테크": "technology", "경제/주식": "stock market economy", "세상이야기": "warm lifestyle people", "시니어/복지": "senior elderly care"}
    keyword = keyword_map.get(category, "news")
    imgs = fetch_unsplash_images(keyword, count=1)

    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO articles (category, title, content, image_url, image_author) VALUES (?, ?, ?, ?, ?)", 
                   (category, title, content, imgs[0]['url'], f"{imgs[0]['author']} / Unsplash"))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

# 3. AI 프롬프트 확장 발행 (서로 다른 이미지 고유 ID 보장 로직 적용)
@app.post("/admin/create-ai-expand")
def create_ai_expand(category: str = Form(...), title: str = Form(...), prompt: str = Form(...)):
    system_directive = (
        "당신은 전문 수석 뉴스 기자입니다. "
        "사용자가 제공한 [기사 제목]과 [작성 요청사항/메모]를 바탕으로, "
        "독자들이 읽기 편하도록 여러 개의 단락과 깔끔한 소제목(### 소제목 형태)을 포함하여 풍성하고 상세한 SEO 최적화 뉴스 기사 본문을 작성해 주세요. "
        "마지막 줄에는 반드시 검색에 유용한 해시태그 5개를 #태그 형태로 포함해 주세요."
    )
    
    full_query = f"{system_directive}\n\n[기사 제목]: {title}\n[작성 요청사항/메모]: {prompt}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_query,
        )
        final_content = response.text.strip()
    except Exception as e:
        final_content = prompt

    keyword_map = {"AI/테크": "technology", "경제/주식": "stock market economy", "세상이야기": "warm lifestyle people", "시니어/복지": "senior elderly care"}
    keyword = keyword_map.get(category, "news")
    
    # 2번 개별 요청을 통해 완전히 서로 다른 고유 사진 2장을 확보합니다.
    imgs = fetch_unsplash_images(keyword, count=2)
    
    final_content = clean_and_format_content(final_content)

    paragraphs = final_content.split("\n\n")
    if len(paragraphs) > 1:
        mid_idx = len(paragraphs) // 2
        mid_img_html = f"<br><img src='{imgs[1]['url']}' class='article-img'><div class='img-source'>📷 Photo by {imgs[1]['author']} / Unsplash</div><br>"
        paragraphs.insert(mid_idx, mid_img_html)
        final_content = "\n\n".join(paragraphs)

    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO articles (category, title, content, image_url, image_author) VALUES (?, ?, ?, ?, ?)", 
                   (category, title, final_content, imgs[0]['url'], f"{imgs[0]['author']} / Unsplash"))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/edit/{article_id}", response_class=HTMLResponse)
def edit_page(article_id: int):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, title, content FROM articles WHERE id = ?", (article_id,))
    art = cursor.fetchone()
    conn.close()

    if not art:
        return RedirectResponse(url="/", status_code=303)

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>기사 수정하기</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f4f6f7; }}
            h1 {{ color: #2c3e50; }}
            .box {{ background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #f39c12; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }}
            button:hover {{ background: #d68910; }}
            input[type="text"], select, textarea {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }}
            textarea {{ height: 250px; resize: vertical; }}
            label {{ font-weight: bold; color: #34495e; display: block; margin-top: 10px; }}
            .back-link {{ display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <div class="box">
            <h1>✏️ 기사 수정하기</h1>
            <form action="/admin/update/{art[0]}" method="post">
                <label>카테고리</label>
                <select name="category">
                    <option value="AI/테크" {"selected" if art[1]=="AI/테크" else ""}>AI/테크</option>
                    <option value="경제/주식" {"selected" if art[1]=="경제/주식" else ""}>경제/주식</option>
                    <option value="세상이야기" {"selected" if art[1]=="세상이야기" else ""}>세상이야기</option>
                    <option value="시니어/복지" {"selected" if art[1]=="세상이야기" else ""}>시니어/복지</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" value="{art[2]}" required>
                <label>기사 내용</label>
                <textarea name="content" required>{art[3]}</textarea>
                <button type="submit">💾 수정 사항 저장하기</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/update/{article_id}")
def update_article(article_id: int, category: str = Form(...), title: str = Form(...), content: str = Form(...)):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE articles SET category = ?, title = ?, content = ? WHERE id = ?", (category, title, content, article_id))
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
