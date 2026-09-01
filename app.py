import os
import sqlite3
import json
import time
import threading
import random
from datetime import datetime

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

app = FastAPI()

ADMIN_STATS_PASSWORD = "admin1234"

# Gemini API 클라이언트 초기화
client = None
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_api_key:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
except Exception as e:
    print("Gemini 초기화 오류:", e)

def get_db():
    conn = sqlite3.connect("webzine.db", timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0
        )
    """)
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN views INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN likes INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

def increase_article_view_async(article_id: int):
    def _run():
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE articles SET views = COALESCE(views, 0) + 1 WHERE id = ?", (article_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

AUTO_TOPIC_POOL = [
    ("정부 지원금/복지 혜택", "2026년 시니어 임플란트 및 틀니 건강보험 적용 혜택과 본인부담금 완벽 가이드"),
    ("문화/예술", "시니어를 위한 전국 힐링 무장애 나눔길 베스트 5 및 코스별 대중교통 상세 안내"),
    ("생활 경제/세무 상식", "2026년 기초연금 수급자격 및 소득인정액 모의계산법과 인상 혜택 총정리"),
    ("시니어 건강/식품", "시니어 무릎 관절염 예방 걷기 운동법과 연골 부담 줄이는 생활 수칙"),
    ("정부 지원금/복지 혜택", "문화누리카드 지원금 100% 알찬 활용법과 KTX 기차여행 할인 연계 꿀팁"),
    ("생활 경제/세무 상식", "주택연금 가입조건과 내 집으로 받는 평생 월 지급금 수령액 비교 분석"),
    ("시니어 건강/식품", "혈관 나이를 10년 젊게 만드는 아침 식습관과 필수 항산화 식단 가이드"),
    ("문화/예술", "국립자연휴양림 시니어 치유 숲 프로그램 예약 방법과 입장료 감면 혜택")
]

def make_article_data(category: str, topic: str):
    title = topic
    summary = "1. 실생활에 즉시 도움 되는 심층 핵심 정보. 2. 지원 대상, 신청처 및 구체적인 혜택 총정리. 3. 꼭 알아두어야 할 주의사항과 실전 꿀팁 수록."
    
    content = """
    <h2>1. 주요 배경과 핵심 정보</h2>
    <p>""" + topic + """에 대해 독자 여러분이 반드시 알아야 할 핵심 정보를 상세히 안내해 드립니다. 본 가이드는 실생활에서 즉시 활용할 수 있는 알찬 지침을 담고 있습니다.</p>
    <h2>2. 한눈에 비교하는 기준 및 혜택 요약</h2>
    <table class="table table-bordered my-3">
        <thead class="table-light">
            <tr><th>구분</th><th>주요 지원 내용</th><th>지원 대상 및 기준</th></tr>
        </thead>
        <tbody>
            <tr><td>기본 지원</td><td>맞춤형 혜택 및 본인부담금 대폭 감면</td><td>만 65세 이상 및 해당 가구</td></tr>
            <tr><td>신청 방법</td><td>정부24 온라인 신청 또는 관할 주민센터 방문</td><td>신분증 및 구비서류 지참</td></tr>
        </tbody>
    </table>
    <h2>3. 실패 없는 실전 신청 절차</h2>
    <ol>
        <li>신청 자격 및 해당 연도 소득인정액 기준을 확인합니다.</li>
        <li>필수 지참 서류를 구비하여 관할 기관 또는 공식 웹사이트에 접수합니다.</li>
        <li>심사 통과 후 혜택을 수령하고 변동 사항을 주기적으로 확인합니다.</li>
    </ol>
    <h2>4. 전문가 주의사항 및 알짜 꿀팁</h2>
    <ul>
        <li>신청 기한을 넘기면 소급 지원이 어려울 수 있으니 사전 신청 기간을 반드시 확인하세요.</li>
        <li>기타 유사 복지 제도와의 중복 수혜 가능 여부를 전담 고객센터에 사전 문의하시기 바랍니다.</li>
    </ul>
    <h2>5. 자주 묻는 질문 (FAQ)</h2>
    <p><strong>Q. 본인 방문이 어려울 때 대리 신청이 가능한가요?</strong><br>A. 네, 배우자나 직계가족이 위임장과 신분증, 가족관계증명서를 지참하시면 가능합니다.</p>
    """

    if client:
        prompt = """
        당신은 5060 시니어 전문 웹진의 수석 에디터입니다.
        아래 [주제]와 [카테고리]에 대해 독자가 5분 이상 깊이 읽을 '초고품질 심층 가이드 기사'를 작성해 주세요.

        [주제]: """ + topic + """
        [카테고리]: """ + category + """

        [작성 가이드라인]:
        1. 분량: 한글 1,500자 ~ 2,000자 이상의 매우 상세하고 유익한 내용.
        2. 기사 구성 (HTML 태그 필수 적용):
           - [제목]: 신뢰감 있고 매력적인 고품격 헤드라인
           - [요약]: 핵심 3줄 브리핑 (1., 2., 3. 번호 포함)
           - [본문]: <h2>1. 주요 배경과 핵심 정보</h2>, <h2>2. 한눈에 비교하는 기준 및 혜택 요약</h2> (HTML <table> 표 포함), <h2>3. 실패 없는 실전 신청 절차</h2> (<ol> 리스트), <h2>4. 전문가 주의사항 및 알짜 꿀팁</h2> (<ul> 리스트), <h2>5. 자주 묻는 질문 (FAQ)</h2> (질문 3가지와 명쾌한 답변)
        3. 어조: 뉴스 아나운서처럼 정중하고 신뢰를 주는 어조 ('~합니다', '~하시기 바랍니다').

        [출력 JSON 규격]:
        {
            "title": "기사 제목",
            "summary": "1. ... 2. ... 3. ...",
            "content": "<h2>1. ...</h2><p>...</p><table>...</table><h2>3. ...</h2><ol>...</ol><h2>4. ...</h2><ul>...</ul><h2>5. 자주 묻는 질문 (FAQ)</h2><p><strong>Q1...</strong></p><p>A1...</p>"
        }
        """
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=dict(response_mime_type="application/json")
            )
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.endswith("```"):
                raw = raw[:-3]
            data = json.loads(raw.strip())
            title = data.get("title", title)
            summary = data.get("summary", summary)
            content = data.get("content", content)
        except Exception as e:
            print("Gemini 생성 예외:", e)

    return title, category, summary, content

def generate_and_save_article(category="", topic=""):
    if not category or not topic:
        chosen = random.choice(AUTO_TOPIC_POOL)
        category, topic = chosen[0], chosen[1]

    title, category, summary, content = make_article_data(category, topic)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO articles (title, category, summary, content, created_at, views, likes)
        VALUES (?, ?, ?, ?, ?, 0, 0)
    """, (title, category, summary, content, now))
    inserted_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print("[" + now + "] 기사 발행 완료 (ID: " + str(inserted_id) + "): " + title)
    return inserted_id

def auto_article_scheduler():
    time.sleep(20)
    generate_and_save_article()
    while True:
        time.sleep(21600)
        generate_and_save_article()

threading.Thread(target=auto_article_scheduler, daemon=True).start()

HTML_BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta name="naver-site-verification" content="2be1d8c699f2db6d04ee4bbe598876b754cf1c10" />
    <meta name="google-site-verification" content="FuUKAJVoYVh_WbGkmCXJX2YwcIayUpBDGpBwLu7vlkU" />
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__PAGE_TITLE__ - 인사이트 데일리</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Pretendard", sans-serif; color: #1e293b; }
        .navbar-brand { font-weight: 800; color: #1e3a8a !important; font-size: 1.35rem; }
        .hero-section { background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #2563eb 100%); color: white; padding: 42px 0; margin-bottom: 25px; }
        
        .cat-nav-btn { font-size: 0.95rem; font-weight: 600; padding: 8px 16px; border-radius: 30px; margin: 3px; text-decoration: none; display: inline-block; color: #475569; background: #ffffff; border: 1px solid #e2e8f0; transition: all 0.2s; }
        .cat-nav-btn:hover, .cat-nav-btn.active { background: #1e3a8a; color: #ffffff; border-color: #1e3a8a; }
        
        .article-card { border: none; border-radius: 14px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; height: 100%; background: white; }
        .article-card:hover { transform: translateY(-4px); box-shadow: 0 10px 22px rgba(0,0,0,0.09); }
        
        .badge-cat-복지 { background-color: #eff6ff; color: #1d4ed8; font-weight: 600; border: 1px solid #dbeafe; }
        .badge-cat-경제 { background-color: #ecfdf5; color: #047857; font-weight: 600; border: 1px solid #a7f3d0; }
        .badge-cat-건강 { background-color: #fef2f2; color: #b91c1c; font-weight: 600; border: 1px solid #fecaca; }
        .badge-cat-문화 { background-color: #faf5ff; color: #7e22ce; font-weight: 600; border: 1px solid #e9d5ff; }
        
        .article-content { font-size: 1.16rem; line-height: 2.05; color: #334155; }
        .article-content h2 { color: #0f172a; font-weight: 800; font-size: 1.45rem; margin-top: 2.6rem; margin-bottom: 1.2rem; border-left: 6px solid #2563eb; padding-left: 14px; }
        .article-content table { width: 100%; margin: 1.8rem 0; border-collapse: separate; border-spacing: 0; background: white; border-radius: 10px; overflow: hidden; border: 1px solid #e2e8f0; }
        .article-content th { background: #f1f5f9; padding: 14px; font-weight: 700; text-align: center; border-bottom: 2px solid #cbd5e1; }
        .article-content td { padding: 13px 15px; border-bottom: 1px solid #f1f5f9; font-size: 1.05rem; }
        .article-content ul, .article-content ol { margin-bottom: 1.8rem; padding-left: 1.8rem; }
        .article-content li { margin-bottom: 0.6rem; }

        .tts-player-box { background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-radius: 14px; padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
        .toc-box { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px 24px; margin-bottom: 2rem; }
        .toc-box a { color: #4b5563; text-decoration: none; font-weight: 600; }
        .toc-box a:hover { color: #2563eb; text-decoration: underline; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm sticky-top">
        <div class="container">
            <a class="navbar-brand" href="/"><i class="fa-solid fa-newspaper me-2 text-primary"></i>인사이트 데일리</a>
            <div class="d-flex align-items-center">
                <span class="badge bg-success-subtle text-success border border-success-subtle me-2 px-2 py-1"><i class="fa-solid fa-circle-dot me-1"></i>하루 4회 무인 자동 발행</span>
                <a href="/write" class="btn btn-primary btn-sm me-2 fw-semibold"><i class="fa-solid fa-plus me-1"></i>수동 기사 발행</a>
                <a href="/admin/stats" class="btn btn-outline-secondary btn-sm"><i class="fa-solid fa-chart-line me-1"></i>관리자 통계</a>
            </div>
        </div>
    </nav>
    __MAIN_CONTENT__
    <footer class="bg-white border-top py-4 mt-5 text-center text-muted small">
        <div class="container">
            <p class="mb-1 fw-semibold text-secondary">© 인사이트 데일리 웹진. All Rights Reserved.</p>
            <p class="mb-0"><a href="/rss" class="text-decoration-none text-muted me-3">RSS 피드</a> <a href="/sitemap.xml" class="text-decoration-none text-muted">사이트맵</a></p>
        </div>
    </footer>
</body>
</html>"""

def get_cat_badge(cat_name):
    if "복지" in cat_name or "지원" in cat_name:
        return '<span class="badge badge-cat-복지 px-2 py-1">🏛️ ' + cat_name + '</span>'
    elif "경제" in cat_name or "세무" in cat_name:
        return '<span class="badge badge-cat-경제 px-2 py-1">📈 ' + cat_name + '</span>'
    elif "건강" in cat_name or "식품" in cat_name:
        return '<span class="badge badge-cat-건강 px-2 py-1">🩺 ' + cat_name + '</span>'
    else:
        return '<span class="badge badge-cat-문화 px-2 py-1">🎨 ' + cat_name + '</span>'

def render_html(title, content):
    page = HTML_BASE_TEMPLATE.replace("__PAGE_TITLE__", title).replace("__MAIN_CONTENT__", content)
    return HTMLResponse(content=page)

@app.get("/")
def index(cat: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    if cat:
        cursor.execute("SELECT id, title, category, summary, created_at, COALESCE(views, 0) as views FROM articles WHERE category LIKE ? ORDER BY id DESC", ('%' + cat + '%',))
    else:
        cursor.execute("SELECT id, title, category, summary, created_at, COALESCE(views, 0) as views FROM articles ORDER BY id DESC")
    articles = cursor.fetchall()
    conn.close()

    cards_html = ""
    for row in articles:
        art_id = str(row['id'])
        art_title = str(row['title'])
        art_cat = str(row['category'])
        art_sum = str(row['summary'])
        art_date = str(row['created_at'])[:10]
        art_views = str(row['views'])
        badge_html = get_cat_badge(art_cat)

        cards_html += """
        <div class="col-md-4 mb-4">
            <div class="card article-card p-4 d-flex flex-column">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    """ + badge_html + """
                    <small class="text-muted"><i class="fa-regular fa-clock me-1"></i>""" + art_date + """</small>
                </div>
                <h5 class="card-title fw-bold mb-3 lh-base">
                    <a href="/article/""" + art_id + """" class="text-decoration-none text-dark">""" + art_title + """</a>
                </h5>
                <p class="card-text text-secondary small flex-grow-1" style="line-height: 1.65;">""" + art_sum + """</p>
                <div class="mt-3 pt-3 border-top d-flex justify-content-between align-items-center">
                    <span class="text-muted small"><i class="fa-regular fa-eye me-1"></i>조회 """ + art_views + """회</span>
                    <a href="/article/""" + art_id + """" class="btn btn-sm btn-outline-primary fw-semibold">기사 읽기 →</a>
                </div>
            </div>
        </div>
        """

    if not cards_html:
        cards_html = '<div class="col-12 text-center py-5 text-muted">등록된 기사가 없습니다. 상단의 수동 기사 발행을 눌러보세요.</div>'

    cat_nav = """
    <div class="d-flex justify-content-center flex-wrap mb-4">
        <a href="/" class="cat-nav-btn """ + ('active' if not cat else '') + """">전체보기</a>
        <a href="/?cat=복지" class="cat-nav-btn """ + ('active' if cat == '복지' else '') + """">🏛️ 정부지원·복지</a>
        <a href="/?cat=경제" class="cat-nav-btn """ + ('active' if cat == '경제' else '') + """">📈 생활경제·재테크</a>
        <a href="/?cat=건강" class="cat-nav-btn """ + ('active' if cat == '건강' else '') + """">🩺 시니어건강·식품</a>
        <a href="/?cat=문화" class="cat-nav-btn """ + ('active' if cat == '문화' else '') + """">🎨 문화·힐링여행</a>
    </div>
    """

    body = """
    <div class="hero-section text-center">
        <div class="container">
            <h1 class="fw-bold mb-2 display-6">인사이트 데일리 웹진</h1>
            <p class="lead mb-0 text-white-50">시니어 복지 혜택 · 실전 생활재테크 · 웰에이징 건강 심층 가이드</p>
        </div>
    </div>
    <div class="container">
        """ + cat_nav + """
        <div class="row">
            """ + cards_html + """
        </div>
    </div>
    """
    return render_html("메인", body)

@app.get("/article/{article_id}")
def view_article(article_id: int):
    # 조회수는 백그라운드에서 비동기로 올려 딜레이(0.1초 전환)를 없앰
    increase_article_view_async(article_id)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return HTMLResponse("존재하지 않는 기사입니다. <a href='/'>메인으로</a>", status_code=404)

    cursor.execute("SELECT id, title, category, created_at FROM articles WHERE id != ? AND category = ? ORDER BY id DESC LIMIT 3", (article_id, row['category']))
    related_articles = cursor.fetchall()
    if len(related_articles) < 3:
        cursor.execute("SELECT id, title, category, created_at FROM articles WHERE id != ? ORDER BY id DESC LIMIT 3", (article_id,))
        related_articles = cursor.fetchall()
    conn.close()

    related_html = ""
    for rel in related_articles:
        rel_id = str(rel['id'])
        rel_title = str(rel['title'])
        rel_cat = str(rel['category'])
        rel_date = str(rel['created_at'])[:10]
        badge_html = get_cat_badge(rel_cat)
        related_html += """
        <div class="col-md-4 mb-3">
            <div class="card h-100 p-3 border-0 shadow-sm rounded-3">
                <div class="mb-2">""" + badge_html + """</div>
                <h6 class="fw-bold"><a href="/article/""" + rel_id + """" class="text-decoration-none text-dark">""" + rel_title + """</a></h6>
                <small class="text-muted mt-auto pt-2">""" + rel_date + """</small>
            </div>
        </div>
        """

    content_len = len(row['content'])
    est_minutes = max(2, round(content_len / 450))
    body_html = str(row['content'])
    likes_count = str(row['likes']) if 'likes' in row.keys() and row['likes'] is not None else "0"
    badge_html = get_cat_badge(str(row['category']))

    body = """
    <div class="container py-5" style="max-width: 860px;">
        <div class="mb-4">
            <div class="d-flex gap-2 align-items-center mb-2">
                """ + badge_html + """
                <span class="text-muted small"><i class="fa-regular fa-clock me-1"></i>""" + str(row['created_at']) + """</span>
                <span class="badge bg-light text-dark border ms-auto"><i class="fa-solid fa-book-open-reader me-1 text-primary"></i>약 """ + str(est_minutes) + """분 분량</span>
            </div>
            <h1 class="fw-bold text-dark lh-base my-3" style="font-size: 2.15rem; letter-spacing: -0.03em;">""" + str(row['title']) + """</h1>
        </div>

        <div class="tts-player-box mb-4 shadow-sm">
            <div class="d-flex align-items-center gap-3 flex-wrap">
                <button id="ttsPlayBtn" class="btn btn-primary px-3 py-2 fw-bold rounded-pill shadow-sm" onclick="toggleTTS()">
                    <i class="fa-solid fa-circle-play me-1"></i> <span id="ttsBtnText">뉴스 아나운서 음성 듣기</span>
                </button>
                <div class="btn-group btn-group-sm" role="group">
                    <button type="button" class="btn btn-outline-primary" onclick="setSpeed(0.85)">0.8x</button>
                    <button type="button" class="btn btn-primary active" id="speedNormal" onclick="setSpeed(1.0)">1.0x</button>
                    <button type="button" class="btn btn-outline-primary" onclick="setSpeed(1.2)">1.2x</button>
                </div>
                <small id="ttsStatus" class="text-secondary fw-semibold">편안하고 또렷한 음성으로 낭독합니다.</small>
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="text-muted small fw-semibold">글자:</span>
                <button class="btn btn-light btn-sm border rounded-circle" onclick="changeFontSize(1)" title="확대"><i class="fa-solid fa-plus"></i></button>
                <button class="btn btn-light btn-sm border rounded-circle" onclick="changeFontSize(-1)" title="축소"><i class="fa-solid fa-minus"></i></button>
            </div>
        </div>

        <div class="p-4 mb-4 bg-white rounded-4 border-start border-5 border-primary shadow-sm">
            <h6 class="fw-bold text-primary mb-2"><i class="fa-solid fa-bolt me-2"></i>핵심 3줄 브리핑</h6>
            <div class="text-secondary fw-medium lh-base" style="font-size: 1.06rem;">""" + str(row['summary']) + """</div>
        </div>

        <div class="toc-box">
            <div class="fw-bold text-dark mb-2"><i class="fa-solid fa-list-check me-2 text-primary"></i>이 기사의 주요 목차</div>
            <ul id="tocList" class="mb-0 ps-3 small" style="line-height: 1.9;"></ul>
        </div>

        <article id="articleBody" class="article-content bg-white p-4 p-md-5 rounded-4 shadow-sm mb-5">
            """ + body_html + """
        </article>

        <div class="d-flex justify-content-between align-items-center bg-white p-3 p-md-4 rounded-4 shadow-sm mb-5 border">
            <button id="likeBtn" class="btn btn-outline-danger btn-sm px-3 fw-bold rounded-pill" onclick="likePost()">
                <i class="fa-solid fa-heart me-1"></i> 유익해요 <span id="likeCount">""" + likes_count + """</span>
            </button>
            <div class="d-flex gap-2">
                <button class="btn btn-outline-secondary btn-sm rounded-pill" onclick="copyCurrentUrl()"><i class="fa-solid fa-link me-1"></i>기사 링크 복사</button>
                <a href="/" class="btn btn-primary btn-sm rounded-pill px-3"><i class="fa-solid fa-list me-1"></i>목록으로</a>
            </div>
        </div>

        <div class="mt-5 pt-3">
            <h4 class="fw-bold mb-3 text-dark"><i class="fa-solid fa-newspaper me-2 text-primary"></i>함께 읽으면 유익한 추천 가이드</h4>
            <div class="row">
                """ + (related_html if related_html else '<p class="text-muted small">추천 기사가 준비 중입니다.</p>') + """
            </div>
        </div>
    </div>

    <script>
        window.addEventListener('DOMContentLoaded', function() {
            var h2s = document.querySelectorAll('#articleBody h2');
            var tocList = document.getElementById('tocList');
            if (h2s.length === 0) {
                if (document.querySelector('.toc-box')) document.querySelector('.toc-box').style.display = 'none';
                return;
            }
            h2s.forEach(function(h2, index) {
                h2.id = 'section-' + index;
                var li = document.createElement('li');
                var a = document.createElement('a');
                a.href = '#section-' + index;
                a.innerText = h2.innerText;
                li.appendChild(a);
                tocList.appendChild(li);
            });
        });

        var isSpeaking = false;
        var speechSynth = window.speechSynthesis;
        var currentRate = 0.95;
        var selectedVoice = null;

        function findBestKoreanVoice() {
            if (!speechSynth) return null;
            var voices = speechSynth.getVoices();
            for (var i = 0; i < voices.length; i++) {
                if (voices[i].lang.indexOf('ko') !== -1 || voices[i].lang.indexOf('KO') !== -1) {
                    if (voices[i].name.indexOf('Google') !== -1 || voices[i].name.indexOf('Natural') !== -1 || voices[i].name.indexOf('Online') !== -1) {
                        return voices[i];
                    }
                }
            }
            for (var j = 0; j < voices.length; j++) {
                if (voices[j].lang.indexOf('ko') !== -1 || voices[j].lang.indexOf('KO') !== -1) return voices[j];
            }
            return null;
        }

        if (speechSynth && speechSynth.onvoiceschanged !== undefined) {
            speechSynth.onvoiceschanged = function() {
                selectedVoice = findBestKoreanVoice();
            };
        }

        function setSpeed(speed) {
            currentRate = speed;
            if (isSpeaking) {
                toggleTTS();
                toggleTTS();
            }
        }

        function toggleTTS() {
            if (!speechSynth) {
                alert("음성 재생을 지원하지 않는 브라우저입니다.");
                return;
            }

            if (isSpeaking) {
                speechSynth.cancel();
                isSpeaking = false;
                document.getElementById('ttsBtnText').innerText = "뉴스 아나운서 음성 듣기";
                document.getElementById('ttsPlayBtn').className = "btn btn-primary px-3 py-2 fw-bold rounded-pill shadow-sm";
                document.getElementById('ttsStatus').innerText = "재생이 정지되었습니다.";
            } else {
                var rawText = document.getElementById('articleBody').innerText;
                var cleanText = rawText.replace(/\\s+/g, ' ').trim();
                
                var utterance = new SpeechSynthesisUtterance(cleanText);
                utterance.lang = 'ko-KR';
                utterance.rate = currentRate;
                utterance.pitch = 1.0;
                
                if (!selectedVoice) selectedVoice = findBestKoreanVoice();
                if (selectedVoice) utterance.voice = selectedVoice;

                utterance.onend = function() {
                    isSpeaking = false;
                    document.getElementById('ttsBtnText').innerText = "기사 다시 듣기";
                    document.getElementById('ttsPlayBtn').className = "btn btn-primary px-3 py-2 fw-bold rounded-pill shadow-sm";
                    document.getElementById('ttsStatus').innerText = "낭독이 완료되었습니다.";
                };

                speechSynth.speak(utterance);
                isSpeaking = true;
                document.getElementById('ttsBtnText').innerText = "음성 일시정지";
                document.getElementById('ttsPlayBtn').className = "btn btn-danger px-3 py-2 fw-bold rounded-pill shadow-sm";
                document.getElementById('ttsStatus').innerText = "아나운서 톤으로 정갈하게 낭독 중입니다...";
            }
        }

        var currentSize = 1.16;
        function changeFontSize(delta) {
            currentSize = Math.max(0.95, Math.min(1.65, currentSize + (delta * 0.1)));
            document.getElementById('articleBody').style.fontSize = currentSize + 'rem';
        }

        function copyCurrentUrl() {
            navigator.clipboard.writeText(window.location.href).then(function() {
                alert("기사 링크가 복사되었습니다!");
            });
        }

        function likePost() {
            var countEl = document.getElementById('likeCount');
            var curr = parseInt(countEl.innerText) || 0;
            countEl.innerText = curr + 1;
            document.getElementById('likeBtn').className = "btn btn-danger btn-sm px-3 fw-bold rounded-pill";
        }
    </script>
    """
    return render_html(str(row['title']), body)

@app.get("/write")
def write_form():
    body = """
    <div class="container py-5" style="max-width: 760px;">
        <div class="card p-4 p-md-5 shadow-sm border-0 rounded-4">
            <h3 class="fw-bold mb-2 text-dark"><i class="fa-solid fa-plus me-2 text-primary"></i>전문가 심층 기사 수동 발행</h3>
            <p class="text-muted small mb-4">원하는 특정 주제가 있을 때 입력하시면 즉시 2,000자 이상의 심층 리포트를 작성하여 웹진에 자동 등록합니다.</p>

            <form id="writeForm" method="post" action="/write" onsubmit="showLoading()">
                <div class="mb-3">
                    <label class="form-label fw-bold">카테고리</label>
                    <select name="category" class="form-select py-2">
                        <option value="정부 지원금/복지 혜택">🏛️ 정부 지원금/복지 혜택</option>
                        <option value="생활 경제/세무 상식">📈 생활 경제/세무 상식</option>
                        <option value="시니어 건강/식품">🩺 시니어 건강/식품</option>
                        <option value="문화/예술">🎨 문화/예술</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold">기사 주제</label>
                    <input type="text" name="topic" class="form-control py-2" placeholder="예: 2026년 시니어 노인장기요양보험 등급 판정 기준 및 방문요양 혜택 총정리" required>
                </div>
                <button type="submit" id="submitBtn" class="btn btn-primary w-100 py-3 fw-bold fs-6 mt-3 shadow-sm">
                    <i class="fa-solid fa-bolt me-1"></i> 즉시 2,000자 심층 기사 작성 및 발행
                </button>
            </form>

            <div id="loadingBox" class="text-center py-4 mt-3" style="display: none;">
                <div class="spinner-border text-primary mb-3" role="status"></div>
                <h5 class="fw-bold text-dark">AI 기자가 2,000자 심층 가이드를 집필 중입니다...</h5>
                <p class="text-muted small mb-0">약 5~10초 후 완성된 기사로 바로 이동합니다. 창을 닫지 마세요.</p>
            </div>
        </div>
    </div>

    <script>
        function showLoading() {
            document.getElementById('writeForm').style.display = 'none';
            document.getElementById('loadingBox').style.display = 'block';
        }
    </script>
    """
    return render_html("기사 수동 발행", body)

@app.post("/write")
def write_submit(category: str = Form(...), topic: str = Form(...)):
    new_article_id = generate_and_save_article(category, topic)
    return RedirectResponse(url="/article/" + str(new_article_id), status_code=303)

@app.get("/sitemap.xml", response_class=Response)
def sitemap():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM articles ORDER BY id DESC")
        articles = cursor.fetchall()
        conn.close()

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        xml += '  <url><loc>https://insight-webzine.onrender.com/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        for row in articles:
            xml += '  <url><loc>https://insight-webzine.onrender.com/article/' + str(row["id"]) + '</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")
    except Exception:
        return Response(content='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://insight-webzine.onrender.com/</loc></url></urlset>', media_type="application/xml")

@app.get("/rss", response_class=Response)
def rss_feed():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, summary FROM articles ORDER BY id DESC LIMIT 30")
        articles = cursor.fetchall()
        conn.close()

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<rss version="2.0">\n<channel>\n'
        xml += '  <title>인사이트 데일리 웹진</title>\n'
        xml += '  <link>https://insight-webzine.onrender.com</link>\n'
        xml += '  <description>최신 뉴스 및 인사이트 웹진</description>\n'
        for row in articles:
            xml += '  <item>\n'
            xml += '    <title><![CDATA[' + str(row["title"]) + ']]></title>\n'
            xml += '    <link>https://insight-webzine.onrender.com/article/' + str(row["id"]) + '</link>\n'
            xml += '    <description><![CDATA[' + str(row["summary"]) + ']]></description>\n'
            xml += '  </item>\n'
        xml += '</channel>\n</rss>'
        return Response(content=xml, media_type="application/xml")
    except Exception:
        return Response(content='<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>인사이트 데일리 웹진</title><link>https://insight-webzine.onrender.com</link></channel></rss>', media_type="application/xml")

@app.get("/admin/stats")
def admin_stats(pw=""):
    if pw != ADMIN_STATS_PASSWORD:
        login_html = """
        <div class="container py-5 d-flex justify-content-center">
            <div class="card p-4 shadow-sm border-0 text-center rounded-4" style="max-width: 360px; width: 100%;">
                <h4 class="fw-bold mb-3">📊 관리자 로그인</h4>
                """ + ('<div class="alert alert-danger py-2 small mb-3">비밀번호가 일치하지 않습니다.</div>' if pw else '') + """
                <form method="get" action="/admin/stats">
                    <input type="password" name="pw" class="form-control mb-3 py-2" placeholder="비밀번호 입력" autofocus required>
                    <button type="submit" class="btn btn-primary w-100 py-2 fw-bold">통계 보기</button>
                </form>
            </div>
        </div>
        """
        return render_html("관리자 로그인", login_html)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, COALESCE(views, 0) as views, COALESCE(likes, 0) as likes, created_at FROM articles ORDER BY views DESC, id DESC")
    articles = cursor.fetchall()
    total_views = sum([row['views'] for row in articles])
    conn.close()

    rows_html = ""
    for idx, row in enumerate(articles, 1):
        badge_html = get_cat_badge(str(row['category']))
        rows_html += """
        <tr>
            <td class="text-center fw-bold text-muted">""" + str(idx) + """</td>
            <td><a href="/article/""" + str(row['id']) + """" target="_blank" class="text-decoration-none text-dark fw-semibold">""" + str(row['title']) + """</a></td>
            <td class="text-center">""" + badge_html + """</td>
            <td class="text-center text-primary fw-bold">""" + str(row['views']) + """ 회</td>
            <td class="text-center text-danger fw-bold">""" + str(row['likes']) + """ 개</td>
            <td class="text-center text-muted small">""" + str(row['created_at'])[:10] + """</td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="6" class="text-center py-4 text-muted">등록된 기사가 없습니다.</td></tr>'

    dashboard_html = """
    <div class="container py-5" style="max-width: 960px;">
        <h3 class="fw-bold mb-4">📊 기사 조회수 및 방문 통계</h3>
        <div class="row g-3 mb-4">
            <div class="col-md-6">
                <div class="card p-4 shadow-sm border-0 text-center rounded-4">
                    <div class="text-muted small mb-1">총 누적 기사 조회수</div>
                    <div class="fs-1 fw-bold text-primary">""" + str(total_views) + """ <span class="fs-6 text-muted">회</span></div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card p-4 shadow-sm border-0 text-center rounded-4">
                    <div class="text-muted small mb-1">총 발행 기사 수</div>
                    <div class="fs-1 fw-bold text-secondary">""" + str(len(articles)) + """ <span class="fs-6 text-muted">개</span></div>
                </div>
            </div>
        </div>
        <div class="card shadow-sm border-0 rounded-4 overflow-hidden">
            <table class="table table-hover mb-0 align-middle">
                <thead class="table-light">
                    <tr>
                        <th class="text-center" style="width: 60px;">순위</th>
                        <th>기사 제목</th>
                        <th class="text-center" style="width: 150px;">카테고리</th>
                        <th class="text-center" style="width: 100px;">조회수</th>
                        <th class="text-center" style="width: 90px;">좋아요</th>
                        <th class="text-center" style="width: 110px;">작성일</th>
                    </tr>
                </thead>
                <tbody>
                    """ + rows_html + """
                </tbody>
            </table>
        </div>
    </div>
    """
    return render_html("관리자 통계", dashboard_html)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
