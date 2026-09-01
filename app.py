import os
import sqlite3
import json
import urllib.request
import urllib.error
from datetime import datetime

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

app = FastAPI()
ADMIN_PW = "admin1234"

def get_db():
    conn = sqlite3.connect("webzine.db", timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            cat_slug TEXT DEFAULT 'welfare',
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0
        )
    """)
    for col, definition in [("cat_slug", "TEXT DEFAULT 'welfare'"), ("views", "INTEGER DEFAULT 0"), ("likes", "INTEGER DEFAULT 0")]:
        try:
            c.execute("ALTER TABLE articles ADD COLUMN " + col + " " + definition)
        except Exception:
            pass
    conn.commit()
    conn.close()

init_db()

def get_cat_slug(category):
    if "복지" in category or "지원" in category:
        return "welfare"
    elif "경제" in category or "세무" in category:
        return "economy"
    elif "건강" in category or "식품" in category:
        return "health"
    return "culture"

def call_gemini_api(category: str, topic: str):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    # API 키가 없을 때의 기본 가이드
    fallback_title = topic
    fallback_summary = f"1. {topic}에 대한 핵심 요약 정보.\n2. 세부 기준 및 절차 안내.\n3. 필수 주의사항."
    fallback_content = f"""
    <h2>1. {topic} - 개요 및 필요성</h2>
    <p>{topic}에 대한 상세 가이드입니다.</p>
    """

    if not api_key:
        return fallback_title, fallback_summary, fallback_content

    prompt = f"""
당신은 5060 시니어 전문 웹진의 수석 에디터입니다.
주제: "{topic}" (카테고리: {category})

입력된 주제("{topic}")에 정확히 부합하는 1,800자 이상의 고품질 실전 가이드 기사를 작성해 주세요. 
절대 엉뚱한 복지 제도나 관련 없는 내용을 섞지 말고, 오직 주제("{topic}")의 내용만 심층적으로 다루어 주십시오.

[필수 HTML 구조]
- <h2>1. {topic} - 주요 배경과 핵심 내용</h2>
- <h2>2. 상세 기준 및 주요 내용 요약</h2> (HTML <table> 표 활용하여 해당 주제에 맞는 항목 작성)
- <h2>3. 단계별 실전 절차 및 실행 방법</h2> (<ol> 목록)
- <h2>4. 전문가 주의사항 및 핵심 팁</h2> (<ul> 목록)

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "title": "{topic}",
  "summary": "1. 첫 번째 핵심 요약\\n2. 두 번째 핵심 요약\\n3. 세 번째 핵심 요약",
  "content": "<h2>1. ...</h2><p>...</p><table>...</table>..."
}}
"""

    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]

    for model_name in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                if raw_text.startswith("```"):
                    lines = raw_text.splitlines()
                    if lines[0].startswith("```"): lines = lines[1:]
                    if lines and lines[-1].startswith("```"): lines = lines[:-1]
                    raw_text = "\n".join(lines).strip()

                data = json.loads(raw_text)
                title = data.get("title", topic)
                summary = data.get("summary", fallback_summary)
                content = data.get("content", fallback_content)
                if content and len(content) > 100:
                    return title, summary, content
        except Exception:
            continue

    return fallback_title, fallback_summary, fallback_content

def save_article_secure(category: str, topic: str):
    cat_slug = get_cat_slug(category)
    title, summary, content = call_gemini_api(category, topic)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO articles (title, category, cat_slug, summary, content, created_at, views, likes)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0)
    """, (title, category, cat_slug, summary, content, now))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

BASE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__ - 인사이트 데일리</title>
    <link rel="stylesheet" href="[https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css](https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css)">
    <link rel="stylesheet" href="[https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css](https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css)">
    <style>
        body { background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; margin: 0; padding: 0; }
        .hero { background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%); color: #ffffff; padding: 45px 0; margin-bottom: 30px; text-align: center; }
        .cat-btn { font-size: 0.92rem; font-weight: 600; padding: 7px 16px; border-radius: 20px; text-decoration: none; margin: 3px; color: #334155; background: #ffffff; border: 1px solid #cbd5e1; display: inline-block; }
        .cat-btn.active, .cat-btn:hover { background: #1e3a8a; color: #ffffff; border-color: #1e3a8a; }
        .card-art { border-radius: 12px; border: 1px solid #e2e8f0; background: #ffffff; height: 100%; padding: 22px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
        .art-body { font-size: 1.15rem; line-height: 2.1; color: #334155; background: #ffffff; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0; }
        .art-body h2 { font-size: 1.35rem; font-weight: 700; margin-top: 2.2rem; margin-bottom: 1rem; border-left: 5px solid #2563eb; padding-left: 12px; color: #0f172a; }
        .art-body table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
        .art-body th { background: #f1f5f9; padding: 12px; font-weight: 700; border: 1px solid #cbd5e1; }
        .art-body td { border: 1px solid #e2e8f0; padding: 12px; }
        .art-body ol, .art-body ul { margin-bottom: 1.5rem; padding-left: 1.6rem; }
        .art-body li { margin-bottom: 0.5rem; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm">
        <div class="container d-flex justify-content-between align-items-center">
            <a class="navbar-brand fw-bold text-primary fs-4" href="/"><i class="fa-solid fa-newspaper me-2"></i>인사이트 데일리</a>
            <div>
                <a href="/write" class="btn btn-primary btn-sm fw-semibold me-2"><i class="fa-solid fa-pen me-1"></i>수동 기사 발행</a>
                <a href="/admin/stats" class="btn btn-outline-secondary btn-sm"><i class="fa-solid fa-chart-line me-1"></i>통계</a>
            </div>
        </div>
    </nav>
    __BODY__
    <footer class="text-center py-4 text-muted small border-top bg-white mt-5">
        <p class="mb-0">© 인사이트 데일리 웹진. All Rights Reserved. | <a href="/rss" class="text-decoration-none text-muted">RSS</a> | <a href="/sitemap.xml" class="text-decoration-none text-muted">사이트맵</a></p>
    </footer>
</body>
</html>"""

def get_badge(cat):
    colors = {"복지": "primary", "경제": "success", "건강": "danger", "문화": "purple"}
    c = "primary"
    for k, v in colors.items():
        if k in cat:
            c = v
            break
    return f'<span class="badge bg-{c}-subtle text-{c} border border-{c}-subtle px-2 py-1">{cat}</span>'

def render(title, body):
    return HTMLResponse(BASE_HTML.replace("__TITLE__", str(title or "인사이트 데일리")).replace("__BODY__", str(body or "")))

@app.get("/ping")
def ping():
    return Response(content="pong", media_type="text/plain")

@app.get("/")
def index(cat: str = ""):
    conn = get_db()
    c = conn.cursor()
    if cat:
        c.execute("SELECT * FROM articles WHERE category LIKE ? ORDER BY id DESC", ('%' + cat + '%',))
    else:
        c.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = c.fetchall()
    conn.close()

    cards_list = []
    for r in articles:
        row = dict(r)
        art_id = str(row.get('id', ''))
        art_cat = str(row.get('category', ''))
        art_date = str(row.get('created_at', ''))[:10]
        art_title = str(row.get('title', ''))
        art_sum = str(row.get('summary', ''))
        art_views = str(row.get('views', 0))

        card_html = f"""
        <div class="col-md-4 mb-4">
            <div class="card-art d-flex flex-column">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    {get_badge(art_cat)}
                    <small class="text-muted">{art_date}</small>
                </div>
                <h5 class="fw-bold mb-2">
                    <a href="/article/{art_id}" class="text-decoration-none text-dark">{art_title}</a>
                </h5>
                <p class="text-secondary small flex-grow-1" style="white-space: pre-line; line-height: 1.6;">{art_sum}</p>
                <div class="d-flex justify-content-between align-items-center pt-3 border-top mt-2">
                    <span class="text-muted small"><i class="fa-regular fa-eye me-1"></i>{art_views}회</span>
                    <a href="/article/{art_id}" class="btn btn-outline-primary btn-sm">읽기 →</a>
                </div>
            </div>
        </div>
        """
        cards_list.append(card_html)

    cards = "".join(cards_list) if cards_list else '<div class="col-12 text-center py-5 text-muted">등록된 기사가 없습니다.</div>'

    cat_nav = f"""
    <div class="d-flex justify-content-center flex-wrap mb-4">
        <a href="/" class="cat-btn {'active' if not cat else ''}">전체보기</a>
        <a href="/?cat=복지" class="cat-btn {'active' if cat == '복지' else ''}">🏛️ 정부지원·복지</a>
        <a href="/?cat=경제" class="cat-btn {'active' if cat == '경제' else ''}">📈 생활경제·재테크</a>
        <a href="/?cat=건강" class="cat-btn {'active' if cat == '건강' else ''}">🩺 시니어건강·식품</a>
        <a href="/?cat=문화" class="cat-btn {'active' if cat == '문화' else ''}">🎨 문화·힐링여행</a>
    </div>
    """

    body = f"""
    <div class="hero">
        <div class="container">
            <h1 class="fw-bold display-6 mb-2">인사이트 데일리 웹진</h1>
            <p class="mb-0 text-white-50">시니어 복지 · 실전 재테크 · 건강 심층 가이드</p>
        </div>
    </div>
    <div class="container">
        {cat_nav}
        <div class="row">
            {cards}
        </div>
    </div>
    """
    return render("홈", body)

ARTICLE_VIEW_TEMPLATE = """
<div class="container py-4" style="max-width: 840px;">
    <div class="mb-3 d-flex align-items-center gap-2">
        __BADGE__ <span class="text-muted small">__CREATED_AT__</span>
    </div>
    <h1 class="fw-bold text-dark mb-4 lh-base" style="font-size: 2rem;">__ARTICLE_TITLE__</h1>
    
    <div class="p-3 bg-white border rounded-3 d-flex align-items-center justify-content-between mb-4 shadow-sm flex-wrap gap-2">
        <div class="d-flex align-items-center gap-2">
            <button id="ttsBtn" class="btn btn-dark btn-sm fw-bold px-3 py-2 rounded-pill shadow-sm" onclick="toggleSpeech()">
                <i class="fa-solid fa-volume-high me-1 text-warning"></i> <span id="ttsText">차분한 아나운서 음성 듣기</span>
            </button>
            <small id="ttsStatus" class="text-secondary fw-semibold">차분하고 편안한 브리핑 톤</small>
        </div>
        <div class="d-flex gap-1">
            <button class="btn btn-light btn-sm border" onclick="resizeFont(1)" title="글자 확대">A+</button>
            <button class="btn btn-light btn-sm border" onclick="resizeFont(-1)" title="글자 축소">A-</button>
        </div>
    </div>

    <div class="p-3 bg-white border-start border-4 border-primary rounded-2 shadow-sm mb-4">
