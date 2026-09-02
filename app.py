import os
import sqlite3
import json
import urllib.request
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
    c.execute("CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, category TEXT NOT NULL, cat_slug TEXT DEFAULT 'welfare', summary TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

init_db()

def call_gemini_api(category, topic):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    fallback_title = topic
    fallback_summary = f"1. {topic} 핵심 정보 요약.\n2. 세부 기준 및 절차 안내.\n3. 필수 주의사항."
    fallback_content = f"<h2>1. {topic} - 개요</h2><p>{topic}에 대한 상세 가이드입니다.</p>"

    if not api_key:
        return fallback_title, fallback_summary, fallback_content

    prompt = f"시니어 전문 에디터입니다. 주제 '{topic}'(카테고리: {category})에 대한 1500자 이상의 상세 가이드를 JSON으로 작성해주세요. 포맷: {{\"title\": \"제목\", \"summary\": \"요약3줄\", \"content\": \"HTML본문\"}}"

    for m in ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=25) as res:
                data = json.loads(json.loads(res.read().decode("utf-8"))["candidates"][0]["content"]["parts"][0]["text"].strip().replace("```json", "").replace("```", "").strip())
                return data.get("title", topic), data.get("summary", fallback_summary), data.get("content", fallback_content)
        except Exception:
            continue
    return fallback_title, fallback_summary, fallback_content

def render_page(title, content_html):
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 인사이트 데일리</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        body {{ background: #f8fafc; font-family: sans-serif; color: #1e293b; }}
        .hero {{ background: linear-gradient(135deg, #0f172a, #1e3a8a); color: white; padding: 40px 0; margin-bottom: 25px; text-align: center; }}
        .art-body {{ font-size: 1.15rem; line-height: 2.0; background: #fff; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0; }}
        .art-body h2 {{ font-size: 1.35rem; font-weight: 700; margin-top: 2rem; border-left: 5px solid #2563eb; padding-left: 10px; color: #0f172a; }}
        .art-body table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        .art-body th, .art-body td {{ border: 1px solid #e2e8f0; padding: 10px; }}
    </style>
</head>
<body>
    <nav class="navbar navbar-light bg-white border-bottom shadow-sm">
        <div class="container d-flex justify-content-between">
            <a class="navbar-brand fw-bold text-primary text-decoration-none" href="/"><i class="fa-solid fa-newspaper me-2"></i>인사이트 데일리</a>
            <div>
                <a href="/write" class="btn btn-primary btn-sm fw-semibold me-2"><i class="fa-solid fa-pen me-1"></i>수동 기사 발행</a>
                <a href="/admin/stats" class="btn btn-outline-secondary btn-sm"><i class="fa-solid fa-chart-line"></i> 통계</a>
            </div>
        </div>
    </nav>
    <div class="container">{content_html}</div>
    <footer class="text-center py-4 text-muted small border-top bg-white mt-5">© 인사이트 데일리. All Rights Reserved.</footer>
</body>
</html>"""
    return HTMLResponse(html)

@app.get("/")
def index(cat: str = ""):
    conn = get_db()
    c = conn.cursor()
    if cat:
        c.execute("SELECT * FROM articles WHERE category LIKE ? ORDER BY id DESC", (f'%{cat}%',))
    else:
        c.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = c.fetchall()
    conn.close()

    cards = "".join([f"""
        <div class="col-md-4 mb-4">
            <div class="card border-0 shadow-sm p-3 h-100 bg-white rounded-3">
                <span class="badge bg-primary-subtle text-primary mb-2 align-self-start">{r['category']}</span>
                <h5 class="fw-bold mb-2"><a href="/article/{r['id']}" class="text-decoration-none text-dark">{r['title']}</a></h5>
                <p class="text-secondary small flex-grow-1">{r['summary']}</p>
                <div class="d-flex justify-content-between align-items-center pt-2 border-top">
                    <small class="text-muted"><i class="fa-regular fa-eye me-1"></i>{r['views']}회</small>
                    <a href="/article/{r['id']}" class="btn btn-outline-primary btn-sm">읽기 →</a>
                </div>
            </div>
        </div>
    """ for r in articles]) or '<div class="col-12 text-center py-5 text-muted">등록된 기사가 없습니다.</div>'

    body = f"""
    <div class="hero rounded-3 mb-4"><h1 class="fw-bold">인사이트 데일리 웹진</h1><p class="text-white-50 mb-0">시니어 복지 · 실전 재테크 · 건강 가이드</p></div>
    <div class="d-flex justify-content-center gap-2 mb-4 flex-wrap">
        <a href="/" class="btn btn-outline-dark btn-sm rounded-pill px-3 {'active' if not cat else ''}">전체보기</a>
        <a href="/?cat=복지" class="btn btn-outline-dark btn-sm rounded-pill px-3 {'active' if cat=='복지' else ''}">정부지원·복지</a>
        <a href="/?cat=경제" class="btn btn-outline-dark btn-sm rounded-pill px-3 {'active' if cat=='경제' else ''}">생활경제·재테크</a>
        <a href="/?cat=건강" class="btn btn-outline-dark btn-sm rounded-pill px-3 {'active' if cat=='건강' else ''}">시니어건강</a>
    </div>
    <div class="row">{cards}</div>"""
    return render_page("홈", body)

@app.get("/article/{art_id}")
def view_article(art_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE articles SET views = views + 1 WHERE id = ?", (art_id,))
    c.execute("SELECT * FROM articles WHERE id = ?", (art_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    if not row:
        return HTMLResponse("기사를 찾을 수 없습니다.", status_code=404)

    content = f"""
    <div class="py-4" style="max-width: 820px; margin: 0 auto;">
        <span class="badge bg-primary-subtle text-primary mb-2">{row['category']}</span>
        <h1 class="fw-bold text-dark mb-3">{row['title']}</h1>
        <p class="text-muted small mb-4">{row['created_at']}</p>
        <div class="p-3 bg-white border rounded-3 mb-4 shadow-sm">
            <div class="fw-bold text-primary mb-1"><i class="fa-solid fa-bolt me-1"></i>핵심 요약</div>
            <div class="text-secondary small" style="white-space: pre-line;">{row['summary']}</div>
        </div>
        <article class="art-body shadow-sm mb-4">{row['content']}</article>
        <a href="/" class="btn btn-primary rounded-pill px-4">목록으로</a>
    </div>"""
    return render_page(row['title'], content)

@app.get("/write")
def write_form():
    body = """
    <div class="py-5" style="max-width: 500px; margin: 0 auto;">
        <div class="card p-4 shadow-sm border-0 rounded-3 bg-white">
            <h4 class="fw-bold mb-3"><i class="fa-solid fa-pen text-primary me-2"></i>기사 수동 발행</h4>
            <form method="get" action="/create" onsubmit="this.btn.disabled=true; this.btn.innerText='AI 기사 작성 중...';">
                <div class="mb-3">
                    <label class="form-label fw-bold small">카테고리</label>
                    <select name="category" class="form-select">
                        <option value="정부 지원금/복지 혜택">정부 지원금/복지 혜택</option>
                        <option value="생활 경제/세무 상식">생활 경제/세무 상식</option>
                        <option value="시니어 건강/식품">시니어 건강/식품</option>
                        <option value="문화/예술">문화/예술</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold small">기사 주제</label>
                    <input type="text" name="topic" class="form-control" placeholder="예: 장애인 복지카드 발급방법" required>
                </div>
                <button type="submit" name="btn" class="btn btn-primary w-100 py-2 fw-bold">발행하기</button>
            </form>
        </div>
    </div>"""
    return render_page("기사 작성", body)

@app.get("/create")
def create_article(category: str = "", topic: str = ""):
    if not topic:
        return RedirectResponse(url="/", status_code=303)
    title, summary, content = call_gemini_api(category, topic)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO articles (title, category, summary, content, created_at, views, likes) VALUES (?, ?, ?, ?, ?, 0, 0)", (title, category, summary, content, now))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/article/{new_id}", status_code=303)

@app.get("/admin/stats")
def admin_stats(pw: str = ""):
    if pw != ADMIN_PW:
        return render_page("로그인", '<div class="py-5 text-center" style="max-width:300px; margin:0 auto;"><form method="get"><input type="password" name="pw" class="form-control mb-2" placeholder="비밀번호" required><button class="btn btn-primary w-100">접속</button></form></div>')
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM articles ORDER BY views DESC")
    rows = c.fetchall()
    conn.close()
    tr = "".join([f"<tr><td>{r['id']}</td><td><a href='/article/{r['id']}'>{r['title']}</a></td><td>{r['category']}</td><td>{r['views']}회</td></tr>" for r in rows])
    return render_page("통계", f'<div class="py-4"><h3>통계</h3><table class="table table-bordered bg-white mt-3"><thead><tr><th>ID</th><th>제목</th><th>분류</th><th>조회수</th></tr></thead><tbody>{tr}</tbody></table></div>')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
