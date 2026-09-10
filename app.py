import os
import re
import sys
import sqlite3
import datetime
import urllib.parse
from flask import Flask, render_template_string, request, redirect, url_for

flask_app = Flask(__name__)
flask_app.secret_key = "sisatoday_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "webzine.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            title TEXT,
            lead_text TEXT,
            content TEXT,
            image_url TEXT,
            source_link TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 본래 웹진 완성형 UI 템플릿 (2단 하이라이트 + 하단 목록)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>시사투데이 창</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", sans-serif; background-color: #f4f6f9; color: #222; }
        
        .header { background: #fff; border-bottom: 2px solid #002d5b; padding: 18px 30px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 26px; font-weight: 900; color: #111; text-decoration: none; }
        .logo span { background: #002d5b; color: #fff; padding: 2px 8px; border-radius: 4px; margin-left: 6px; font-size: 22px; }
        .btn-admin { background: #1e293b; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: bold; }

        .nav-bar { background: #fff; padding: 12px 30px; display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid #dce2e8; }
        .nav-item { padding: 7px 16px; text-decoration: none; font-size: 13px; font-weight: bold; border-radius: 20px; color: #4b5563; background: #eef2f6; white-space: nowrap; }
        .nav-item.active { background: #002d5b; color: #fff; }

        .container { max-width: 1100px; margin: 28px auto; padding: 0 16px; }

        /* 상단 2개 대형 하이라이트 사진 카드 */
        .highlights { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 36px; }
        @media (max-width: 768px) { .highlights { grid-template-columns: 1fr; } }
        .hl-card { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 3px 10px rgba(0,0,0,0.06); text-decoration: none; color: inherit; display: flex; flex-direction: column; border: 1px solid #e2e8f0; }
        .hl-img-wrap { width: 100%; height: 240px; background-color: #1e293b; overflow: hidden; }
        .hl-img-wrap img { width: 100%; height: 100%; object-fit: cover; }
        .hl-body { padding: 20px; flex: 1; display: flex; flex-direction: column; }
        .cat-badge { align-self: flex-start; background: #e0f2fe; color: #0284c7; font-size: 12px; font-weight: bold; padding: 4px 8px; border-radius: 4px; margin-bottom: 10px; }
        .hl-title { font-size: 18px; font-weight: 800; line-height: 1.45; color: #111; margin-bottom: 10px; word-break: keep-all; }
        .hl-date { font-size: 12px; color: #888; margin-top: auto; }

        /* 하단 글 목록 게시판 */
        .board-section { background: #fff; border-radius: 8px; padding: 24px 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }
        .board-header { font-size: 18px; font-weight: 800; color: #002d5b; border-bottom: 2px solid #002d5b; padding-bottom: 12px; margin-bottom: 10px; }
        .board-row { display: flex; justify-content: space-between; align-items: center; padding: 14px 4px; border-bottom: 1px solid #f1f5f9; text-decoration: none; color: #333; }
        .board-row:hover { background-color: #f8fafc; }
        .board-row-cat { font-size: 13px; font-weight: bold; color: #0284c7; width: 110px; white-space: nowrap; }
        .board-row-title { font-size: 15px; font-weight: 600; color: #1e293b; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 16px; }
        .board-row:hover .board-row-title { color: #002d5b; text-decoration: underline; }
        .board-row-date { font-size: 13px; color: #94a3b8; white-space: nowrap; }

        /* 본문 상세 페이지 */
        .detail-box { background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .detail-cat { display: inline-block; background: #e0f2fe; color: #0284c7; font-weight: bold; font-size: 13px; padding: 4px 12px; border-radius: 4px; }
        .detail-title { font-size: 28px; font-weight: 800; margin: 16px 0; line-height: 1.4; word-break: keep-all; }
        .detail-date { font-size: 13px; color: #666; border-bottom: 1px solid #eee; padding-bottom: 16px; margin-bottom: 24px; }
        .detail-img { width: 100%; max-height: 460px; object-fit: cover; border-radius: 6px; margin-bottom: 24px; }
        .detail-content { font-size: 16px; line-height: 1.85; color: #333; }
        .detail-content h3 { font-size: 19px; margin: 24px 0 10px 0; color: #002d5b; border-left: 4px solid #002d5b; padding-left: 10px; }
        .lead-quote { background: #f8fafc; border-left: 4px solid #0284c7; padding: 16px; margin-bottom: 24px; font-weight: 600; color: #1e293b; }
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">시사투데이 <span>창</span></a>
        <a href="/admin" class="btn-admin">⚙️ 관리자 홈</a>
    </header>

    <nav class="nav-bar">
        <a href="/" class="nav-item {% if not current_cat %}active{% endif %}">전체</a>
        {% for cat in categories %}
        <a href="/?cat={{ cat }}" class="nav-item {% if current_cat == cat %}active{% endif %}">{{ cat }}</a>
        {% endfor %}
    </nav>

    <main class="container">
        {% if is_detail %}
            <article class="detail-box">
                <span class="detail-cat">{{ article['category'] }}</span>
                <h1 class="detail-title">{{ article['title'] }}</h1>
                <div class="detail-date">발행일시: {{ article['created_at'] }}</div>
                
                {% if article['image_url'] %}
                <img src="{{ article['image_url'] }}" class="detail-img" alt="대표 이미지" onerror="this.style.display='none';">
                {% endif %}

                {% if article['lead_text'] %}
                <div class="lead-quote">{{ article['lead_text'] }}</div>
                {% endif %}

                <div class="detail-content">{{ article['content']|safe }}</div>

                <div style="margin-top: 36px;">
                    <a href="/" class="nav-item active">← 목록으로 돌아가기</a>
                </div>
            </article>
        {% else %}
            <!-- 상단 2단 하이라이트 사진 카드 -->
            {% if highlights %}
            <section class="highlights">
                {% for it in highlights %}
                <a href="/article/{{ it['id'] }}" class="hl-card">
                    <div class="hl-img-wrap">
                        <img src="{{ it['image_url'] if it['image_url'] else 'https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=800' }}" 
                             alt="기사 사진" 
                             onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=800';">
                    </div>
                    <div class="hl-body">
                        <span class="cat-badge">{{ it['category'] }}</span>
                        <div class="hl-title">{{ it['title'] }}</div>
                        <span class="hl-date">발행: {{ it['created_at'][:10] }}</span>
                    </div>
                </a>
                {% endfor %}
            </section>
            {% endif %}

            <!-- 하단 글 목록 게시판 -->
            <section class="board-section">
                <div class="board-header">
                    📁 {% if current_cat %}{{ current_cat }} 뉴스 목록{% else %}최신 기사 목록{% endif %}
                </div>
                {% if list_articles %}
                    {% for it in list_articles %}
                    <a href="/article/{{ it['id'] }}" class="board-row">
                        <div class="board-row-cat">[{{ it['category'] }}]</div>
                        <div class="board-row-title">{{ it['title'] }}</div>
                        <div class="board-row-date">{{ it['created_at'][:10] }}</div>
                    </a>
                    {% endfor %}
                {% else %}
                    <div style="padding: 40px; text-align: center; color: #888;">등록된 기사가 없습니다.</div>
                {% endif %}
            </section>
        {% endif %}
    </main>
</body>
</html>
"""

# ==========================================
# 관리자 UI (/admin)
# ==========================================
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>시사투데이 관리자 시스템</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: "Malgun Gothic", sans-serif; background: #f1f4f8; padding: 20px; }
        .topbar { background: #1e293b; color: #fff; padding: 16px 24px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .topbar a { color: #94a3b8; text-decoration: none; font-weight: bold; }
        .box { background: #fff; border-radius: 8px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
        input, select, textarea { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; }
        textarea { height: 160px; }
        .btn-submit { background: #0284c7; color: #fff; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: left; }
        th { background: #f8fafc; }
        .btn-del { background: #ef4444; color: #fff; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 12px; }
    </style>
</head>
<body>
    <div class="topbar">
        <h2>⚙️ 시사투데이 창 웹진 관리자</h2>
        <a href="/">← 웹진 홈으로 돌아가기</a>
    </div>

    <div class="box">
        <h3>📝 새 기사 등록</h3>
        <form action="/admin/add" method="POST">
            <select name="category" required>
                {% for cat in categories %}
                <option value="{{ cat }}">{{ cat }}</option>
                {% endfor %}
            </select>
            <input type="text" name="title" placeholder="기사 제목" required>
            <input type="text" name="image_url" placeholder="대표 이미지 URL (https://...)">
            <input type="text" name="lead_text" placeholder="기사 요약 리드문">
            <textarea name="content" placeholder="기사 본문 내용 (HTML 허용)" required></textarea>
            <button type="submit" class="btn-submit">기사 등록</button>
        </form>
    </div>

    <div class="box">
        <h3>📑 등록된 전체 기사 목록 (총 {{ articles|length }}편)</h3>
        <table>
            <thead>
                <tr>
                    <th style="width: 50px;">ID</th>
                    <th style="width: 120px;">카테고리</th>
                    <th>제목</th>
                    <th style="width: 140px;">등록일</th>
                    <th style="width: 80px; text-align: center;">관리</th>
                </tr>
            </thead>
            <tbody>
                {% for it in articles %}
                <tr>
                    <td>{{ it['id'] }}</td>
                    <td><b>{{ it['category'] }}</b></td>
                    <td><a href="/article/{{ it['id'] }}" target="_blank" style="text-decoration:none; color:#111;">{{ it['title'] }}</a></td>
                    <td>{{ it['created_at'][:16] }}</td>
                    <td style="text-align: center;">
                        <a href="/admin/delete/{{ it['id'] }}" class="btn-del" onclick="return confirm('삭제하시겠습니까?');">삭제</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

# ==========================================
# 라우트 핸들러
# ==========================================
@flask_app.route("/")
def index():
    cat = request.args.get("cat", "").strip()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
    categories = [r['category'] for r in cur.fetchall()]

    if cat:
        cur.execute("SELECT * FROM articles WHERE category = ? ORDER BY id DESC", (cat,))
    else:
        cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()
    conn.close()

    highlights = articles[:2]
    list_articles = articles[2:] if len(articles) > 2 else articles

    return render_template_string(
        HTML_TEMPLATE,
        highlights=highlights,
        list_articles=list_articles,
        categories=categories,
        current_cat=cat,
        is_detail=False
    )

@flask_app.route("/article/<int:article_id>")
def article_detail(article_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
    categories = [r['category'] for r in cur.fetchall()]

    cur.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    article = cur.fetchone()
    conn.close()

    if not article:
        return redirect(url_for("index"))

    return render_template_string(
        HTML_TEMPLATE,
        article=article,
        categories=categories,
        current_cat=article['category'],
        is_detail=True
    )

@flask_app.route("/admin")
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()

    cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
    categories = [r['category'] for r in cur.fetchall()]
    if not categories:
        categories = ["정치/시사", "경제/주식", "건강/복지", "생활정보"]
    conn.close()

    return render_template_string(ADMIN_TEMPLATE, articles=articles, categories=categories)

@flask_app.route("/admin/add", methods=["POST"])
def admin_add():
    category = request.form.get("category")
    title = request.form.get("title")
    image_url = request.form.get("image_url", "").strip()
    lead_text = request.form.get("lead_text", "").strip()
    content = request.form.get("content")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO articles (category, title, lead_text, content, image_url, source_link, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (category, title, lead_text, content, image_url, "", now_str))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

@flask_app.route("/admin/delete/<int:article_id>")
def admin_delete(article_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))


# ==========================================
# Render Uvicorn 호환 내장 ASGI 어댑터
# ==========================================
async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            msg = await receive()
            if msg['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            elif msg['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return

    if scope['type'] != 'http':
        return

    import io
    body = b""
    while True:
        msg = await receive()
        body += msg.get('body', b'')
        if not msg.get('more_body', False):
            break

    environ = {
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': scope.get('scheme', 'http'),
        'wsgi.input': io.BytesIO(body),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'REQUEST_METHOD': scope['method'],
        'SCRIPT_NAME': '',
        'PATH_INFO': urllib.parse.unquote(scope['path']),
        'QUERY_STRING': scope['query_string'].decode('latin-1'),
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '80',
    }

    for name, val in scope.get('headers', []):
        k = name.decode('latin-1').lower()
        v = val.decode('latin-1')
        if k == 'content-type':
            environ['CONTENT_TYPE'] = v
        elif k == 'content-length':
            environ['CONTENT_LENGTH'] = v
        else:
            environ['HTTP_' + k.upper().replace('-', '_')] = v

    status_code = 200
    headers = []

    def start_response(status, resp_headers, exc_info=None):
        nonlocal status_code, headers
        status_code = int(status.split(' ')[0])
        headers = [(h[0].lower().encode('latin-1'), h[1].encode('latin-1')) for h in resp_headers]

    resp = flask_app(environ, start_response)
    resp_body = b''.join(resp)

    await send({'type': 'http.response.start', 'status': status_code, 'headers': headers})
    await send({'type': 'http.response.body', 'body': resp_body})


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
