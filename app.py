import os
import sqlite3
import json
import time
from datetime import datetime

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
import uvicorn

# ======================================================
# 1. 환경 설정 및 DB 초기화
# ======================================================
app = FastAPI()

# 관리자 통계 비밀번호
ADMIN_STATS_PASSWORD = "admin1234"

# Gemini API 클라이언트 초기화 (환경 변수 GEMINI_API_KEY 사용)
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
            views INTEGER DEFAULT 0
        )
    """)
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN views INTEGER DEFAULT 0")
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
# 2. 공통 HTML 레이아웃
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
        body { background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; }
        .navbar-brand { font-weight: 800; color: #1e3a8a !important; font-size: 1.3rem; }
        .hero-section { background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); color: white; padding: 45px 0; margin-bottom: 30px; }
        .article-card { border: none; border-radius: 14px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; height: 100%; background: white; }
        .article-card:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.08); }
        .badge-cat { background-color: #eff6ff; color: #1d4ed8; font-weight: 600; border: 1px solid #dbeafe; }
        .btn-custom { background-color: #1e3a8a; color: white; }
        .btn-custom:hover { background-color: #172554; color: white; }
        
        .article-content { font-size: 1.15rem; line-height: 1.95; color: #334155; }
        .article-content h2, .article-content h3 { color: #0f172a; font-weight: 700; margin-top: 2rem; margin-bottom: 1rem; border-left: 5px solid #2563eb; padding-left: 12px; }
        .article-content p { margin-bottom: 1.4rem; word-break: keep-all; }
        .article-content table { width: 100%; margin: 1.5rem 0; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,0.04); }
        .article-content th { background: #f1f5f9; padding: 12px; font-weight: 600; text-align: center; border-bottom: 2px solid #e2e8f0; }
        .article-content td { padding: 12px; border-bottom: 1px solid #f1f5f9; }
        .article-content ul, .article-content ol { margin-bottom: 1.4rem; padding-left: 1.5rem; }
        .article-content li { margin-bottom: 0.5rem; }
        
        .tts-player-box { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 12px; padding: 15px 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm sticky-top">
        <div class="container">
            <a class="navbar-brand" href="/"><i class="fa-solid fa-newspaper me-2 text-primary"></i>인사이트 데일리</a>
            <div class="d-flex align-items-center">
                <a href="/write" class="btn btn-primary btn-sm me-2 fw-semibold"><i class="fa-solid fa-wand-magic-sparkles me-1"></i>AI 기사 생성</a>
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
# 3. 사이트 페이지 라우트
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
                <p class="card-text text-secondary small flex-grow-1" style="line-height: 1.6;">{row['summary']}</p>
                <div class="mt-3 pt-3 border-top d-flex justify-content-between align-items-center">
                    <span class="text-muted small"><i class="fa-regular fa-eye me-1"></i>추천 가이드</span>
                    <a href="/article/{row['id']}" class="btn btn-sm btn-outline-primary fw-semibold">기사 읽기 →</a>
                </div>
            </div>
        </div>
        """

    if not cards_html:
        cards_html = '<div class="col-12 text-center py-5 text-muted">발행된 기사가 없습니다. 상단의 AI 기사 생성을 눌러보세요.</div>'

    content = f"""
    <div class="hero-section text-center">
        <div class="container">
            <h1 class="fw-bold mb-2 display-6">인사이트 데일리 웹진</h1>
            <p class="lead mb-0 text-white-50">시니어를 위한 알찬 혜택부터 생활 문화·재테크 심층 가이드</p>
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
    est_minutes = max(1, round(content_len / 500))
    body_html = row['content'].replace('\n', '<br>') if '<p>' not in row['content'] and '<div>' not in row['content'] else row['content']

    content = f"""
    <div class="container py-5" style="max-width: 840px;">
        <div class="mb-4">
            <div class="d-flex gap-2 align-items-center mb-2">
                <span class="badge badge-cat px-3 py-2 fs-6">{row['category']}</span>
                <span class="text-muted small"><i class="fa-regular fa-clock me-1"></i>{row['created_at']}</span>
                <span class="badge bg-light text-dark border ms-auto"><i class="fa-solid fa-book-open-reader me-1 text-primary"></i>약 {est_minutes}분 소요 ({content_len:,}자)</span>
            </div>
            <h1 class="fw-bold text-dark lh-base my-3" style="font-size: 2.1rem;">{row['title']}</h1>
        </div>

        <div class="tts-player-box mb-4 shadow-sm">
            <div class="d-flex align-items-center gap-3">
                <button id="ttsPlayBtn" class="btn btn-primary btn-sm px-3 fw-bold rounded-pill" onclick="toggleTTS()">
                    <i class="fa-solid fa-volume-high me-1"></i> <span id="ttsBtnText">기사 음성 듣기</span>
                </button>
                <small id="ttsStatus" class="text-secondary fw-semibold">클릭 시 기사를 편안하게 읽어드립니다.</small>
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="text-muted small fw-semibold">글자 크기:</span>
                <button class="btn btn-light btn-sm border rounded-circle" onclick="changeFontSize(1)" title="글자 확대"><i class="fa-solid fa-plus"></i></button>
                <button class="btn btn-light btn-sm border rounded-circle" onclick="changeFontSize(-1)" title="글자 축소"><i class="fa-solid fa-minus"></i></button>
            </div>
        </div>

        <div class="p-4 mb-4 bg-white rounded-3 border-start border-4 border-primary shadow-sm">
            <h6 class="fw-bold text-primary mb-2"><i class="fa-solid fa-circle-check me-2"></i>핵심 3줄 브리핑</h6>
            <div class="text-secondary fw-medium lh-base" style="font-size: 1.05rem;">{row['summary']}</div>
        </div>

        <article id="articleBody" class="article-content bg-white p-4 p-md-5 rounded-4 shadow-sm mb-5">
            {body_html}
        </article>

        <div class="d-flex justify-content-between align-items-center bg-light p-3 rounded-3 mb-5 border">
            <span class="fw-semibold text-secondary small"><i class="fa-solid fa-share-nodes me-1"></i>이 기사를 주변에 공유해 보세요</span>
            <div class="d-flex gap-2">
                <button class="btn btn-outline-secondary btn-sm" onclick="copyCurrentUrl()"><i class="fa-solid fa-link me-1"></i>링크 복사</button>
                <a href="/" class="btn btn-primary btn-sm"><i class="fa-solid fa-list me-1"></i>목록으로</a>
            </div>
        </div>

        <div class="mt-5 pt-3">
            <h4 class="fw-bold mb-3 text-dark"><i class="fa-solid fa-newspaper me-2 text-primary"></i>함께 읽으면 좋은 추천 가이드</h4>
            <div class="row">
                {related_html if related_html else '<p class="text-muted small">추천 기사가 준비 중입니다.</p>'}
            </div>
        </div>
    </div>

    <script>
        let isSpeaking = false;
        let speechSynth = window.speechSynthesis;
        let utterance = null;

        function toggleTTS() {
            if (!speechSynth) {
                alert("현재 브라우저는 음성 듣기를 지원하지 않습니다.");
                return;
            }

            if (isSpeaking) {
                speechSynth.cancel();
                isSpeaking = false;
                document.getElementById('ttsBtnText').innerText = "기사 음성 듣기";
                document.getElementById('ttsPlayBtn').className = "btn btn-primary btn-sm px-3 fw-bold rounded-pill";
                document.getElementById('ttsStatus').innerText = "음성 재생이 중지되었습니다.";
            } else {
                const articleText = document.getElementById('articleBody').innerText;
                utterance = new SpeechSynthesisUtterance(articleText);
                utterance.lang = 'ko-KR';
                utterance.rate = 0.95;

                utterance.onend = function() {
                    isSpeaking = false;
                    document.getElementById('ttsBtnText').innerText = "기사 다시 듣기";
                    document.getElementById('ttsPlayBtn').className = "btn btn-primary btn-sm px-3 fw-bold rounded-pill";
                    document.getElementById('ttsStatus').innerText = "재생이 완료되었습니다.";
                };

                speechSynth.speak(utterance);
                isSpeaking = true;
                document.getElementById('ttsBtnText').innerText = "음성 일시정지";
                document.getElementById('ttsPlayBtn').className = "btn btn-danger btn-sm px-3 fw-bold rounded-pill";
                document.getElementById('ttsStatus').innerText = "기사를 낭독하고 있습니다...";
            }
        }

        let currentSize = 1.15;
        function changeFontSize(delta) {
            currentSize = Math.max(0.9, Math.min(1.6, currentSize + (delta * 0.1)));
            document.getElementById('articleBody').style.fontSize = currentSize + 'rem';
        }

        function copyCurrentUrl() {
            navigator.clipboard.writeText(window.location.href).then(() => {
                alert("기사 링크가 복사되었습니다! 원하는 곳에 붙여넣어 공유하세요.");
            });
        }
    </script>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", row['title']).replace("__CONTENT__", content)

# ======================================================
# 4. 고도화된 AI 기사 작성 시스템
# ======================================================
@app.get("/write", response_class=HTMLResponse)
def write_form():
    form_html = """
    <div class="container py-5" style="max-width: 760px;">
        <div class="card p-4 p-md-5 shadow-sm border-0 rounded-4">
            <h3 class="fw-bold mb-2 text-dark"><i class="fa-solid fa-wand-magic-sparkles me-2 text-primary"></i>AI 전문가 심층 기사 생성</h3>
            <p class="text-muted small mb-4">주제 키워드만 입력하면 체류 시간을 극대화하는 1,500자 이상의 고품격 가이드 기사를 자동 작성합니다.</p>

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
                    <label class="form-label fw-bold">기사 주제 (키워드 또는 관심사)</label>
                    <input type="text" name="topic" class="form-control py-2" placeholder="예: 2026년 시니어 임플란트 건강보험 혜택 및 신청방법 총정리" required>
                </div>
                <button type="submit" class="btn btn-primary w-100 py-3 fw-bold fs-6 mt-3 shadow-sm">
                    <i class="fa-solid fa-bolt me-1"></i> 원클릭 1,500자 전문 기사 자동 생성 및 발행
                </button>
            </form>
        </div>
    </div>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", "AI 기사 작성").replace("__CONTENT__", form_html)

@app.post("/write")
def write_submit(category: str = Form(...), topic: str = Form(...)):
    if not client:
        title = f"[안내] {topic}"
        summary = "1. 주요 세부 정보 가이드. 2. 신청 방법 및 핵심 혜택 요약. 3. 꼭 알아두어야 할 주의사항 안내."
        content = f"<h2>1. {topic} 개요 및 필요성</h2><p>본 기사는 {topic}에 대해 다룹니다.</p>"
    else:
        prompt = f"""
        당신은 5060 시니어 및 일반 대중을 위한 전문 웹진의 수석 에디터입니다.
        아래 [주제]와 [카테고리]에 맞는 고품격 심층 가이드 기사를 작성해 주세요.

        [주제]: {topic}
        [카테고리]: {category}

        [작성 가이드라인 - 반드시 준수]:
        1. 분량: 한글 공백 포함 최소 1,500자 ~ 2,000자 이상의 매우 상세하고 실용적인 내용.
        2. 기사 구조:
           - 매력적이고 클릭을 유도하는 기사 제목 1개 (SEO 최적화)
           - 핵심 3줄 요약 (1. 2. 3. 번호 매김)
           - 본문 (HTML 태그 적극 활용):
             * <h2> 소제목 3~4개로 구조화
             * 독자가 바로 실천할 수 있는 구체적 수치, 지원 대상, 신청처, 고객센터 정보 포함
             * 본문 중간에 비교나 정리를 위한 HTML <table> 요약표 반드시 1개 이상 포함
             * <h2> 자주 묻는 질문 (FAQ) 3가지 및 명쾌한 답변
             * <h2> 주의사항 및 꿀팁 체크리스트
        3. 톤앤매너: 친절하고 신뢰감 넘치는 전문가 어조 ('~합니다', '~하세요').

        [출력 JSON 형식]:
        {{
            "title": "기사 제목",
            "summary": "1. ... 2. ... 3. ...",
            "content": "<h2>...</h2><p>...</p><table>...</table><h2>자주 묻는 질문 (FAQ)</h2>..."
        }}
        """
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=dict(response_mime_type="application/json")
            )
            data = json.loads(response.text)
            title = data.get("title", topic)
            summary = data.get("summary", "상세 가이드 내용 요약")
            content = data.get("content", "<p>내용 생성 오류</p>")
        except Exception as e:
            title = f"{topic} 핵심 가이드"
            summary = "상세 내용 요약"
            content = f"<p>AI 기사 생성 중 오류: {str(e)}</p>"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO articles (title, category, summary, content, created_at, views)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (title, category, summary, content, now))
    conn.commit()
    conn.close()
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
    cursor.execute("SELECT id, title, category, COALESCE(views, 0) as views, created_at FROM articles ORDER BY views DESC, id DESC")
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
            <td class="text-center text-muted small">{row['created_at'][:10]}</td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="5" class="text-center py-4 text-muted">등록된 기사가 없습니다.</td></tr>'

    dashboard_html = f"""
    <div class="container py-5" style="max-width: 900px;">
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
                        <th class="text-center" style="width: 120px;">조회수</th>
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
