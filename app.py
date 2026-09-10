import os
import re
import time
import sqlite3
import datetime
import urllib.parse
import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory

app = Flask(__name__)

# 기본 경로 및 데이터베이스 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGE_DIR = os.path.join(STATIC_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "webzine.db")

os.makedirs(IMAGE_DIR, exist_ok=True)

# 카테고리 매핑 및 실시간 속보 RSS 소스
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


# ==========================================
# 1. DB 초기화 및 관리 함수
# ==========================================
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
# 2. 엑박 원천 방지: 이미지 로컬 다운로드 및 대체 생성
# ==========================================
def create_fallback_image(category: str, title: str, filename: str) -> str:
    """외부 이미지 차단 시 즉시 시사 정론지 스타일의 고화질 썸네일을 자동 생성"""
    filepath = os.path.join(IMAGE_DIR, filename)
    img = Image.new("RGB", (800, 450), color=(26, 29, 36))
    draw = ImageDraw.Draw(img)

    # 헤더 라벨
    draw.rectangle([(0, 0), (800, 10)], fill=(0, 204, 153))
    
    # 텍스트 렌더링 (기본 폰트 사용)
    draw.text((40, 60), f"[{category}] 시사투데이 특별 취재", fill=(0, 204, 153))

    # 제목 줄바꿈 정리
    display_title = title if len(title) <= 30 else title[:28] + "..."
    draw.text((40, 180), display_title, fill=(240, 240, 240))
    draw.text((40, 360), "SISATODAY NEWS ISSUE ANALYSIS", fill=(120, 130, 145))

    img.save(filepath, "JPEG")
    return f"/static/uploads/{filename}"

def save_safe_image(original_url: str, category: str, title: str) -> str:
    """외부 핫링크 이미지를 내 서버로 직접 다운로드 (실패 시 자체 생성 이미지로 완벽 대체)"""
    safe_name = f"thumb_{int(time.time() * 1000)}.jpg"
    local_path = os.path.join(IMAGE_DIR, safe_name)

    if original_url and original_url.startswith("http"):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.get(original_url, headers=headers, timeout=4)
            if res.status_code == 200 and len(res.content) > 1024:
                with open(local_path, "wb") as f:
                    f.write(res.content)
                return f"/static/uploads/{safe_name}"
        except Exception:
            pass

    return create_fallback_image(category, title, safe_name)


# ==========================================
# 3. 실시간 속보 수집 & 클릭 유도 심층 기사 생성기
# ==========================================
def generate_click_worthy_title(original_title: str) -> str:
    """밋밋한 제목을 대중 독자가 클릭할 수 있는 의문형·쟁점형 제목으로 변환"""
    clean = re.sub(r'\[.*?\]|\(.*?\)', '', original_title).strip()
    if any(k in clean for k in ['논란', '의혹', '충격', '폭등', '급락']):
        return f"\"{clean}\"... 핵심 쟁점과 파급 효과 총정리"
    elif '?' in clean:
        return f"{clean} 현장 분석 및 전문가 전망"
    else:
        return f"\"{clean}\"... 지금 실시간 주목받는 진짜 이유는?"

def compose_depth_article(category: str, raw_title: str, summary: str) -> dict:
    """배경-핵심쟁점-파급효과-향후전망 4단계 정규 심층 기사 포맷 생성"""
    clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
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
    return {
        "title": click_title,
        "lead": lead,
        "content": body_html
    }

def fetch_and_publish_category(category_name: str, limit: int = 1):
    """지정 카테고리의 실시간 속보를 크롤링하여 웹진에 자동 등록"""
    url = CATEGORIES.get(category_name)
    if not url:
        return

    feed = feedparser.parse(url)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    count = 0
    for entry in feed.entries:
        if count >= limit:
            break

        # 중복 기사 등록 방지
        cur.execute("SELECT id FROM articles WHERE source_link = ?", (entry.link,))
        if cur.fetchone():
            continue

        raw_summary = BeautifulSoup(entry.get('summary', ''), "html.parser").get_text()
        article_data = compose_depth_article(category_name, entry.title, raw_summary)

        # 이미지 추출 시도 (RSS 내 미디어 태그 탐색)
        extracted_img = ""
        if 'media_content' in entry and entry.media_content:
            extracted_img = entry.media_content[0].get('url', '')

        saved_image_url = save_safe_image(extracted_img, category_name, article_data["title"])
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            INSERT INTO articles (category, title, lead_text, content, image_url, source_link, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            category_name,
            article_data["title"],
            article_data["lead"],
            article_data["content"],
            saved_image_url,
            entry.link,
            now_str
        ))
        conn.commit()
        count += 1

    conn.close()


# ==========================================
# 4. 웹진 프론트엔드 라우트 & 템플릿
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
        body { font-family: 'Pretendard', 'Malgun Gothic', sans-serif; background-color: #f4f6f9; color: #222; }
        .header { background: #fff; border-bottom: 2px solid #002d5b; padding: 18px 24px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 26px; font-weight: 900; color: #002d5b; text-decoration: none; }
        .logo span { background: #002d5b; color: #fff; padding: 2px 8px; border-radius: 4px; margin-left: 5px; }
        .btn-refresh { background: #ff0055; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: bold; }
        
        .nav-bar { background: #fff; padding: 12px 24px; display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid #e0e4e9; }
        .nav-item { padding: 7px 14px; text-decoration: none; font-size: 13px; font-weight: bold; border-radius: 20px; color: #4b5563; background: #eef2f6; white-space: nowrap; }
        .nav-item.active { background: #002d5b; color: #fff; }

        .container { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
        
        .main-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 24px; margin-bottom: 40px; }
        .card { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; flex-direction: column; }
        .card-img-wrap { width: 100%; height: 210px; background: #1a1d24; overflow: hidden; position: relative; }
        .card-img-wrap img { width: 100%; height: 100%; object-fit: cover; }
        .card-body { padding: 18px; flex: 1; display: flex; flex-direction: column; }
        .cat-tag { align-self: flex-start; background: #e0f2fe; color: #0284c7; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px; margin-bottom: 10px; }
        .card-title { font-size: 17px; font-weight: 700; line-height: 1.45; color: #111; text-decoration: none; margin-bottom: 10px; }
        .card-title:hover { color: #002d5b; }
        .card-date { font-size: 12px; color: #888; margin-top: auto; }

        .detail-box { background: #fff; padding: 36px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .detail-cat { color: #002d5b; font-weight: bold; font-size: 14px; }
        .detail-title { font-size: 28px; font-weight: 800; margin: 12px 0 20px 0; line-height: 1.4; }
        .detail-date { font-size: 13px; color: #666; border-bottom: 1px solid #eee; padding-bottom: 16px; margin-bottom: 24px; }
        .detail-content h3 { font-size: 19px; margin: 24px 0 10px 0; color: #002d5b; border-left: 4px solid #002d5b; padding-left: 10px; }
        .detail-content p { font-size: 16px; line-height: 1.8; color: #333; margin-bottom: 16px; word-break: keep-all; }
        .article-lead { background: #f8fafc; padding: 16px; border-radius: 6px; border-left: 4px solid #0284c7; }
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
                {% if article[5] %}
                <div style="text-align: center; margin-bottom: 24px;">
                    <img src="{{ article[5] }}" alt="기사 썸네일" style="max-width: 100%; border-radius: 8px;">
                </div>
                {% endif %}
                <div class="detail-content">{{ article[4]|safe }}</div>
                <div style="margin-top: 30px;">
                    <a href="/" class="nav-item active">목록으로 돌아가기</a>
                </div>
            </article>
        {% else %}
            <div class="main-grid">
                {% for item in articles %}
                <div class="card">
                    <div class="card-img-wrap">
                        <img src="{{ item[5] }}" onerror="this.onerror=null; this.src='/static/uploads/default.jpg';" alt="썸네일">
                    </div>
                    <div class="card-body">
                        <span class="cat-tag">{{ item[1] }}</span>
                        <a href="/article/{{ item[0] }}" class="card-title">{{ item[2] }}</a>
                        <span class="card-date">발행 | {{ item[7] }}</span>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% endif %}
    </main>
</body>
</html>
"""

@app.route("/")
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
        current_cat=cat,
        is_detail=False
    )

@app.route("/article/<int:article_id>")
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
        current_cat=article[1],
        is_detail=True
    )

@app.route("/crawl-all")
def crawl_all():
    """모든 카테고리의 최신 실시간 이슈를 1개씩 즉시 수집해 기사화"""
    for cat in CATEGORIES.keys():
        fetch_and_publish_category(cat, limit=1)
    return redirect(url_for("index"))


if __name__ == "__main__":
    # 최초 실행 시 샘플 기사 1건씩 자동 수집
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM articles")
    if cur.fetchone()[0] == 0:
        for c in ["정치/시사", "경제/주식", "세상이야기", "AI/테크"]:
            fetch_and_publish_category(c, limit=1)
    conn.close()

    print("[웹진 서버 실행 완료] http://127.0.0.1:5000 접속")
    app.run(host="0.0.0.0", port=5000, debug=False)
