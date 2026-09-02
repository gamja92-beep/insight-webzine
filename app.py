import sqlite3
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
import os

app = FastAPI()

# 환경 변수에서 API 키 불러오기
API_KEY = os.environ.get("API_KEY", "")
MODEL_NAME = "gemini-3.6-flash"

client = genai.Client(api_key=API_KEY)

# DB 초기화
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# 메인 페이지
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, created_at FROM articles ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    articles = [{"id": r[0], "title": r[1], "content": r[2], "created_at": r[3]} for r in rows]

    html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>인사이트 웹진</title>
        <style>
            body { font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f9f9f9; color: #333; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            .admin-link { display: inline-block; margin-bottom: 20px; padding: 10px 15px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; }
            .admin-link:hover { background: #2980b9; }
            .article { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            .article h2 { margin-top: 0; color: #2980b9; }
            .date { font-size: 0.85em; color: #888; margin-bottom: 10px; }
            .content { line-height: 1.6; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <h1>📰 인사이트 웹진</h1>
        <a href="/admin" class="admin-link">⚙️ 관리자 페이지로 이동</a>
        <hr style="border:0; border-top:1px solid #ddd; margin: 20px 0;">
    """
    if not articles:
        html += "<p>아직 발행된 기사가 없습니다. 관리자 페이지에서 기사를 생성해 보세요!</p>"
    else:
        for art in articles:
            html += f"""
            <div class="article">
                <h2>{art['title']}</h2>
                <div class="date">발행일시: {art['created_at']}</div>
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
            button { background: #27ae60; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; }
            button:hover { background: #219653; }
            .manual-btn { background: #2980b9; }
            .manual-btn:hover { background: #1f618d; }
            input[type="text"], textarea { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }
            textarea { height: 200px; resize: vertical; }
            label { font-weight: bold; color: #34495e; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <h1>⚙️ 웹진 관리자 스튜디오</h1>
        
        <div class="box">
            <h3>🤖 AI 자동 SEO 기사 발행</h3>
            <p>구글 제미니가 최신 트렌드를 분석해 고품질 SEO 기사를 즉시 작성합니다.</p>
            <form action="/admin/create" method="post">
                <button type="submit">🚀 AI 기사 즉시 생성 및 발행</button>
            </form>
        </div>

        <div class="box">
            <h3>✍️ 직접 글 작성하기 (수동 발행)</h3>
            <p>원장님의 통찰이 담긴 오리지널 글을 직접 작성하여 등록할 수 있습니다.</p>
            <form action="/admin/manual-create" method="post">
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목을 입력하세요" required>
                
                <label>기사 내용</label>
                <textarea name="content" placeholder="내용을 자유롭게 작성하세요..." required></textarea>
                
                <button type="submit" class="manual-btn">📝 직접 작성한 글 발행하기</button>
            </form>
        </div>
    </body>
    </html>
    """

# AI 자동 생성
@app.post("/admin/create")
def create_article():
    prompt = "최근 주목받는 AI 기술과 트렌드에 대한 흥미롭고 전문적인 SEO 최적화 뉴스 기사를 작성해줘. 제목과 본문을 포함해줘."
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        text = response.text
        lines = text.split("\n", 1)
        title = lines[0].replace("#", "").strip() if len(lines) > 0 else "AI 트렌드 뉴스"
        content = lines[1].strip() if len(lines) > 1 else text

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO articles (title, content) VALUES (?, ?)", (title, content))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"AI 생성 오류: {e}")

    return RedirectResponse(url="/", status_code=303)

# 수동 글 작성
@app.post("/admin/manual-create")
def manual_create_article(title: str = Form(...), content: str = Form(...)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO articles (title, content) VALUES (?, ?)", (title, content))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)
