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

# 실시간 기사 수집 대상 카테고리 (새 기사 생성용)
CRAWL_TARGETS = {
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

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 컬럼 이름으로 안전하게 접근
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # 테이블 구조 확인 및 생성
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
# 1. 텍스트 정제 및 실시간 기사 작성 로직
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
    <p>{summary if summary else clean_title}와 관련하여 주요 이해관계자 간의 견해차가 가시화되면서 온·오프라인 상에서 뜨거운 반응이 이어지고 있습니다. 특히 단기적 이슈에 그치지 않고 시장 전반에 미칠 파장에 대한 분석이 잇따르는 상황입니다.</p>

    <h3>2. 핵심 쟁점 및 찬반 대립 구도</h3>
    <p>이번 현안을 둘러싼 가장 큰 분기점은 실효성과 부작용의 대립입니다. 일각에서는 현실적인 제도 개선과 발 빠른 조치를 요구하는 반면, 다른 한편에서는 신중한 접근과 보완 장치 마련이 선행되어야 한다고 맞서고 있습니다.</p>

    <h3>3. 독자 및 경제·사회에 미치는 파급 영향</h3>
    <p>본 사안은 일반 시민들의 실생활과 직간접적으로 맞닿아 있습니다. 향후 발표될 후속 대책의 수위에 따라 관련 시장의 지형 변화는 물론, 국민들의 체감 물가 및 권익에도 중대한 변곡점으로 작용할 전망입니다.</p>

    <h3>4. 향후 관전 포인트 및 후속 일정</h3>
    <p>전문가들은 향후 관계 당국의 공식 발표와 입법·행정 절차의 구체화 시점을 면밀히 주시해야 한다고 조언합니다. 시사투데이는 추가적인 사실관계와 세부 변동사항을 지속적으로 추적 보도할 예정입니다.</p>
    """
    return {"title": click_title, "lead": lead, "content": body_html}

def fetch_and_publish_category(category_name: str, limit: int = 1):
    url = CRAWL_TARGETS.get(category_name)
    if not url:
        return

    items = get_rss_items(url)
    conn = get_db_connection()
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
# 2. 웹진 프론트엔드 UI 템플릿
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
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Pretendard", sans-serif; background-color: #f4f6f9; color: #222; }
        .header { background: #fff; border-bottom: 2px solid #002d5b; padding: 18px 24px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 26px; font-weight: 900; color: #002d5b; text-decoration: none; }
        .logo span { background: #002d5b; color: #fff; padding: 2px 8px; border-radius: 4px; margin-left: 5px; }
        .btn-refresh { background: #ff0055; color: #fff; text-decoration: none; padding: 10px 18px; border-radius: 4px; font-size: 13px; font-weight: bold; }
        .btn-refresh:hover { background: #e0004c; }

        .nav-bar { background: #fff; padding: 12px 24px; display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid #e0e4e9; }
        .nav-item { padding: 8px 16px; text-decoration: none; font-size: 13px; font-weight: bold; border-radius: 20px; color: #4b5563; background: #eef2f6; white-space: nowrap; }
        .nav-item:hover { background: #dde3eb; }
        .nav-item.active { background: #002d5b; color: #fff; }

        .container { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; margin-bottom: 40px; }
        
        .card-link { text-decoration: none; color: inherit; display: block; }
        .card { background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); display: flex; flex-direction: column; height: 100%; transition: transform 0.2s, box-shadow 0.2s; border: 1px solid #eaecef; }
        .card:hover { transform: translateY(-4px); box-shadow: 0 8px 20px rgba(0,0,0,0.12); }
        
        .card-visual { height: 160px; padding: 20px; background: linear-gradient(135deg, #1e3c72, #2a5298); color: #fff; display: flex; flex-direction: column; justify-content: space-between; }
        .card-visual .badge { align-self: flex-start; background: rgba(0,0,0,0.4); padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        .card-visual .card-banner-text { font-size: 17px; font-weight: 800; line-height: 1.4; word-break: keep-all; }
        .card-visual .sub { font-size: 11px; opacity: 0.85; }

        .card-body { padding: 20px; flex: 1; display: flex; flex-direction: column; }
        .card-title { font-size: 16px; font-weight: 700; line-height: 1.5; color: #111; margin-bottom: 12px; word-break: keep-all; }
        .card-lead { font-size: 13px; color: #666; line-height: 1.6; margin-bottom: 14px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .card-date { font-size: 12px; color: #999; margin-top: auto; }

        .detail-box { background: #fff; padding: 40px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #eaecef; }
        .detail-cat { display: inline-block; background: #e0f2fe; color: #0284c7; font-weight: bold; font-size: 13px; padding: 4px 12px; border-radius: 4px; }
        .detail-title { font-size: 28px; font-weight: 800; margin: 16px 0; line-height: 1.4; word-break: keep-all; }
        .detail-date { font-size: 13px; color: #666; border-bottom: 1px solid #eee; padding-bottom: 16px; margin-bottom: 24px; }
        .detail-content h3 { font-size: 19px; margin: 28px 0 12px 0; color: #002d5b; border-left: 4px solid #002d5b; padding-left: 10px; }
        .detail-content p { font-size: 16px; line-height: 1.85; color: #333; margin-bottom: 16px; word-break: keep-all; }
        .article-lead { background: #f8fafc; padding: 18px; border-radius: 8px; border-left: 4px solid #0284c7; font-size: 16px; line-height: 1.7; margin-bottom: 24px; }
        .empty-msg { text-align: center; padding: 60px 20px; color: #666; font-size: 15px; background: #fff; border-radius: 10px; border: 1px solid #eaecef; }
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">시사투데이<span>창</span></a>
        <a href="/crawl-all" class="btn-refresh">⚡ 전 카테고리 실시간 이슈 자동 취재</a>
    </header>

    <nav class="nav-bar">
        <a href="/" class="nav-item {% if not current_cat %}active{% endif %}">전체 ({{ total_count }})</a>
        {% for cat in categories %}
        <a href="/?cat={{ cat }}" class="nav-item {% if current_cat == cat %}active{% endif %}">{{ cat }}</a>
        {% endfor %}
    </nav>

    <main class="container">
        {% if is_detail %}
            <article class="detail-box">
                <span class="detail-cat">{{ article['category'] }}</span>
                <h1 class="detail-title">{{ article['title'] }}</h1>
                <div class="detail-date">발행일시: {{ article['created_at'] }} | 시사투데이 특별취재팀</div>
                
                {% if article['lead_text'] %}
                    <div class="article-lead"><b>[핵심 개요]</b> {{ article['lead_text'] }}</div>
                {% endif %}

                <div class="detail-content">
                    {% if article['content'] %}
                        {{ article['content']|safe }}
                    {% else %}
                        <h3>보도 상세 내용</h3>
                        <p>{{ article['lead_text'] if article['lead_text'] else article['title'] }}</p>
                        <p>본 기사는 시사투데이 아카이브에 정식 등록된 기사입니다. 세부 속보 및 관련 이슈는 상단의 [실시간 이슈 자동 취재]를 통해 계속해서 업데이트됩니다.</p>
                    {% endif %}
                </div>
                
                <div style="margin-top: 36px; display: flex; gap: 10px;">
                    <a href="/" class="nav-item active">← 전체 목록으로 돌아가기</a>
                    {% if article['category'] %}
                    <a href="/?cat={{ article['category'] }}" class="nav-item">[{{ article['category'] }}] 목록으로</a>
                    {% endif %}
                </div>
            </article>
        {% else %}
            {% if articles|length == 0 %}
                <div class="empty-msg">
                    <p>선택하신 카테고리에 기사가 없습니다.</p>
                    <p style="margin-top: 12px;">우측 상단의 <b>[⚡ 전 카테고리 실시간 이슈 자동 취재]</b> 버튼을 누르면 실시간 속보가 즉시 등록됩니다.</p>
                </div>
            {% else %}
                <div class="main-grid">
                    {% for item in articles %}
                    <a href="/article/{{ item['id'] }}" class="card-link">
                        <div class="card">
                            <div class="card-visual">
                                <span class="badge">{{ item['category'] }}</span>
                                <div class="card-banner-text">{{ item['title'][:28] }}{% if item['title']|length > 28 %}...{% endif %}</div>
                                <span class="sub">SISATODAY ISSUE REPORT</span>
                            </div>
                            <div class="card-body">
                                <div class="card-title">{{ item['title'] }}</div>
                                {% if item['lead_text'] %}
                                    <div class="card-lead">{{ item['lead_text'] }}</div>
                                {% endif %}
                                <span class="card-date">발행: {{ item['created_at'] }}</span>
                            </div>
                        </div>
                    </a>
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
    cat = request.args.get("cat", "").strip()
    conn = get_db_connection()
    cur = conn.cursor()

    # DB에 존재하는 모든 카테고리를 실시간으로 자동 추출 (과거+현재 모든 카테고리 포함)
    cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
    db_cats = [row['category'] for row in cur.fetchall()]

    # 기본 카테고리와 DB에 있는 카테고리를 합쳐서 중복 없이 메뉴 생성
    all_categories = list(dict.fromkeys(list(CRAWL_TARGETS.keys()) + db_cats))

    # 기사 수 카운트
    cur.execute("SELECT COUNT(*) as cnt FROM articles")
    total_count = cur.fetchone()['cnt']

    if cat:
        cur.execute("SELECT * FROM articles WHERE category = ? ORDER BY id DESC", (cat,))
    else:
        cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()
    conn.close()

    return render_template_string(
        HTML_TEMPLATE,
        articles=articles,
        categories=all_categories,
        current_cat=cat,
        total_count=total_count,
        is_detail=False
    )

@flask_app.route("/article/<int:article_id>")
def article_detail(article_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
    db_cats = [row['category'] for row in cur.fetchall()]
    all_categories = list(dict.fromkeys(list(CRAWL_TARGETS.keys()) + db_cats))

    cur.execute("SELECT COUNT(*) as cnt FROM articles")
    total_count = cur.fetchone()['cnt']

    cur.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    article = cur.fetchone()
    conn.close()

    if not article:
        return redirect(url_for("index"))

    return render_template_string(
        HTML_TEMPLATE,
        article=article,
        categories=all_categories,
        current_cat=article['category'],
        total_count=total_count,
        is_detail=True
    )

@flask_app.route("/crawl-all")
def crawl_all():
    for cat in CRAWL_TARGETS.keys():
        fetch_and_publish_category(cat, limit=1)
    return redirect(url_for("index"))


# ==========================================
# 3. Render Uvicorn 호환 내장 ASGI 브리지
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
