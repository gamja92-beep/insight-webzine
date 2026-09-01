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

    fallback_title = topic
    fallback_summary = f"1. {topic} 관련 핵심 내용 요약\n2. 분야별 세부 기준 및 단계별 실행 요령\n3. 시니어 독자를 위한 전문가 핵심 권고사항"
    fallback_content = f"""
    <h2>1. {topic} - 핵심 배경과 중요성</h2>
    <p>{topic}에 대해 반드시 알아두어야 할 실전 지침과 필수 기준을 안내해 드립니다.</p>
    <h2>2. 단계별 실천 및 점검 절차</h2>
    <ol>
        <li>현재 본인의 적용 대상 여부와 기준 요건을 정확히 검토합니다.</li>
        <li>필요한 준비 사항 및 공식 확인 창구를 파악합니다.</li>
        <li>정확한 절차에 따라 순서대로 진행하여 불이익을 방지합니다.</li>
    </ol>
    <h2>3. 전문가 주의사항 및 실전 꿀팁</h2>
    <ul>
        <li>공식 공고나 지침이 변경될 수 있으므로 정기적으로 확인하시기 바랍니다.</li>
        <li>출처가 불분명한 정보에 주의하시고 공식 기관을 통해 교차 확인하세요.</li>
    </ul>
    """

    if not api_key:
        return fallback_title, fallback_summary, fallback_content

    prompt = f"""
당신은 5060 시니어 전문 웹진의 수석 에디터입니다.
주제: "{topic}" (카테고리: {category})

시니어 독자가 즉시 이해하고 실천할 수 있는 1,800자 이상의 고품질 실전 가이드 기사를 작성해 주세요.
반드시 주어진 주제("{topic}")에 들어맞는 전문적인 내용만 작성하고, 무관한 다른 주제의 내용은 일절 섞지 마십시오.

기사 본문은 HTML 태그(<h2>, <p>, <ol>, <ul>, <table> 등)를 활용하여 가독성 높게 구성하세요.

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "title": "{topic}",
  "summary": "1. 요약 첫 번째\\n2. 요약 두 번째\\n3. 요약 세 번째",
  "content": "<h2>1. ...</h2><p>...</p><h2>2. ...</h2>..."
}}
"""

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash"
    ]

    for model_name in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3
                }
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
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
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

def save_article_direct(category: str, topic: str):
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
        body { background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; color: #1e293b; margin: 0; padding: 0; }
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
    return HTMLResponse(BASE_HTML.replace("__TITLE__", title).replace("__BODY__", body))

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
