import os
import sqlite3
import random
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

def generate_clean_article(category: str, topic: str):
    title = topic
    summary = (
        f"1. {topic}에 대한 시니어 맞춤형 핵심 실전 가이드.\n"
        f"2. 일상생활에서 즉시 적용 가능한 단계별 상세 절차 수록.\n"
        f"3. 불이익을 방지하기 위한 전문가 필수 주의사항 안내."
    )
    content = f"""
    <h2>1. {topic} - 주요 배경 및 핵심 필요성</h2>
    <p><strong>{topic}</strong>에 대해 5060 시니어 독자들이 가장 궁금해하시는 핵심 정보와 꼭 알아두어야 할 기준을 상세히 안내해 드립니다. 본 가이드는 복잡한 절차를 줄이고 실생활에서 즉시 활용할 수 있도록 작성되었습니다.</p>
    
    <h2>2. 한눈에 비교하는 기준 및 주요 혜택</h2>
    <table class="table table-bordered my-3">
        <thead class="table-light">
            <tr><th>구분</th><th>주요 내용 및 지원 기준</th><th>비고 및 참고사항</th></tr>
        </thead>
        <tbody>
            <tr><td>기본 적용 대상</td><td>만 65세 이상 및 관련 요건 충족 가구</td><td>개인별 세부 조건에 따라 상이</td></tr>
            <tr><td>주요 혜택</td><td>맞춤형 지원 및 비용 절감 효과</td><td>공식 접수처를 통한 확인 필수</td></tr>
        </tbody>
    </table>

    <h2>3. 실패 없는 단계별 실전 신청 및 실행 절차</h2>
    <ol>
        <li><strong>사전 자격 확인:</strong> 본인의 현재 조건이 해당 연도 기준에 부합하는지 꼼꼼히 체크합니다.</li>
        <li><strong>필수 서류 및 준비물 구비:</strong> 신분증 및 관련 증빙 서류를 빠짐없이 준비합니다.</li>
        <li><strong>공식 접수 및 신청:</strong> 관할 기관 방문 또는 공식 온라인 채널을 통해 최종 접수를 완료합니다.</li>
    </ol>

    <h2>4. 전문가 주의사항 및 알짜배기 꿀팁</h2>
    <ul>
        <li>신청 기간이나 마감 기한을 넘기면 소급 적용이 어려울 수 있으니 사전 일정을 반드시 확인하세요.</li>
        <li>유사한 제도가 많으므로 본인에게 가장 유리한 혜택을 선택하여 중복 신청 가능 여부를 문의하시기 바랍니다.</li>
    </ul>
    """
    return title, summary, content

def save_article_secure(category: str, topic: str):
    cat_slug = get_cat_slug(category)
    title, summary, content = generate_clean_article(category, topic)
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
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
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
    safe_title = str(title) if title else "인사이트 데일리"
    safe_body = str(body) if body else ""
    html_output = BASE_HTML.replace("__TITLE__", safe_title).replace("__BODY__", safe_body)
    return HTMLResponse(content=html_output)

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
        <div class="fw-bold text-primary mb-1"><i class="fa-solid fa-bolt me-1"></i>핵심 요약</div>
        <div class="text-secondary small" style="white-space: pre-line; line-height: 1.7;">__SUMMARY__</div>
    </div>

    <article id="artBody" class="art-body shadow-sm mb-4">
        __CONTENT__
    </article>

    <div class="d-flex justify-content-between align-items-center bg-white p-3 rounded-3 border">
        <button class="btn btn-outline-danger btn-sm rounded-pill" onclick="this.innerHTML='❤️ 유익해요 ' + (parseInt(this.innerText.replace(/[^0-9]/g,'')||0)+1)">
            ❤️ 유익해요 __LIKES__
        </button>
        <a href="/" class="btn btn-primary btn-sm rounded-pill px-3">목록으로</a>
    </div>
</div>
<script>
    var synth = window.speechSynthesis;
    var isSpeaking = false;
    var sList = [];
    var sIdx = 0;
    var bestVoice = null;

    function getVoice() {
        if (!synth) return null;
        var vs = synth.getVoices();
        for (var i = 0; i < vs.length; i++) {
            if (vs[i].lang.indexOf('ko') !== -1 && (vs[i].name.indexOf('SunHi') !== -1 || vs[i].name.indexOf('Natural') !== -1 || vs[i].name.indexOf('Google') !== -1)) {
                return vs[i];
            }
        }
        for (var j = 0; j < vs.length; j++) {
            if (vs[j].lang.indexOf('ko') !== -1) return vs[j];
        }
        return null;
    }

    if (synth && synth.onvoiceschanged !== undefined) {
        synth.onvoiceschanged = function() { bestVoice = getVoice(); };
    }

    function speakNext() {
        if (!isSpeaking || sIdx >= sList.length) {
            isSpeaking = false;
            document.getElementById('ttsText').innerText = "기사 다시 듣기";
            document.getElementById('ttsBtn').className = "btn btn-dark btn-sm fw-bold px-3 py-2 rounded-pill shadow-sm";
            document.getElementById('ttsStatus').innerText = "낭독이 완료되었습니다.";
            return;
        }
        var u = new SpeechSynthesisUtterance(sList[sIdx].trim());
        u.lang = 'ko-KR';
        u.rate = 0.90;
        u.pitch = 0.92;
        if (!bestVoice) bestVoice = getVoice();
        if (bestVoice) u.voice = bestVoice;
        u.onend = function() { sIdx++; speakNext(); };
        u.onerror = function() { sIdx++; speakNext(); };
        synth.speak(u);
    }

    function toggleSpeech() {
        if (!synth) return alert("음성을 지원하지 않는 브라우저입니다.");
        if (isSpeaking) {
            synth.cancel();
            isSpeaking = false;
            document.getElementById('ttsText').innerText = "차분한 아나운서 음성 듣기";
            document.getElementById('ttsBtn').className = "btn btn-dark btn-sm fw-bold px-3 py-2 rounded-pill shadow-sm";
            document.getElementById('ttsStatus').innerText = "재생이 일시정지되었습니다.";
        } else {
            synth.cancel();
            var text = document.getElementById('artBody').innerText.replace(/\\s+/g, ' ').trim();
            sList = text.match(/[^.?!]+[.?!]+/g) || [text];
            sIdx = 0;
            isSpeaking = true;
            document.getElementById('ttsText').innerText = "일시정지";
            document.getElementById('ttsBtn').className = "btn btn-danger btn-sm fw-bold px-3 py-2 rounded-pill shadow-sm";
            document.getElementById('ttsStatus').innerText = "차분하고 정중한 어조로 낭독 중입니다...";
            speakNext();
        }
    }

    var curSize = 1.15;
    function resizeFont(d) {
        curSize = Math.max(0.95, Math.min(1.5, curSize + (d * 0.1)));
        document.getElementById('artBody').style.fontSize = curSize + 'rem';
    }
</script>
"""

@app.get("/article/{art_id}")
def view_article(art_id: int):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE articles SET views = COALESCE(views, 0) + 1 WHERE id = ?", (art_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE id = ?", (art_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        return HTMLResponse("기사를 찾을 수 없습니다. <a href='/'>홈으로</a>", status_code=404)

    row = dict(r)
    body = (
        ARTICLE_VIEW_TEMPLATE
        .replace("__BADGE__", get_badge(str(row.get('category', ''))))
        .replace("__CREATED_AT__", str(row.get('created_at', '')))
        .replace("__ARTICLE_TITLE__", str(row.get('title', '')))
        .replace("__SUMMARY__", str(row.get('summary', '')))
        .replace("__CONTENT__", str(row.get('content', '')))
        .replace("__LIKES__", str(row.get('likes', 0)))
    )
    return render(str(row.get('title', '기사 보기')), body)

@app.get("/write")
def write_form():
    body = """
    <div class="container py-5" style="max-width: 600px;">
        <div class="card p-4 shadow-sm border-0 rounded-3">
            <h4 class="fw-bold mb-3"><i class="fa-solid fa-pen text-primary me-2"></i>기사 수동 발행</h4>
            <p class="text-muted small mb-3">원하는 주제를 입력하시면 0.1초 만에 맞춤형 전문 기사가 즉시 발행됩니다.</p>
            <form method="get" action="/create" onsubmit="this.btn.disabled=true; this.btn.innerText='기사 발행 중...';">
                <div class="mb-3">
                    <label class="form-label fw-bold small">카테고리</label>
                    <select name="category" class="form-select">
                        <option value="정부 지원금/복지 혜택">🏛️ 정부 지원금/복지 혜택</option>
                        <option value="생활 경제/세무 상식">📈 생활 경제/세무 상식</option>
                        <option value="시니어 건강/식품">🩺 시니어 건강/식품</option>
                        <option value="문화/예술">🎨 문화/예술</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-bold small">기사 주제</label>
                    <input type="text" name="topic" class="form-control" placeholder="예: 2026년 시니어 노인장기요양보험 등급 판정 기준" required>
                </div>
                <button type="submit" name="btn" class="btn btn-primary w-100 py-2 fw-bold">기사 발행하기</button>
            </form>
        </div>
    </div>
    """
    return render("기사 수동 발행", body)

@app.get("/create")
def create_article(category: str = "정부 지원금/복지 혜택", topic: str = ""):
    if not topic:
        return RedirectResponse(url="/", status_code=303)
    new_id = save_article_secure(category, topic)
    return RedirectResponse(url=f"/article/{new_id}", status_code=303)

@app.get("/sitemap.xml", response_class=Response)
def sitemap():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM articles ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        xml += '  <url><loc>https://insight-webzine.onrender.com/</loc><priority>1.0</priority></url>\n'
        for r in rows:
            xml += f'  <url><loc>https://insight-webzine.onrender.com/article/{r["id"]}</loc><priority>0.8</priority></url>\n'
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")
    except Exception:
        return Response(content='<xml></xml>', media_type="application/xml")

@app.get("/rss", response_class=Response)
def rss_feed():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, title, summary FROM articles ORDER BY id DESC LIMIT 20")
        rows = c.fetchall()
        conn.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>인사이트 데일리</title><link>https://insight-webzine.onrender.com</link>'
        for r in rows:
            xml += f'<item><title><![CDATA[{r["title"]}]]></title><link>https://insight-webzine.onrender.com/article/{r["id"]}</link><description><![CDATA[{r["summary"]}]]></description></item>'
        xml += '</channel></rss>'
        return Response(content=xml, media_type="application/xml")
    except Exception:
        return Response(content='<xml></xml>', media_type="application/xml")

@app.get("/admin/stats")
def admin_stats(pw=""):
    if pw != ADMIN_PW:
        body = """
        <div class="container py-5 text-center" style="max-width:320px;">
            <h5 class="fw-bold mb-3">관리자 로그인</h5>
            <form method="get" action="/admin/stats">
                <input type="password" name="pw" class="form-control mb-2" placeholder="비밀번호" required>
                <button type="submit" class="btn btn-primary w-100">접속</button>
            </form>
        </div>
        """
        return render("로그인", body)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM articles ORDER BY views DESC")
    rows = c.fetchall()
    conn.close()
    
    tr_list = []
    for r in rows:
        row = dict(r)
        tr_list.append(
            f"<tr><td>{row.get('id', '')}</td><td><a href='/article/{row.get('id', '')}'>{row.get('title', '')}</a></td><td>{row.get('category', '')}</td><td>{row.get('views', 0)}회</td><td>{str(row.get('created_at', ''))[:10]}</td></tr>"
        )
    table_rows = "".join(tr_list)
    body = f'<div class="container py-4"><h3>📊 통계</h3><table class="table table-bordered bg-white mt-3"><thead><tr><th>ID</th><th>제목</th><th>분류</th><th>조회수</th><th>일자</th></tr></thead><tbody>{table_rows}</tbody></table></div>'
    return render("통계", body)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
