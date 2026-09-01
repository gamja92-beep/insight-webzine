import os
import sqlite3
import json
import time
import threading
import random
from datetime import datetime

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
import uvicorn

# ======================================================
# 1. 환경 설정 및 DB 초기화
# ======================================================
app = FastAPI()

# 관리자 통계 접속 비밀번호
ADMIN_STATS_PASSWORD = "admin1234"

# Gemini API 클라이언트 초기화
gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

def get_db():
    conn = sqlite3.connect("webzine.db", check_same_thread=False)
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

def increase_article_view(article_id: int):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE articles SET views = COALESCE(views, 0) + 1 WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ======================================================
# 2. 고품격 심층 기사 자동 생성 엔진 (2,000자+ 전문 리포트)
# ======================================================
AUTO_TOPIC_POOL = [
    ("시니어/복지", "2026년 시니어 임플란트 및 틀니 건강보험 적용 혜택과 본인부담금 완벽 가이드"),
    ("문화/여행", "시니어를 위한 전국 힐링 무장애 나눔길 베스트 5 및 코스별 대중교통 상세 안내"),
    ("경제/재테크", "기초연금 수급자격 및 소득인정액 모의계산법과 2026년 인상 혜택 총정리"),
    ("건강/의학", "시니어 무릎 관절염 예방 걷기 운동법과 연골 부담 줄이는 생활 수칙"),
    ("시니어/복지", "문화누리카드 지원금 100% 알찬 활용법과 KTX 기차여행 할인 연계 꿀팁"),
    ("IT/디지털", "어르신을 위한 스마트폰 모바일 신분증 발급 및 병원 본인확인 간편 활용법"),
    ("경제/재테크", "주택연금 가입조건과 내 집으로 받는 평생 월 지급금 수령액 비교 분석"),
    ("건강/의학", "뇌세포를 깨우는 치매 예방 식습관 7가지와 일상 속 인지재활 트레이닝"),
    ("문화/여행", "국립자연휴양림 시니어 치유 숲 프로그램 예약 방법과 입장료 감면 혜택"),
    ("시니어/복지", "2026년 노인일자리 및 사회활동 지원사업 신청기간 및 맞춤 직종 종합 안내")
]

def generate_and_save_article(category: str = "", topic: str = ""):
    if not category or not topic:
        category, topic = random.choice(AUTO_TOPIC_POOL)

    title = topic
    summary = "1. 실생활에 즉시 도움 되는 심층 가이드. 2. 지원 대상, 신청처 및 구체적인 혜택 총정리. 3. 꼭 알아두어야 할 주의사항과 실전 꿀팁 수록."
    content = f"<h2>1. {topic} 핵심 개요</h2><p>본 기사는 독자 여러분께 꼭 필요한 정확하고 실용적인 정보를 안내합니다.</p>"

    if client:
        prompt = f"""
        당신은 5060 시니어 및 일반 대중을 위한 전문 프리미엄 웹진의 수석 전문 기자입니다.
        아래 [주제]와 [카테고리]에 대해 독자가 5분 이상 깊이 읽고 소장할 만한 '초고품질 심층 가이드 리포트'를 작성해 주세요.

        [주제]: {topic}
        [카테고리]: {category}

        [작성 필수 가이드라인 - 엄격 준수]:
        1. 분량: 한글 공백 포함 최소 2,000자 ~ 3,000자 이상의 매우 방대하고 디테일한 분량. (절대 몇 줄 요약으로 끝내지 마세요)
        2. 기사 구성 형식 (HTML 태그 필수 적용):
           - [제목]: 신뢰감 있고 호기심을 유발하는 고품격 헤드라인 (30자 내외)
           - [요약]: 기사의 핵심을 찌르는 3줄 브리핑 (1., 2., 3. 번호 포함)
           - [본문 구성]:
             * <h2>1. 주요 배경과 꼭 알아야 할 핵심 포인트</h2>
               (구체적인 정책 배경, 수혜 조건, 금액 수치 등을 3개 이상의 상세 문단으로 깊이 있게 서술)
             * <h2>2. 한눈에 비교하는 주요 기준 및 혜택 요약</h2>
               (독자의 가독성을 위해 항목/대상/지원내용/비고가 포함된 깔끔한 HTML <table> 표를 반드시 작성)
             * <h2>3. 실패 없는 실전 신청 절차 및 준비 서류 가이드</h2>
               (온라인 신청처, 관할 주민센터 방문 방법, 고객센터 대표번호, 필수 지참 서류를 <ol> 순서 리스트로 상세 설명)
             * <h2>4. 전문가가 알려주는 주의사항 및 알짜 꿀팁</h2>
               (신청 시 놓치기 쉬운 감액 조건, 유효기간, 중복 수혜 가능 여부 등을 <ul> 체크리스트로 작성)
             * <h2>5. 자주 묻는 질문 (FAQ)</h2>
               (실제 시니어 독자들이 가장 궁금해하는 핵심 질문 3가지와 명쾌한 해결 답변을 <p><strong>Q1...</strong></p><p>A1...</p> 형태로 수록)
        3. 어조: 뉴스 아나운서처럼 정중하고 정확하며 신뢰를 주는 어조 ('~합니다', '~하시기 바랍니다').

        [출력 JSON 규격]:
        {{
            "title": "기사 제목",
            "summary": "1. ... 2. ... 3. ...",
            "content": "<h2>1. ...</h2><p>...</p><table>...</table><h2>3. ...</h2><ol>...</ol><h2>4. ...</h2><ul>...</ul><h2>5. 자주 묻는 질문 (FAQ)</h2><p><strong>Q1...</strong></p><p>A1...</p>"
        }}
        """
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=dict(response_mime_type="application/json")
            )
            data = json.loads(response.text)
            title = data.get("title", title)
            summary = data.get("summary", summary)
            content = data.get("content", content)
        except Exception as e:
            print(f"AI 심층 기사 생성 오류: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO articles (title, category, summary, content, created_at, views, likes)
        VALUES (?, ?, ?, ?, ?, 0, 0)
    """, (title, category, summary, content, now))
    conn.commit()
    conn.close()
    print(f"[{now}] 고품질 심층 기사 자동 발행 완료: {title}")

# 백그라운드 자동 스케줄러 (6시간 = 21600초마다 1편씩 무인 발행)
def auto_article_scheduler():
    time.sleep(10)  # 서버 시작 10초 후 1편 자동 발행
    generate_and_save_article()
    while True:
        time.sleep(21600)
        generate_and_save_article()

threading.Thread(target=auto_article_scheduler, daemon=True).start()

# ======================================================
# 3. 공통 HTML 레이아웃 (반응형 & 시니어 최적화)
# ======================================================
HTML_LAYOUT = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta name="naver-site-verification" content="2be1d8c699f2db6d04ee4bbe598876b754cf1c10" />
    <meta name="google-site-verification" content="FuUKAJVoYVh_WbGkmCXJX2YwcIayUpBDGpBwLu7vlkU" />
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__PAGE_TITLE__ - 인사이트 데일리 웹진</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #1e3a8a;
            --accent-color: #2563eb;
            --text-main: #1e293b;
            --bg-subtle: #f8fafc;
        }
        body { background-color: var(--bg-subtle); font-family: "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: var(--text-main); -webkit-font-smoothing: antialiased; }
        
        /* 읽기 진행바 */
        #readingProgress { position: fixed; top: 0; left: 0; height: 4px; background: linear-gradient(90deg, #2563eb, #38bdf8); width: 0%; z-index: 9999; transition: width 0.1s ease; }

        .navbar-brand { font-weight: 800; color: var(--primary-color) !important; font-size: 1.35rem; }
        .hero-section { background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #2563eb 100%); color: white; padding: 48px 0; margin-bottom: 30px; }
        .article-card { border: none; border-radius: 14px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; height: 100%; background: white; }
        .article-card:hover { transform: translateY(-4px); box-shadow: 0 10px 22px rgba(0,0,0,0.09); }
        .badge-cat { background-color: #eff6ff; color: #1d4ed8; font-weight: 600; border: 1px solid #dbeafe; }
        
        /* 기사 본문 스타일링 */
        .article-content { font-size: 1.18rem; line-height: 2.05; color: #334155; }
        .article-content h2 { color: #0f172a; font-weight: 800; font-size: 1.45rem; margin-top: 2.8rem; margin-bottom: 1.2rem; border-left: 6px solid #2563eb; padding-left: 14px; }
        .article-content h3 { color: #1e293b; font-weight: 700; font-size: 1.25rem; margin-top: 2rem; margin-bottom: 0.8rem; }
        .article-content p { margin-bottom: 1.6rem; word-break: keep-all; letter-spacing: -0.02em; }
        .article-content table { width: 100%; margin: 2rem 0; border-collapse: separate; border-spacing: 0; background: white; border-radius: 10px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 2px 6px rgba(0,0,0,0.03); }
        .article-content th { background: #f1f5f9; padding: 14px; font-weight: 700; text-align: center; border-bottom: 2px solid #cbd5e1; color: #0f172a; }
        .article-content td { padding: 13px 15px; border-bottom: 1px solid #f1f5f9; font-size: 1.05rem; }
        .article-content ul, .article-content ol { margin-bottom: 1.8rem; padding-left: 1.8rem; }
        .article-content li { margin-bottom: 0.7rem; }

        /* 뉴스 브리핑 아나운서 TTS 바 */
        .tts-player-box { background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-radius: 14px; padding: 18px 22px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
        
        /* 자동 목차 박스 */
        .toc-box { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px 24px; margin-bottom: 2rem; }
        .toc-box a { color: #4b5563; text-decoration: none; font-weight: 600; }
        .toc-box a:hover { color: #2563eb; text-decoration: underline; }
    </style>
</head>
<body>
    <div id="readingProgress"></div>
    <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm sticky-top">
        <div class="container">
            <a class="navbar-brand" href="/"><i class="fa-solid fa-newspaper me-2 text-primary"></i>인사이트 데일리</a>
            <div class="d-flex align-items-center">
                <span class="badge bg-success-subtle text-success border border-success-subtle me-2 px-2 py-1"><i class="fa-solid fa-circle-dot me-1"></i>하루 4회 무인 자동 발행</span>
                <a href="/write" class="btn btn-primary btn-sm me-2 fw-semibold"><i class="fa-solid fa-plus me-1"></i>수동 즉시 발행</a>
                <a href="/admin/stats" class="btn btn-outline-secondary btn-sm"><i class="fa-solid fa-chart-line me-1"></i>관리자 통계</a>
            </div>
        </div>
    </nav>
    __CONTENT__
    <footer class="bg-white border-top py-4 mt-5 text-center text-muted small">
        <div class="container">
            <p class="mb-1 fw-semibold text-secondary">© 인사이트 데일리 웹진. All Rights Reserved.</p>
            <p class="mb-0"><a href="/rss" class="text-decoration-none text-muted me-3">RSS 피드</a> <a href="/sitemap.xml" class="text-decoration-none text-muted">사이트맵</a></p>
        </div>
    </footer>
</body>
</html>
"""

# ======================================================
# 4. 사이트 메인 & 기사 뷰 라우트
# ======================================================
@app.get("/", response_class=HTMLResponse)
def index():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cursor.fetchall()
    conn.close()

    cards_html = ""
    for row in articles:
        cards_html += f"""
        <div class="col-md-4 mb-4">
            <div class="card article-card p-4">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <span class="badge badge-cat px-2 py-1">{row['category']}</span>
                    <small class="text-muted"><i class="fa-regular fa-clock me-1"></i>{row['created_at'][:10]}</small>
                </div>
                <h5 class="card-title fw-bold mb-3 lh-base">
                    <a href="/article/{row['id']}" class="text-decoration-none text-dark">{row['title']}</a>
                </h5>
                <p class="card-text text-secondary small flex-grow-1" style="line-height: 1.65;">{row['summary']}</p>
                <div class="mt-3 pt-3 border-top d-flex justify-content-between align-items-center">
                    <span class="text-muted small"><i class="fa-regular fa-eye me-1"></i>조회 {row['views']}회</span>
                    <a href="/article/{row['id']}" class="btn btn-sm btn-outline-primary fw-semibold">심층 가이드 읽기 →</a>
                </div>
            </div>
        </div>
        """

    if not cards_html:
        cards_html = '<div class="col-12 text-center py-5 text-muted">첫 기사를 생성하고 있습니다. 잠시 후 새로고침해 주세요.</div>'

    content = f"""
    <div class="hero-section text-center">
        <div class="container">
            <h1 class="fw-bold mb-2 display-6">인사이트 데일리 웹진</h1>
            <p class="lead mb-0 text-white-50">시니어 복지 혜택 · 실전 생활재테크 · 웰에이징 건강 심층 가이드</p>
        </div>
    </div>
    <div class="container">
        <div class="row">
            {cards_html}
        </div>
    </div>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", "메인").replace("__CONTENT__", content)

@app.get("/article/{article_id}", response_class=HTMLResponse)
def view_article(article_id: int):
    increase_article_view(article_id)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return HTMLResponse("존재하지 않는 기사입니다.", status_code=404)

    # 관련 기사 3편
    cursor.execute("SELECT id, title, category, created_at FROM articles WHERE id != ? AND category = ? ORDER BY id DESC LIMIT 3", (article_id, row['category']))
    related_articles = cursor.fetchall()
    if len(related_articles) < 3:
        cursor.execute("SELECT id, title, category, created_at FROM articles WHERE id != ? ORDER BY id DESC LIMIT 3", (article_id,))
        related_articles = cursor.fetchall()
    conn.close()

    related_html = ""
    for rel in related_articles:
        related_html += f"""
        <div class="col-md-4 mb-3">
            <div class="card h-100 p-3 border-0 shadow-sm rounded-3">
                <span class="badge badge-cat w-auto align-self-start mb-2">{rel['category']}</span>
                <h6 class="fw-bold"><a href="/article/{rel['id']}" class="text-decoration-none text-dark">{rel['title']}</a></h6>
                <small class="text-muted mt-auto pt-2">{rel['created_at'][:10]}</small>
            </div>
        </div>
        """

    content_len = len(row['content'])
    est_minutes = max(2, round(content_len / 450))
    body_html = row['content']

    content = f"""
    <div class="container py-5" style="max-width: 860px;">
        <!-- 상단 헤더 -->
        <div class="mb-4">
            <div class="d-flex gap-2 align-items-center mb-2">
                <span class="badge badge-cat px-3 py-2 fs-6">{row['category']}</span>
                <span class="text-muted small"><i class="fa-regular fa-clock me-1"></i>{row['created_at']}</span>
                <span class="badge bg-light text-dark border ms-auto"><i class="fa-solid fa-book-open-reader me-1 text-primary"></i>약 {est_minutes}분 분량 ({content_len:,}자)</span>
            </div>
            <h1 class="fw-bold text-dark lh-base my-3" style="font-size: 2.15rem; letter-spacing: -0.03em;">{row['title']}</h1>
        </div>

        <!-- 고품질 아나운서 TTS 바 & 폰트 조절 컨트롤러 -->
        <div class="tts-player-box mb-4 shadow-sm">
            <div class="d-flex align-items-center gap-3 flex-wrap">
                <button id="ttsPlayBtn" class="btn btn-primary px-3 py-2 fw-bold rounded-pill shadow-sm" onclick="toggleTTS()">
                    <i class="fa-solid fa-circle-play me-1"></i> <span id="ttsBtnText">뉴스 아나운서 음성 듣기</span>
                </button>
                <div class="btn-group btn-group-sm" role="group">
                    <button type="button" class="btn btn-outline-primary" onclick="setSpeed(0.85)">0.8x</button>
                    <button type="button" class="btn btn-primary active" id="speedNormal" onclick="setSpeed(1.0)">1.0x (표준)</button>
                    <button type="button" class="btn btn-outline-primary" onclick="setSpeed(1.2)">1.2x</button>
                </div>
                <small id="ttsStatus" class="text-secondary fw-semibold">편안하고 또렷한 음성으로 읽어드립니다.</small>
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="text-muted small fw-semibold">글자 크기:</span>
                <button class="btn btn-light btn-sm border rounded-circle" onclick="changeFontSize(1)" title="글자 확대"><i class="fa-solid fa-plus"></i></button>
                <button class="btn btn-light btn-sm border rounded-circle" onclick="changeFontSize(-1)" title="글자 축소"><i class="fa-solid fa-minus"></i></button>
            </div>
        </div>

        <!-- 핵심 3줄 브리핑 카드 -->
        <div class="p-4 mb-4 bg-white rounded-4 border-start border-5 border-primary shadow-sm">
            <h6 class="fw-bold text-primary mb-2"><i class="fa-solid fa-bolt me-2"></i>핵심 3줄 브리핑</h6>
            <div class="text-secondary fw-medium lh-base" style="font-size: 1.08rem;">{row['summary']}</div>
        </div>

        <!-- 스마트 인터랙티브 목차 -->
        <div class="toc-box">
            <div class="fw-bold text-dark mb-2"><i class="fa-solid fa-list-check me-2 text-primary"></i>이 기사의 주요 목차</div>
            <ul id="tocList" class="mb-0 ps-3 small" style="line-height: 1.9;"></ul>
        </div>

        <!-- 심층 기사 본문 영역 -->
        <article id="articleBody" class="article-content bg-white p-4 p-md-5 rounded-4 shadow-sm mb-5">
            {body_html}
        </article>

        <!-- 독자 공감 & 공유 버튼 -->
        <div class="d-flex justify-content-between align-items-center bg-white p-3 p-md-4 rounded-4 shadow-sm mb-5 border">
            <button id="likeBtn" class="btn btn-outline-danger btn-sm px-3 fw-bold rounded-pill" onclick="likePost()">
                <i class="fa-solid fa-heart me-1"></i> 유익해요 <span id="likeCount">{row['likes']}</span>
            </button>
            <div class="d-flex gap-2">
                <button class="btn btn-outline-secondary btn-sm rounded-pill" onclick="copyCurrentUrl()"><i class="fa-solid fa-link me-1"></i>기사 주소 복사</button>
                <a href="/" class="btn btn-primary btn-sm rounded-pill px-3"><i class="fa-solid fa-list me-1"></i>목록으로</a>
            </div>
        </div>

        <!-- 관련 기사 추천 섹션 -->
        <div class="mt-5 pt-3">
            <h4 class="fw-bold mb-3 text-dark"><i class="fa-solid fa-newspaper me-2 text-primary"></i>함께 읽으면 유익한 추천 가이드</h4>
            <div class="row">
                {related_html if related_html else '<p class="text-muted small">추천 기사가 준비 중입니다.</p>'}
            </div>
        </div>
    </div>

    <!-- 스크립트: 아나운서 고품질 음성 엔진 & 목차 자동생성 & 스크롤바 -->
    <script>
        // 1. 읽기 스크롤 진행바
        window.onscroll = function() {{
            var winScroll = document.body.scrollTop || document.documentElement.scrollTop;
            var height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            var scrolled = (winScroll / height) * 100;
            document.getElementById("readingProgress").style.width = scrolled + "%";
        }};

        // 2. 본문 제목(h2) 기반 자동 목차 생성
        window.addEventListener('DOMContentLoaded', function() {{
            var h2s = document.querySelectorAll('#articleBody h2');
            var tocList = document.getElementById('tocList');
            if (h2s.length === 0) {{
                document.querySelector('.toc-box').style.display = 'none';
                return;
            }}
            h2s.forEach(function(h2, index) {{
                h2.id = 'section-' + index;
                var li = document.createElement('li');
                var a = document.createElement('a');
                a.href = '#section-' + index;
                a.innerText = h2.innerText;
                li.appendChild(a);
                tocList.appendChild(li);
            }});
        }});

        // 3. 고품질 뉴스 아나운서 TTS 엔진
        var isSpeaking = false;
        var speechSynth = window.speechSynthesis;
        var currentRate = 0.95;
        var selectedVoice = null;

        function findBestKoreanVoice() {{
            if (!speechSynth) return null;
            var voices = speechSynth.getVoices();
            // 가장 자연스러운 음성 우선순위 탐색 (구글 한국어 > MS 하이미/선희/인준 > 일반 ko-KR)
            for (var i = 0; i < voices.length; i++) {{
                if (voices[i].lang.includes('ko') || voices[i].lang.includes('KO')) {{
                    if (voices[i].name.includes('Google') || voices[i].name.includes('Natural') || voices[i].name.includes('Online')) {{
                        return voices[i];
                    }}
                }}
            }}
            for (var j = 0; j < voices.length; j++) {{
                if (voices[j].lang.includes('ko') || voices[j].lang.includes('KO')) return voices[j];
            }}
            return null;
        }}

        if (speechSynth && speechSynth.onvoiceschanged !== undefined) {{
            speechSynth.onvoiceschanged = function() {{
                selectedVoice = findBestKoreanVoice();
            }};
        }}

        function setSpeed(speed) {{
            currentRate = speed;
            if (isSpeaking) {{
                toggleTTS();
                toggleTTS();
            }}
        }}

        function toggleTTS() {{
            if (!speechSynth) {{
                alert("현재 브라우저는 음성 재생 기능을 지원하지 않습니다.");
                return;
            }}

            if (isSpeaking) {{
                speechSynth.cancel();
                isSpeaking = false;
                document.getElementById('ttsBtnText').innerText = "뉴스 아나운서 음성 듣기";
                document.getElementById('ttsPlayBtn').className = "btn btn-primary px-3 py-2 fw-bold rounded-pill shadow-sm";
                document.getElementById('ttsStatus').innerText = "재생이 멈췄습니다.";
            }} else {{
                var rawText = document.getElementById('articleBody').innerText;
                var cleanText = rawText.replace(/\\s+/g, ' ').trim();
                
                var utterance = new SpeechSynthesisUtterance(cleanText);
                utterance.lang = 'ko-KR';
                utterance.rate = currentRate;
                utterance.pitch = 1.05; // 명쾌하고 또렷한 아나운서 음조
                
                if (!selectedVoice) selectedVoice = findBestKoreanVoice();
                if (selectedVoice) utterance.voice = selectedVoice;

                utterance.onend = function() {{
                    isSpeaking = false;
                    document.getElementById('ttsBtnText').innerText = "기사 다시 듣기";
                    document.getElementById('ttsPlayBtn').className = "btn btn-primary px-3 py-2 fw-bold rounded-pill shadow-sm";
                    document.getElementById('ttsStatus').innerText = "낭독이 완료되었습니다.";
                }};

                speechSynth.speak(utterance);
                isSpeaking = true;
                document.getElementById('ttsBtnText').innerText = "음성 일시정지";
                document.getElementById('ttsPlayBtn').className = "btn btn-danger px-3 py-2 fw-bold rounded-pill shadow-sm";
                document.getElementById('ttsStatus').innerText = "아나운서 톤으로 정갈하게 낭독 중입니다...";
            }}
        }}

        // 4. 글자 크기 조절
        var currentSize = 1.18;
        function changeFontSize(delta) {{
            currentSize = Math.max(0.95, Math.min(1.65, currentSize + (delta * 0.1)));
            document.getElementById('articleBody').style.fontSize = currentSize + 'rem';
        }}

        // 5. 링크 복사
        function copyCurrentUrl() {{
            navigator.clipboard.writeText(window.location.href).then(function() {{
                alert("기사 링크가 복사되었습니다!");
            }});
        }}

        // 6. 좋아요 반응
        function likePost() {{
            var countEl = document.getElementById('likeCount');
            var curr = parseInt(countEl.innerText) || 0;
            countEl.innerText = curr + 1;
            document.getElementById('likeBtn').className = "btn btn-danger btn-sm px-3 fw-bold rounded-pill";
        }}
    </script>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", row['title']).replace("__CONTENT__", content)

# 수동 즉시 생성 폼
@app.get("/write", response_class=HTMLResponse)
def write_form():
    form_html = """
    <div class="container py-5" style="max-width: 760px;">
        <div class="card p-4 p-md-5 shadow-sm border-0 rounded-4">
            <h3 class="fw-bold mb-2 text-dark"><i class="fa-solid fa-plus me-2 text-primary"></i>전문가 심층 기사 수동 발행</h3>
            <p class="text-muted small mb-4">원하는 특정 주제가 있을 때 입력하시면 즉시 2,000자 이상의 심층 리포트를 작성하여 웹진에 자동 등록합니다.</p>

            <form method="post" action="/write">
                <div class="mb-3">
                    <label class="form-label fw-bold">카테고리</label>
                    <select name="category" class="form-select py-2">
                        <option value="시니어/복지">시니어 / 복지 혜택</option>
                        <option value="문화/여행">문화 / 힐링 여행</option>
                        <option value="경제/재테크">경제 / 생활 재테크</option>
                        <option value="건강/의학">건강 / 웰에이징</option>
                        <option value="IT/디지털">스마트폰 / IT 생활가이드</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold">기사 주제</label>
                    <input type="text" name="topic" class="form-control py-2" placeholder="예: 2026년 시니어 틀니 건강보험 혜택 및 신청방법 총정리" required>
                </div>
                <button type="submit" class="btn btn-primary w-100 py-3 fw-bold fs-6 mt-3 shadow-sm">
                    <i class="fa-solid fa-bolt me-1"></i> 즉시 2,000자 심층 기사 작성 및 발행
                </button>
            </form>
        </div>
    </div>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", "기사 수동 발행").replace("__CONTENT__", form_html)

@app.post("/write")
def write_submit(category: str = Form(...), topic: str = Form(...)):
    generate_and_save_article(category, topic)
    return RedirectResponse(url="/", status_code=303)

# ======================================================
# 5. 검색엔진용 Sitemap 및 RSS 피드 라우트
# ======================================================
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
            xml += f'  <url><loc>https://insight-webzine.onrender.com/article/{row["id"]}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
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
            xml += f'    <title><![CDATA[{row["title"]}]]></title>\n'
            xml += f'    <link>https://insight-webzine.onrender.com/article/{row["id"]}</link>\n'
            xml += f'    <description><![CDATA[{row["summary"]}]]></description>\n'
            xml += '  </item>\n'
        xml += '</channel>\n</rss>'
        return Response(content=xml, media_type="application/xml")
    except Exception:
        return Response(content='<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>인사이트 데일리 웹진</title><link>https://insight-webzine.onrender.com</link></channel></rss>', media_type="application/xml")

# ======================================================
# 6. 비공개 관리자 통계 대시보드
# ======================================================
@app.get("/admin/stats", response_class=HTMLResponse)
def admin_stats(pw: str = ""):
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
        return HTML_LAYOUT.replace("__PAGE_TITLE__", "관리자 로그인").replace("__CONTENT__", login_html)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, COALESCE(views, 0) as views, COALESCE(likes, 0) as likes, created_at FROM articles ORDER BY views DESC, id DESC")
    articles = cursor.fetchall()
    total_views = sum([row['views'] for row in articles])
    conn.close()

    rows_html = ""
    for idx, row in enumerate(articles, 1):
        rows_html += f"""
        <tr>
            <td class="text-center fw-bold text-muted">{idx}</td>
            <td><a href="/article/{row['id']}" target="_blank" class="text-decoration-none text-dark fw-semibold">{row['title']}</a></td>
            <td class="text-center"><span class="badge badge-cat">{row['category']}</span></td>
            <td class="text-center text-primary fw-bold">{row['views']:,} 회</td>
            <td class="text-center text-danger fw-bold">{row['likes']:,} 개</td>
            <td class="text-center text-muted small">{row['created_at'][:10]}</td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="6" class="text-center py-4 text-muted">등록된 기사가 없습니다.</td></tr>'

    dashboard_html = f"""
    <div class="container py-5" style="max-width: 960px;">
        <h3 class="fw-bold mb-4">📊 기사 조회수 및 방문 통계</h3>
        <div class="row g-3 mb-4">
            <div class="col-md-6">
                <div class="card p-4 shadow-sm border-0 text-center rounded-4">
                    <div class="text-muted small mb-1">총 누적 기사 조회수</div>
                    <div class="fs-1 fw-bold text-primary">{total_views:,} <span class="fs-6 text-muted">회</span></div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card p-4 shadow-sm border-0 text-center rounded-4">
                    <div class="text-muted small mb-1">총 발행 기사 수</div>
                    <div class="fs-1 fw-bold text-secondary">{len(articles):,} <span class="fs-6 text-muted">개</span></div>
                </div>
            </div>
        </div>
        <div class="card shadow-sm border-0 rounded-4 overflow-hidden">
            <table class="table table-hover mb-0 align-middle">
                <thead class="table-light">
                    <tr>
                        <th class="text-center" style="width: 60px;">순위</th>
                        <th>기사 제목</th>
                        <th class="text-center" style="width: 130px;">카테고리</th>
                        <th class="text-center" style="width: 110px;">조회수</th>
                        <th class="text-center" style="width: 100px;">좋아요</th>
                        <th class="text-center" style="width: 120px;">작성일</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", "관리자 통계").replace("__CONTENT__", dashboard_html)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
