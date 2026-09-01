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

# 관리자 통계 비밀번호 (원하시는 번호로 변경 가능)
ADMIN_STATS_PASSWORD = "admin1234"

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
    # 기존 DB에 views 컬럼이 없는 경우 대비
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN views INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

# 조회수 증가 함수
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
# 2. 공통 HTML 레이아웃 (SEO 및 메타태그 포함)
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
        body { background-color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .navbar-brand { font-weight: 800; color: #1e3a8a !important; }
        .hero-section { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 40px 0; margin-bottom: 30px; }
        .article-card { border: none; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); transition: transform 0.2s; height: 100%; }
        .article-card:hover { transform: translateY(-4px); }
        .badge-cat { background-color: #e0e7ff; color: #3730a3; font-weight: 600; }
        .btn-custom { background-color: #1e3a8a; color: white; }
        .btn-custom:hover { background-color: #172554; color: white; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom shadow-sm">
        <div class="container">
            <a class="navbar-brand" href="/"><i class="fa-solid fa-newspaper me-2"></i>인사이트 데일리</a>
            <div class="d-flex">
                <a href="/write" class="btn btn-outline-primary btn-sm me-2"><i class="fa-solid fa-pen me-1"></i>기사 작성</a>
                <a href="/admin/stats" class="btn btn-outline-secondary btn-sm"><i class="fa-solid fa-chart-line me-1"></i>관리자 통계</a>
            </div>
        </div>
    </nav>
    __CONTENT__
    <footer class="bg-white border-top py-4 mt-5 text-center text-muted small">
        <div class="container">
            <p class="mb-1">© 인사이트 데일리 웹진. All Rights Reserved.</p>
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
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="badge badge-cat px-2 py-1">{row['category']}</span>
                    <small class="text-muted">{row['created_at'][:10]}</small>
                </div>
                <h5 class="card-title fw-bold mb-3"><a href="/article/{row['id']}" class="text-decoration-none text-dark">{row['title']}</a></h5>
                <p class="card-text text-muted small flex-grow-1">{row['summary']}</p>
                <div class="mt-3">
                    <a href="/article/{row['id']}" class="btn btn-sm btn-outline-secondary w-100">기사 읽기</a>
                </div>
            </div>
        </div>
        """

    if not cards_html:
        cards_html = '<div class="col-12 text-center py-5 text-muted">발행된 기사가 없습니다. 상단의 기사 작성을 눌러보세요.</div>'

    content = f"""
    <div class="hero-section text-center">
        <div class="container">
            <h1 class="fw-bold mb-2">인사이트 데일리 웹진</h1>
            <p class="lead mb-0 text-white-50">매일 만나는 새로운 시선과 유용한 지식</p>
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
    # 독자 화면에는 띄우지 않고 내부 DB 조회수만 1 증가
    increase_article_view(article_id)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("존재하지 않는 기사입니다.", status_code=404)

    body_html = row['content'].replace('\n', '<br>')
    content = f"""
    <div class="container py-5" style="max-width: 800px;">
        <div class="mb-4">
            <span class="badge badge-cat mb-2">{row['category']}</span>
            <h2 class="fw-bold text-dark">{row['title']}</h2>
            <div class="text-muted small border-bottom pb-3">{row['created_at']}</div>
        </div>
        <div class="p-3 mb-4 bg-light rounded border-start border-4 border-primary">
            <strong>요약:</strong> {row['summary']}
        </div>
        <div class="article-body fs-5 lh-lg text-secondary mb-5">
            {body_html}
        </div>
        <div class="text-center border-top pt-4">
            <a href="/" class="btn btn-outline-primary"><i class="fa-solid fa-list me-1"></i>목록으로 돌아가기</a>
        </div>
    </div>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", row['title']).replace("__CONTENT__", content)

@app.get("/write", response_class=HTMLResponse)
def write_form():
    form_html = """
    <div class="container py-5" style="max-width: 700px;">
        <h3 class="fw-bold mb-4"><i class="fa-solid fa-pen-nib me-2"></i>새 기사 작성</h3>
        <form method="post" action="/write" class="card p-4 shadow-sm border-0">
            <div class="mb-3">
                <label class="form-label fw-bold">카테고리</label>
                <select name="category" class="form-select">
                    <option value="경제/경영">경제/경영</option>
                    <option value="IT/테크">IT/테크</option>
                    <option value="사회/복지">사회/복지</option>
                    <option value="문화/라이프">문화/라이프</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label fw-bold">기사 제목</label>
                <input type="text" name="title" class="form-control" placeholder="제목을 입력하세요" required>
            </div>
            <div class="mb-3">
                <label class="form-label fw-bold">기사 요약 (1~2줄)</label>
                <input type="text" name="summary" class="form-control" placeholder="요약 내용을 입력하세요" required>
            </div>
            <div class="mb-4">
                <label class="form-label fw-bold">본문 내용</label>
                <textarea name="content" rows="10" class="form-control" placeholder="본문 내용을 입력하세요" required></textarea>
            </div>
            <button type="submit" class="btn btn-primary w-100 py-2 fw-bold">기사 발행하기</button>
        </form>
    </div>
    """
    return HTML_LAYOUT.replace("__PAGE_TITLE__", "기사 작성").replace("__CONTENT__", form_html)

@app.post("/write")
def write_submit(
    title: str = Form(...),
    category: str = Form(...),
    summary: str = Form(...),
    content: str = Form(...)
):
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
# 4. 검색엔진용 Sitemap 및 RSS 피드 라우트
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
# 5. 비공개 관리자 통계 대시보드
# ======================================================
@app.get("/admin/stats", response_class=HTMLResponse)
def admin_stats(pw: str = ""):
    if pw != ADMIN_STATS_PASSWORD:
        login_html = """
        <div class="container py-5 d-flex justify-content-center">
            <div class="card p-4 shadow-sm border-0 text-center" style="max-width: 360px; width: 100%;">
                <h4 class="fw-bold mb-3">📊 관리자 로그인</h4>
                """ + ('<div class="alert alert-danger py-2 small mb-3">비밀번호가 틀렸습니다.</div>' if pw else '') + """
                <form method="get" action="/admin/stats">
                    <input type="password" name="pw" class="form-control mb-3" placeholder="비밀번호 입력" autofocus required>
                    <button type="submit" class="btn btn-primary w-100 fw-bold">통계 보기</button>
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
                <div class="card p-3 shadow-sm border-0 text-center">
                    <div class="text-muted small">총 누적 기사 조회수</div>
                    <div class="fs-2 fw-bold text-primary">{total_views:,} <span class="fs-6 text-muted">회</span></div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card p-3 shadow-sm border-0 text-center">
                    <div class="text-muted small">총 발행 기사 수</div>
                    <div class="fs-2 fw-bold text-secondary">{len(articles):,} <span class="fs-6 text-muted">개</span></div>
                </div>
            </div>
        </div>
        <div class="card shadow-sm border-0 overflow-hidden">
            <table class="table table-hover mb-0 align-middle">
                <thead class="table-light">
                    <tr>
                        <th class="text-center" style="width: 60px;">순위</th>
                        <th>기사 제목</th>
                        <th class="text-center" style="width: 120px;">카테고리</th>
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
