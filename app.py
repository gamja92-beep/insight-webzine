import os
import re
import sys
import time
import sqlite3
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from flask import Flask, render_template_string, request, redirect, url_for

flask_app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "webzine.db")

# 상단 메뉴바와 1:1로 일치하는 실시간 RSS 주소
CATEGORIES = {
    "정치/시사": "https://news.google.com/rss/search?q=정치+시사&hl=ko&gl=KR&ceid=KR:ko",
    "경제/주식": "https://news.google.com/rss/search?q=경제+증시+주식&hl=ko&gl=KR&ceid=KR:ko",
    "세상이야기": "https://news.google.com/rss/search?q=사회+사건+사고&hl=ko&gl=KR&ceid=KR:ko",
    "AI/테크": "https://news.google.com/rss/search?q=인공지능+IT+테크&hl=ko&gl=KR&ceid=KR:ko",
    "건강/복지": "https://news.google.com/rss/search?q=건강+복지+의료&hl=ko&gl=KR&ceid=KR:ko",
    "생활정보": "https://news.google.com/rss/search?q=부동산+물가+생활정보&hl=ko&gl=KR&ceid=KR:ko",
    "연예뉴스": "https://news.google.com/rss/search?q=방송+연예+이슈&hl=ko&gl=KR&ceid=KR:ko",
    "스포츠": "https://news.google.com/rss/search?q=스포츠+경기&hl=ko&gl=KR&ceid=KR:ko",
    "지역창": "https://news.google.com/rss/search?q=강원+지역+소식&hl=ko&gl=KR&ceid=KR:ko"
}

# 카테고리별 테마 그라데이션 색상 (엑박 없는 브라우저 자체 카드 생성용)
CATEGORY_THEMES = {
    "정치/시사": ("#0f2027", "#203a43", "⚖️"),
    "경제/주식": ("#134e5e", "#71b280", "📈"),
    "세상이야기": ("#2c3e50", "#4ca1af", "📢"),
    "AI/테크": ("#141e30", "#243b55", "⚡"),
    "건강/복지": ("#1d976c", "#93f9b9", "🩺"),
    "생활정보": ("#3a6073", "#3a7bd5", "💡"),
    "연예뉴스": ("#4b134f", "#c94b4b", "🎬"),
    "스포츠": ("#16222f", "#3a6073", "⚽"),
    "지역창": ("#1e3c72", "#2a5298", "🗺️")
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
# 1. 텍스트 추출 및 심층 기사 생성 엔진
# ==========================================
def strip_html_tags(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', clean).strip()

def get_rss_items(rss_url):
    items = []
    try:
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        for it in root.findall('./channel/item'):
            title = it.findtext('title') or ''
            link = it.findtext('link') or ''
            desc = it.findtext('description') or ''
            items.append({'title': title, 'link': link, 'description': desc})
    except Exception:
        pass
    return items

def generate_click_worthy_title(original_title: str) -> str:
    clean = re.sub(r'\[.*?\]|\(.*?\)', '', original_title).strip()
    if any(k in clean for k in ['논란', '의혹', '충격', '폭등', '급락']):
        return f"\"{clean}\"... 핵심 쟁점과 파급 효과 총정리"
    elif '?' in clean:
        return f"{clean} 현장 분석 및 전문가 전망"
    else:
        return f"\"{clean}\"... 지금 실시간 주목받는 진짜 이유는?"

def compose_depth_article(category: str, raw_title: str, summary: str) -> dict:
    clean_title = strip_html_tags(raw_title)
    click_title = generate_click_worthy_title(clean_title)
    lead = f"최근 {category} 분야에서 '{clean_title}' 소식이 전해지며 대중과 관련 업계의 이목이 집중되고 있습니다."

    body_html = f"""
    <p class="article-lead"><b>[시사투데이 실시간 기획분석]</b> {lead}</p>
    
    <h3>1. 사건 경위 및 최근 발생 배경</h3>
    <p>{summary if summary else clean_title}와 관련하여 주요 이해관계자 간의 견해차가 가시화되면서 온·오프라인 상에서 뜨거운 반응이 이어지고 있습니다. 특히 단기적 이슈에 그치지 않고 사회·경제 전반에 미칠 파장에 대한 분석이 잇따르고 있습니다.</p>

    <h3>2. 핵심 쟁점 및 대립 구도</h3>
    <p>이번 현안을 둘러싼 가장 큰 분기점은 실효성과 부작용의 균형입니다. 한편에서는 조속한 조치와 제도 개선을 요구하는 반면, 다른 한편에서는 안전망 확보와 신중한 접근이 선행되어야 한다고 맞서고 있습니다.</p>

    <h3>3. 독자 및 실생활에 미치는 파급 영향</h3>
    <p>본 사안은 일반 시민들의 일상생활과 직간접적으로 연결되어 있습니다. 향후 확정될 정책 방향이나 시장 상황에 따라 독자 여러분의 경제적 판단 및 권익 보호에도 중대한 영향을 미칠 전망입니다.</p>

    <h3>4. 향후 관전 포인트 및 후속 일정</h3>
    <p>관계 당국의 공식 입장 발표 및 구체적인 후속 일정이 예정되어 있어 지속적인 모니터링이 필요합니다. 시사투데이는 추가적인 사실관계와 세부 변동사항을 확인되는 대로 신속히 보도하겠습니다.</p>
    """
    return {"title": click_title, "lead": lead, "content": body_html}

def fetch_and_publish_category(category_name: str, limit: int = 1):
    url = CATEGORIES.get(category_name)
    if not url:
        return

    items = get_rss_items(url)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    count = 0
    for entry in items:
        if count >= limit:
            break

        cur.execute("SELECT id FROM articles WHERE source_link = ?", (entry['link'],))
        if cur.fetchone():
            continue

        raw_summary = strip_html_tags(entry['description'])
        article_data = compose_depth_article(category_name, entry['title'], raw_summary)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            INSERT INTO articles (category, title, lead_text, content, image_url, source_link, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            category_name,
            article_data["title"],
            article_data["lead"],
            article_data["content"],
            "",
            entry['link'],
            now_str
        ))
        conn.commit()
        count += 1

    conn.close()


# ==========================================
# 2. 웹진 프론트엔드 라우트 & 반응형 UI
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>시사투데이 창 - 정론 심층 분석 뉴스</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", sans-serif; background-color: #f4f6f9; color: #222; }
        .header { background: #fff; border-bottom: 2px solid #002d5b; padding: 18px 24px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 26px; font-weight: 900; color: #002d5b; text-decoration: none; }
        .logo span { background: #002d5b; color: #fff; padding: 2px 8px; border-radius: 4px; margin-left: 5px; }
        .btn-refresh { background: #ff0055; color: #fff; text-decoration: none; padding: 9px 18px; border-radius: 4px; font-size: 13px; font-weight: bold; }
        
        .nav-bar { background: #fff; padding: 12px 24px; display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid #e0e4e9; }
        .nav-item { padding: 8px 16px; text-decoration: none; font-size: 13px; font-weight: bold; border-radius: 20px; color: #4b5563; background: #eef2f6; white-space: nowrap; }
        .nav-item.active { background: #002d5b; color: #fff; }

        .container { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; margin-bottom: 40px; }
        .card { background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); display: flex; flex-direction: column; transition: transform 0.2s; }
        .card:hover { transform: translateY(-3px); }
        
        /* 엑박 원천 방지: 모던 카드 썸네일 */
        .card-visual { height: 180px; padding: 20px; color: #fff; display: flex; flex-direction: column; justify-content: space-between; position: relative; }
        .card-visual .badge { align-self: flex-start; background: rgba(0,0,0,0.3); padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        .card-visual .icon-title { font-size: 18px; font-weight: 800; line-height: 1.4; text-shadow: 0 2px 4px rgba(0,0,0,0.4); word-break: keep-all; }
        .card-visual .sub { font-size: 11px; opacity: 0.8; }

        .card-body { padding: 20px; flex: 1; display: flex; flex-direction: column; }
        .card-title { font-size: 16px; font-weight: 700; line-height: 1.5; color: #111; text-decoration: none; margin-bottom: 12px; }
        .card-title:hover { color: #002d5b; }
        .card-date { font-size: 12px; color: #888; margin-top: auto; }

        .detail-box { background: #fff; padding: 40px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
        .detail-cat { color: #002d5b; font-weight: bold; font-size: 15px; }
        .detail-title { font-size: 28px; font-weight: 800; margin: 14px 0 20px 0; line-height: 1.4; word-break: keep-all; }
        .detail-date { font-size: 13px; color: #666; border-bottom: 1px solid #eee; padding-bottom: 16px; margin-bottom: 24px; }
        .detail-content h3 { font-size: 19px; margin: 28px 0 12px 0; color: #002d5b; border-left: 4px solid #002d5b; padding-left: 10px; }
        .detail-content p { font-size: 16px; line-height: 1.85; color: #333; margin-bottom: 16px; word-break: keep-all; }
        .article-lead { background: #f8fafc; padding: 18px; border-radius: 8px; border-left: 4px solid #0284c7; }
        .empty-msg { text-align: center; padding: 60px 20px; color: #666; font-size: 15px; }
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">시사투데이<span>창</span></a>
        <a href="/crawl-all" class="btn-refresh">⚡ 전 카테고리 실시간 이슈 자동 취재</a>
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
                <span class="detail-cat">카테고리: {{ article[1] }}</span>
                <h1 class="detail-title">{{ article[2] }}</h1>
                <div class="detail-date">발행일시: {{ article[7] }} | 시사투데이 특별취재팀</div>
                <div class="detail-content">{{ article[4]|safe }}</div>
                <div style="margin-top: 36px;">
                    <a href="/" class="nav-item active">목록으로 돌아가기</a>
                </div>
            </article>
        {% else %}
            {% if articles|length == 0 %}
                <div class="empty-msg">
                    <p>현재 등록된 기사가 없습니다.</p>
                    <p style="margin-top: 12px;">우측 상단의 <b>[⚡ 전 카테고리 실시간 이슈 자동 취재]</b> 버튼을 누르면 실시간 기사가 등록됩니다.</p>
                </div>
            {% else %}
                <div class="main-grid">
                    {% for item in articles %}
                    <div class="card">
                        <div class="card-visual" style="background: linear-gradient(135deg, {{ themes.get(item[1], ('#1e3c72','#2a5298'))[0] }}, {{ themes.get(item[1], ('#1e3c72','#2a5298'))[1] }});">
                            <span class="badge">{{ themes.get(item[1], ('','','📰'))[2] }} {{ item[1] }}</span>
                            <div class="icon-title">{{ item[2][:26] }}{% if item[2]|length > 26 %}...{% endif %}</div>
                            <span class="sub">SISATODAY ISSUE ANALYSIS</span>
                        </div>
                        <div class="card-body">
                            <a href="/article/{{ item[0] }}" class="card-title">{{ item[2] }}</a>
                            <span class="card-date">발행 | {{ item[7] }}</span>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endif %}
    </main>
</body>
</html>
"""

@flask_app.route("/")
def index():
    cat = request.args.get("cat", "")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if cat:
        cur.execute("SELECT * FROM articles WHERE category = ? ORDER BY id DESC", (cat,))
    else:
        cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()
    conn.close()

    return render_template_string(
        HTML_TEMPLATE,
        articles=articles,
        categories=list(CATEGORIES.keys()),
        themes=CATEGORY_THEMES,
        current_cat=cat,
        is_detail=False
    )

@flask_app.route("/article/<int:article_id>")
def article_detail(article_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    article = cur.fetchone()
    conn.close()

    if not article:
        return redirect(url_for("index"))

    return render_template_string(
        HTML_TEMPLATE,
        article=article,
        categories=list(CATEGORIES.keys()),
        themes=CATEGORY_THEMES,
        current_cat=article[1],
        is_detail=True
    )

@flask_app.route("/crawl-all")
def crawl_all():
    # 과거 잘못된 영문 카테고리 기사 일괄 정리
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM articles WHERE category NOT IN ({})".format(','.join('?' * len(CATEGORIES))), list(CATEGORIES.keys()))
    conn.commit()
    conn.close()

    # 현재 9개 카테고리 실시간 이슈 자동 수집
    for cat in CATEGORIES.keys():
        fetch_and_publish_category(cat, limit=1)
    return redirect(url_for("index"))


# ==========================================
# 3. Render Uvicorn 호환 내장 ASGI 어댑터
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
