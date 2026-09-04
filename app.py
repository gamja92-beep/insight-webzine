import sys
import os
import sqlite3
import random
import requests
import re
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
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

# 단일 고화질 대표 이미지 동적 가져오기
def fetch_single_image(query_keyword):
    try:
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        response = requests.get("https://api.unsplash.com/photos/random", headers=headers, params={"query": query_keyword, "orientation": "landscape"}, timeout=5)
        if response.status_code == 200:
            item = response.json()
            return item["urls"]["regular"], item["user"]["name"]
    except Exception as e:
        print(f"[이미지 검색 오류]: {e}")
    
    return "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe", "Unsplash"

# 🌟 [최종 완성 정제 함수] 소제목 누락 완벽 보완 및 기호 청소
def clean_and_format_content(text, category_name="종합"):
    # 1. 마크다운 특수문자 정리
    text = text.replace('**', '').replace('__', '')
    
    # 2. 불필요한 특수 기호 줄 제거
    lines_cleaned = []
    for line in text.split('\n'):
        stripped = line.strip()
        if re.match(r'^[\*\-\_\#\s]+$', stripped):
            continue
        lines_cleaned.append(line)
    text = '\n'.join(lines_cleaned)

    # 3. 해시태그 분리 및 추출
    all_words = text.split()
    hashtags = [w for w in all_words if w.startswith('#') and len(w) > 1 and not w.startswith('#2c')]
    
    for tag in hashtags:
        text = text.replace(tag, '')
        
    # 4. 소제목 변환 (### 형태뿐만 아니라, AI가 기호 없이 쓴 짧은 독립 문장 형태의 소제목도 완벽하게 HTML로 승격)
    processed_lines = []
    for line in text.split('\n'):
        line_str = line.strip()
        if not line_str:
            continue
        # 명시적 ### 소제목이거나, 문장이 짧고(예: 40자 미만) 마침표로 끝나지 않는 독립 소제목 패턴인 경우
        if line_str.startswith('###'):
            title_text = line_str.replace('###', '').strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 35px; margin-bottom: 14px; font-size: 1.25em; font-weight: 800; letter-spacing: -0.5px;">{title_text}</h3>')
        elif len(line_str) < 42 and not line_str.endswith(('.', '?', '!')) and not line_str.startswith('<'):
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 35px; margin-bottom: 14px; font-size: 1.25em; font-weight: 800; letter-spacing: -0.5px;">{line_str}</h3>')
        else:
            processed_lines.append(f'<p style="margin-bottom: 18px; text-align: justify; word-break: keep-all;">{line_str}</p>')
            
    final_html = "".join(processed_lines)
    
    # 5. 해시태그 보정 및 깔끔한 출력
    unique_tags = list(dict.fromkeys(hashtags))
    fallback_tags = {
        "AI/테크": ["#인공지능", "#테크트렌드", "#AI반도체", "#디지털혁신", "#미래기술"],
        "경제/주식": ["#주식투자", "#경제동향", "#시장분석", "#자산관리", "#투자전략"],
        "세상이야기": ["#세상이야기", "#라이프스타일", "#감동글", "#일상소통", "#휴식"],
        "시니어/복지": ["#시니어복지", "#은퇴설계", "#건강관리", "#노후준비", "#행복한삶"]
    }
    
    if len(unique_tags) < 3:
        unique_tags = fallback_tags.get(category_name, ["#종합뉴스", "#트렌드", "#인사이트", "#정보", "#공유"])

    clean_tags_list = [t if t.startswith('#') else f"#{t}" for t in unique_tags[:5]]
    clean_tags_str = " ".join(clean_tags_list)
    
    tag_html = f"<div style='margin-top: 40px; padding-top: 18px; border-top: 1px solid #eaecee; color: #2980b9; font-weight: bold; font-size: 0.95em; word-spacing: 5px;'>{clean_tags_str}</div>"
    final_html += tag_html

    return final_html

# 기사 데이터베이스 안전 저장 함수 (Commit 보장)
def save_article_to_db(category, title, content, image_url, image_author):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO articles (category, title, content, image_url, image_author) VALUES (?, ?, ?, ?, ?)", 
        (category, title, content, image_url, image_author)
    )
    conn.commit()
    conn.close()

# 1. 자동 발행 함수
def generate_ai_article(category_name):
    prompts = {
        "AI/테크": ("AI/테크", "최근 주목받는 AI 기술과 IT 혁신 트렌드에 대한 흥미롭고 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 단락은 깔끔하게 여러 개로 나누고, 소제목 앞에는 반드시 '### ' 기호를 붙여줘. 마크다운 기호(-, *, _)는 절대 쓰지 마. 마지막 줄에는 검색용 해시태그 5개를 #인공지능 #테크 형태로 공백을 두고 붙여줘.", "technology"),
        "경제/주식": ("경제/주식", "최근 주식 시장과 경제 동향, 투자 인사이트에 대한 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 단락은 깔끔하게 여러 개로 나누고, 소제목 앞에는 반드시 '### ' 기호를 붙여줘. 마크다운 기호(-, *, _)는 절대 쓰지 마. 마지막 줄에는 검색용 해시태그 5개를 #주식투자 #경제동향 형태로 공백을 두고 붙여줘.", "stock market economy"),
        "세상이야기": ("세상이야기", "우리 주변의 따뜻한 세상 이야기나 일상 속 감동적인 트렌드에 대한 뉴스 기사를 작성해줘. 단락은 깔끔하게 여러 개로 나누고, 소제목 앞에는 반드시 '### ' 기호를 붙여줘. 마크다운 기호(-, *, _)는 절대 쓰지 마. 마지막 줄에는 검색용 해시태그 5개를 #세상이야기 #라이프 형태로 공백을 두고 붙여줘.", "warm lifestyle people"),
        "시니어/복지": ("시니어/복지", "시니어 세대를 위한 유용한 복지 정책, 건강 관리, 은퇴 후 삶의 지혜에 대한 전문적인 뉴스 기사를 작성해줘. 단락은 깔끔하게 여러 개로 나누고, 소제목 앞에는 반드시 '### ' 기호를 붙여줘. 마크다운 기호(-, *, _)는 절대 쓰지 마. 마지막 줄에는 검색용 해시태그 5개를 #시니어복지 #은퇴설계 형태로 공백을 두고 붙여줘.", "senior elderly care")
    }
    
    cat_info = prompts.get(category_name, ("종합", "최신 트렌드에 대한 유익한 뉴스 기사를 작성해줘.", "news"))
    prompt = cat_info[1]
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        raw_content = response.text.strip()
    except Exception as e:
        raw_content = f"기사 생성 오류: {e}"

    keyword_map = {"AI/테크": "technology", "경제/주식": "stock market economy", "세상이야기": "warm lifestyle people", "시니어/복지": "senior elderly care"}
    img_keyword = keyword_map.get(category_name, "news")
    
    img_url, author_name = fetch_single_image(img_keyword)
    
    # 첫 줄(제목)을 깔끔하게 분리하고 본문에서 확실하게 도려내어 중복 노출 원천 차단
    split_lines = raw_content.split("\n", 1)
    if len(split_lines) > 1:
        art_title = split_lines[0].replace("#", "").replace("제목:", "").replace("**", "").strip()
        body_content = split_lines[1].strip()
    else:
        art_title = f"{category_name} 소식"
        body_content = raw_content
    
    formatted_content = clean_and_format_content(body_content, category_name)
    save_article_to_db(category_name, art_title, formatted_content, img_url, author_name)

def scheduled_job():
    categories = ["AI/테크", "경제/주식", "세상이야기", "시니어/복지"]
    target_cat = random.choice(categories)
    generate_ai_article(target_cat)

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_job, 'interval', hours=6)
scheduler.start()

# 메인 홈페이지
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
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 850px; margin: 40px auto; padding: 20px; background: #f4f6f7; color: #333; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #2980b9; padding-bottom: 15px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            h1 {{ color: #2c3e50; margin: 0; font-size: 1.6em; }}
            .admin-link {{ display: inline-block; padding: 8px 16px; background: #2980b9; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 14px; }}
            .admin-link:hover {{ background: #1f618d; }}
            
            .nav-tabs {{ display: flex; gap: 10px; margin: 25px 0; flex-wrap: wrap; }}
            .tab-item {{ padding: 8px 18px; background: #e2e8f0; color: #475569; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 14px; transition: 0.2s; }}
            .tab-item:hover, .tab-item.active {{ background: #2980b9; color: white; }}

            .article {{ background: white; padding: 35px; margin-bottom: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); position: relative; }}
            .badge {{ display: inline-block; padding: 4px 12px; background: #ebf5fb; color: #2980b9; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-bottom: 10px; }}
            .article h2 {{ margin-top: 5px; color: #2c3e50; font-size: 1.5em; line-height: 1.4; }}
            .date {{ font-size: 0.85em; color: #888; margin-bottom: 20px; }}
            
            .article-img {{ width: 100%; max-height: 450px; object-fit: cover; border-radius: 8px; margin-bottom: 8px; }}
            .img-source {{ font-size: 0.8em; color: #777; margin-bottom: 25px; font-style: italic; }}
            
            .content {{ line-height: 1.85; font-size: 1.08em; color: #2c3e50; }}
            
            .btn-group {{ position: absolute; top: 35px; right: 35px; display: flex; gap: 6px; }}
            .edit-btn {{ background: #f39c12; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; text-decoration: none; font-weight: bold; }}
            .edit-btn:hover {{ background: #d68910; }}
            .delete-btn {{ background: #e74c3c; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; text-decoration: none; font-weight: bold; }}
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
            source_tag = f"<div class='img-source'>📷 Photo by {art['image_author']} / Unsplash</div>" if art['image_author'] else ""
            
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

# 관리자 페이지
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

        <div class="box" style="border-top: 5px solid #8e44ad;">
            <h3>✨ 3. 하단: AI 프롬프트 확장 발행 (신문 스타일 자동 적용)</h3>
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
                <button type="submit" class="ai-expand-btn">🪄 명품 신문 스타일 기사 발행하기</button>
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
    img_url, author_name = fetch_single_image(keyword)
    
    clean_title = title.replace('**', '').replace('*', '').strip()
    formatted_content = "".join([f"<p style='margin-bottom: 16px; text-align: justify;'>{p}</p>" for p in content.split('\n') if p.strip()])

    save_article_to_db(category, clean_title, formatted_content, img_url, author_name)
    return RedirectResponse(url="/", status_code=303)

@app.post("/admin/create-ai-expand")
def create_ai_expand(category: str = Form(...), title: str = Form(...), prompt: str = Form(...)):
    system_directive = (
        "당신은 전문 수석 뉴스 기자입니다. "
        "사용자가 제공한 [기사 제목]과 [작성 요청사항/메모]를 바탕으로, "
        "독자들이 읽기 편하도록 여러 개의 명확한 단락과 깔끔한 소제목(반드시 ### 소제목 형태)을 포함하여 풍성하고 상세한 SEO 최적화 뉴스 기사 본문을 작성해 주세요. "
        "마크다운 특수기호(-, *, _)는 절대 사용하지 말고 오직 자연스러운 문장과 ### 소제목만 사용해 주세요. "
        "마지막 줄에는 반드시 검색에 유용한 해시태그 5개를 #인공지능 #테크 형태로 공백을 두고 포함해 주세요."
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
    
    img_url, author_name = fetch_single_image(keyword)
    clean_title = title.replace('**', '').replace('*', '').strip()
    final_content = clean_and_format_content(final_content, category)

    save_article_to_db(category, clean_title, final_content, img_url, author_name)
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
                    <option value="시니어/복지" {"selected" if art[1]=="시니어/복지" else ""}>시니어/복지</option>
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
    clean_title = title.replace('**', '').replace('*', '').strip()
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE articles SET category = ?, title = ?, content = ? WHERE id = ?", (category, clean_title, content, article_id))
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
