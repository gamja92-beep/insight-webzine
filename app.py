import os
import sqlite3
import json
import time
from datetime import datetime

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
import uvicorn

# ==========================================================
# 1. 시스템 설정
# ==========================================================
GEMINI_API_KEY = "AIzaSyDUT1q_c4QcAGG7rzqZWTmsWvwXXvqH6zI"
MODEL_NAME = "gemini-2.5-flash"  # 할당량이 넉넉하고 빠른 모델로 최적화
DB_FILE = "webzine.db"

CATEGORIES = [
    {"slug": "all", "name": "전체보기"},
    {"slug": "health", "name": "🌿 시니어 건강/식품"},
    {"slug": "welfare", "name": "💰 정부 지원금/복지 혜택"},
    {"slug": "economy", "name": "📊 생활 경제/세무 상식"},
    {"slug": "culture", "name": "🎨 문화/예술"}
]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_slug TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            content TEXT,
            tags TEXT,
            source_name TEXT,
            created_at TEXT,
            views INTEGER DEFAULT 0,
            status TEXT DEFAULT 'published'
        )
    ''')
    conn.commit()
    conn.close()

init_db()
app = FastAPI(title="인사이트 데일리 웹진")

# ==========================================================
# 2. SEO & CTR 최적화 AI 기사 생성 엔진 (429 자동 재시도 탑재)
# ==========================================================
def generate_rich_article(topic_or_raw: str, category_name: str, source_name: str, max_retries: int = 3):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
너는 20년 경력의 디지털 뉴스 수석 에디터이자 포털(네이버/구글) 검색엔진 최적화(SEO) 수석 컨설턴트야.
제공된 [주제/원문]을 분석하여 검색 포털 1페이지 상단에 노출되고 클릭률(CTR)이 폭발하는 고품질 전문 신문 기사를 작성해줘.

[작성 가이드라인 - SEO 및 CTR 극대화 규칙]

1. 🎯 [기사 제목 (Title)]:
   - 검색자가 지나칠 수 없도록 '숫자', '손실 방지/경고', '구체적 혜택', '연도(2026)'를 조합할 것.
   - 제목 길이: 28자~40자 내외로 정제할 것.

2. 📌 [3줄 핵심 브리핑 (Summary)]:
   - 구글 피처드 스니펫에 채택되도록 바쁜 독자가 결론을 5초 만에 파악할 수 있는 3개 핵심 문장으로 작성할 것.

3. 📝 [본문 구조화 (HTML Content)]:
   - `<h2>`, `<h3>`, `<p>`, `<blockquote>`, `<ul>`, `<li>`, `<table>` 태그를 적극 활용할 것.
   - [섹션 1]: 문제 제기 및 배경 (왜 지금 이 정보가 중요한가?)
   - [섹션 2]: 핵심 실천 가이드 및 신청 방법
   - [섹션 3]: 한눈에 보는 요약 비교표 (HTML `<table>` 태그) 또는 체크리스트
   - [섹션 4]: 💡 자주 묻는 질문 FAQ (실제 궁금해하는 2~3개의 Q&A)

4. 🏷️ [핵심 검색 키워드 (Tags)]:
   - 포털 연관검색어 형태의 롱테일 키워드 4개를 쉼표(,)로 구분하여 제시.

[주제/원문]: {topic_or_raw}
[카테고리]: {category_name}
[출처 기관]: {source_name}

반드시 아래 필드명을 가진 JSON 형식으로만 응답할 것:
- title: (문자열) 고클릭률 최적화 제목
- summary: (문자열) 핵심 3줄 요약 (줄바꿈 포함)
- html_content: (문자열) 완벽히 구조화된 본문 HTML
- tags: (문자열) 검색 키워드 4개
"""
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text.strip())
        except Exception as e:
            err_msg = str(e)
            print(f"[!] AI 생성 시도 ({attempt}/{max_retries}) 오류: {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print(f"⏳ API 호출 제한(429) 감지. 15초 대기 후 자동 재시도합니다...")
                time.sleep(15)
            else:
                time.sleep(3)
                
    return None

# ==========================================================
# 3. 웹 페이지 UI 템플릿
# ==========================================================
HTML_LAYOUT = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta name="naver-site-verification" content="2be1d8c699f2db6d04ee4bbe598876b754cf1c10" />
    <meta name="google-site-verification" content="FuUKAJVoYVh_WbGkmCXJX2YwcIayUpBDGpBwLu7vlkU" />
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__PAGE_TITLE__ - 인사이트 데일리 웹진</title>
    <style>
        :root { --primary: #1e3a8a; --accent: #dc2626; --bg: #f8fafc; --text: #1e293b; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "맑은 고딕", sans-serif; margin: 0; background: var(--bg); color: var(--text); line-height: 1.75; }
        header { background: #ffffff; border-bottom: 2px solid #e2e8f0; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 6px rgba(0,0,0,0.04); }
        .header-top { max-width: 1100px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; }
        .logo { font-size: 26px; font-weight: 900; color: var(--primary); text-decoration: none; letter-spacing: -1px; }
        .logo span { color: var(--accent); }
        .btn-admin { background: #1e3a8a; color: #ffffff; text-decoration: none; font-weight: bold; font-size: 14px; padding: 8px 16px; border-radius: 6px; }
        
        .nav-bar { background: #f1f5f9; border-top: 1px solid #e2e8f0; }
        .nav-inner { max-width: 1100px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 20px; }
        
        .tab-btn { color: #334155; font-weight: 700; font-size: 15px; padding: 8px 18px; border-radius: 20px; background: #ffffff; border: 1px solid #cbd5e1; cursor: pointer; transition: all 0.2s; outline: none; }
        .tab-btn:hover { color: #ffffff; background: #3b82f6; border-color: #3b82f6; }
        .tab-btn.active { background: var(--primary) !important; color: #ffffff !important; border-color: var(--primary) !important; }
        
        .container { max-width: 1100px; margin: 30px auto; padding: 0 20px; min-height: 65vh; }
        .article-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 24px; }
        .card { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.04); display: flex; flex-direction: column; transition: transform 0.2s; }
        .card:hover { transform: translateY(-4px); }
        .card-body { padding: 22px; display: flex; flex-direction: column; flex-grow: 1; }
        .badge { display: inline-block; align-self: flex-start; background: #e0e7ff; color: var(--primary); font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; margin-bottom: 12px; cursor: pointer; }
        .card-title { font-size: 19px; font-weight: bold; margin: 0 0 10px 0; line-height: 1.45; }
        .card-title a { color: var(--text); text-decoration: none; }
        .card-title a:hover { color: var(--primary); }
        .card-desc { font-size: 14px; color: #64748b; margin-bottom: 16px; flex-grow: 1; white-space: pre-line; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
        .card-meta { font-size: 12px; color: #94a3b8; display: flex; justify-content: space-between; border-top: 1px solid #f1f5f9; padding-top: 12px; margin-top: auto; }
        
        .article-detail { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 40px; }
        .detail-title { font-size: 28px; font-weight: 800; line-height: 1.35; margin: 10px 0 15px 0; color: #0f172a; }
        .detail-meta { color: #64748b; font-size: 14px; border-bottom: 1px solid #e2e8f0; padding-bottom: 20px; margin-bottom: 25px; }
        .summary-box { background: #f0fdf4; border-left: 5px solid #22c55e; padding: 20px 24px; border-radius: 0 8px 8px 0; margin-bottom: 35px; font-size: 16px; color: #166534; line-height: 1.8; }
        .summary-box strong { font-size: 17px; display: block; margin-bottom: 8px; }
        .article-content { font-size: 17px; color: #334155; }
        .article-content h2 { color: var(--primary); font-size: 22px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 40px; }
        .article-content h3 { font-size: 18px; color: #0f172a; margin-top: 25px; }
        .article-content blockquote { background: #f8fafc; border-left: 4px solid #94a3b8; margin: 24px 0; padding: 14px 20px; font-style: italic; color: #475569; }
        
        .article-content table { width: 100%; border-collapse: collapse; margin: 25px 0; font-size: 15px; }
        .article-content th, .article-content td { border: 1px solid #cbd5e1; padding: 12px 14px; text-align: left; }
        .article-content th { background: #f1f5f9; font-weight: bold; color: #1e293b; }
        .article-content tr:nth-child(even) { background: #f8fafc; }

        .source-tag { background: #f1f5f9; border-radius: 8px; padding: 16px; margin-top: 40px; font-size: 13px; color: #64748b; }
        .ad-box { background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; text-align: center; padding: 22px; margin: 25px 0; color: #94a3b8; font-size: 13px; font-weight: bold; }
        
        .admin-box { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 32px; max-width: 720px; margin: 0 auto; }
        .form-group { margin-bottom: 18px; }
        .form-group label { display: block; font-weight: bold; margin-bottom: 6px; font-size: 14px; }
        .form-control { width: 100%; padding: 11px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; font-size: 15px; }
        textarea.form-control { height: 160px; line-height: 1.5; }
        .btn-submit { background: var(--primary); color: #fff; border: none; padding: 13px 24px; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; width: 100%; }
        footer { background: #0f172a; color: #94a3b8; text-align: center; padding: 35px 20px; margin-top: 60px; font-size: 13px; }
    </style>
</head>
<body>
    <header>
        <div class="header-top">
            <a href="/" class="logo">인사이트<span>웹진</span></a>
            <a href="/admin" class="btn-admin">⚡ SEO 기사 즉시 발행</a>
        </div>
        <div class="nav-bar">
            <div class="nav-inner">
                <button type="button" class="tab-btn active" onclick="switchCategory('all', this)">전체보기</button>
                <button type="button" class="tab-btn" onclick="switchCategory('health', this)">🌿 시니어 건강/식품</button>
                <button type="button" class="tab-btn" onclick="switchCategory('welfare', this)">💰 정부 지원금/복지 혜택</button>
                <button type="button" class="tab-btn" onclick="switchCategory('economy', this)">📊 생활 경제/세무 상식</button>
                <button type="button" class="tab-btn" onclick="switchCategory('culture', this)">🎨 문화/예술</button>
            </div>
        </div>
    </header>
    <div class="container">
        __BODY_CONTENT__
    </div>
    <footer>
        <p>© 2026 인사이트 데일리 웹진. All rights reserved.</p>
    </footer>

    <script>
    function switchCategory(targetSlug, btnElement) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        if (btnElement) {
            btnElement.classList.add('active');
        } else {
            const b = document.querySelector(`button[onclick*="'${targetSlug}'"]`);
            if (b) b.classList.add('active');
        }

        const cards = document.querySelectorAll('.card');
        let count = 0;

        cards.forEach(card => {
            const slug = card.getAttribute('data-slug');
            if (targetSlug === 'all' || slug === targetSlug) {
                card.style.display = 'flex';
                count++;
            } else {
                card.style.display = 'none';
            }
        });

        const titleEl = document.getElementById('section-title');
        if (titleEl) {
            const label = btnElement ? btnElement.innerText : '기사';
            titleEl.innerText = `🔥 ${label} (${count}개)`;
        }
    }
    </script>
</body>
</html>
"""

# ==========================================================
# 4. 라우터 설정
# ==========================================================
@app.get("/", response_class=HTMLResponse)
async def home_page():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, cat_slug, category, title, summary, created_at, views FROM articles ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    cards_html = ""
    for r in rows:
        art_id, cat_slug, category, title, summary, created_at, views = r
        first_sum = (summary or "").split("\n")[0]
        created_date = (created_at or "")[:10]
        cards_html += f"""
        <div class="card" data-slug="{cat_slug}">
            <div class="card-body">
                <span class="badge" onclick="switchCategory('{cat_slug}')">{category}</span>
                <h3 class="card-title"><a href="/article/{art_id}">{title}</a></h3>
                <p class="card-desc">{first_sum}</p>
                <div class="card-meta">
                    <span>📅 {created_date}</span>
                    <span>👁️ {views}</span>
                </div>
            </div>
        </div>
        """

    if not rows:
        cards_html = "<p style='text-align:center; grid-column: 1/-1; padding: 40px; color:#64748b;'>기사가 없습니다. [⚡ SEO 기사 즉시 발행] 버튼으로 기사를 등록해 보세요.</p>"

    body = f"""
    <div style="margin-bottom: 22px;">
        <h2 id="section-title" style="font-size: 22px; font-weight: 800; margin: 0;">🔥 전체보기 ({len(rows)}개)</h2>
    </div>
    <div class="ad-box">📢 [Google AdSense] 상단 반응형 배너 광고 영역</div>
    <div class="article-grid">
        {cards_html}
    </div>
    """
    html = HTML_LAYOUT.replace("__PAGE_TITLE__", "인사이트 데일리 웹진").replace("__BODY_CONTENT__", body)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/article/{article_id}", response_class=HTMLResponse)
async def article_detail(article_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE articles SET views = views + 1 WHERE id = ?", (article_id,))
    conn.commit()

    c.execute("SELECT category, title, summary, content, tags, source_name, created_at, views, cat_slug FROM articles WHERE id = ?", (article_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("기사를 찾을 수 없습니다.", status_code=404)

    category, title, summary, content, tags, source_name, created_at, views, cat_slug = row
    summary_items = [f"<li>{s.strip()}</li>" for s in (summary or "").split("\n") if s.strip()]
    summary_html = "".join(summary_items) if summary_items else "<li>본문 내용을 확인해 주세요.</li>"

    body = f"""
    <div class="article-detail">
        <span class="badge">{category}</span>
        <h1 class="detail-title">{title}</h1>
        <div class="detail-meta">
            <span>발행일: {created_at}</span> &nbsp;|&nbsp; 
            <span>조회수: {views}</span> &nbsp;|&nbsp;
            <span>출처: {source_name}</span>
        </div>

        <div class="ad-box">📢 [Google AdSense] 본문 상단 반응형 광고</div>

        <div class="summary-box">
            <strong>📌 핵심 요약 브리핑 (스니펫 가이드)</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px;">
                {summary_html}
            </ul>
        </div>

        <div class="article-content">
            {content or ""}
        </div>

        <div class="ad-box">📢 [Google AdSense] 본문 하단 광고 영역</div>

        <div class="source-tag">
            <p style="margin:0;"><strong>💡 출처 안내:</strong> 본 기사는 {source_name}의 공식 자료를 기반으로 AI 심층 분석을 거쳐 작성되었습니다.</p>
            <p style="margin:6px 0 0 0;"><strong>SEO 키워드 태그:</strong> {tags or ""}</p>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <a href="/" style="display:inline-block; padding: 10px 20px; background: #e2e8f0; color: #334155; text-decoration:none; border-radius: 6px; font-weight: bold;">← 전체 기사 목록으로</a>
        </div>
    </div>
    """
    html = HTML_LAYOUT.replace("__PAGE_TITLE__", str(title)).replace("__BODY_CONTENT__", body)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    options_html = "".join([f'<option value="{c["slug"]}">{c["name"]}</option>' for c in CATEGORIES if c["slug"] != "all"])
    body = f"""
    <div class="admin-box">
        <h2 style="margin-top:0; color: var(--primary);">⚡ AI 고품질 SEO 기사 즉시 발행</h2>
        <p style="color: #64748b; font-size: 14px; margin-bottom: 20px;">
            핵심 키워드나 원문 텍스트를 입력하면 AI 에디터가 <b>포털 검색 상위 노출 규격(고클릭률 제목 + 요약 스니펫 + 비교표 + FAQ)</b>에 맞춰 기사를 즉시 작성합니다.
        </p>
        
        <form action="/admin/create" method="post">
            <div class="form-group">
                <label>카테고리 선택</label>
                <select name="cat_slug" class="form-control">
                    {options_html}
                </select>
            </div>
            <div class="form-group">
                <label>출처명 (신뢰도 향상용)</label>
                <input type="text" name="source_name" class="form-control" value="과학기술정보통신부 / 보건복지부 복지로" required>
            </div>
            <div class="form-group">
                <label>원문 텍스트 또는 주제 키워드</label>
                <textarea name="raw_text" class="form-control" placeholder="기사 작성에 참고할 내용을 입력하세요..." required>2026년 65세 이상 기초연금 수급자 통신비 감면 자격 요건, 월 최대 12,100원 할인 혜택, 주민센터 및 복지로/통신사 114 간편 신청방법</textarea>
            </div>
            <button type="submit" class="btn-submit">🚀 고클릭률 SEO 기사 즉시 생성 및 발행</button>
        </form>
    </div>
    """
    html = HTML_LAYOUT.replace("__PAGE_TITLE__", "SEO 기사 등록").replace("__BODY_CONTENT__", body)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.post("/admin/create")
async def create_article(cat_slug: str = Form(...), source_name: str = Form(...), raw_text: str = Form(...)):
    slug_to_name = {c["slug"]: c["name"] for c in CATEGORIES}
    category_name = slug_to_name.get(cat_slug, "기타")
    
    art_data = generate_rich_article(raw_text, category_name, source_name)
    if not art_data:
        return HTMLResponse("""
        <div style="text-align:center; padding:50px; font-family:sans-serif;">
            <h2>⏳ AI API 요청 한도에 도달했습니다.</h2>
            <p style="color:#64748b;">구글 무료 API 일일/분당 할당량 초과 상태입니다. 약 1~2분 후 다시 시도해 주세요.</p>
            <a href="/admin" style="display:inline-block; margin-top:20px; padding:10px 20px; background:#1e3a8a; color:#fff; text-decoration:none; border-radius:6px; font-weight:bold;">← 관리자 페이지로 돌아가기</a>
        </div>
        """, status_code=429)
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO articles (cat_slug, category, title, summary, content, tags, source_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        cat_slug,
        category_name,
        art_data.get("title", "정보 안내"),
        art_data.get("summary", ""),
        art_data.get("html_content", ""),
        art_data.get("tags", ""),
        source_name,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    new_id = c.lastrowid
    conn.close()

    return RedirectResponse(url=f"/article/{new_id}", status_code=303)

# ==========================================================
# 5. 메인 실행 부
# ==========================================================
if __name__ == "__main__":
    print("📰 인사이트 웹진 SEO 강화 버전 가동: http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
