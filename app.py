import sys
import os
import sqlite3
import random
import time
import requests
import re
import xml.etree.ElementTree as ET
import urllib.request
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Form, Request, Response, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response as PlainResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from apscheduler.schedulers.background import BackgroundScheduler
from supabase import create_client, Client

app = FastAPI()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

API_KEY = os.environ.get("API_KEY", "")
MODEL_NAME = "gemini-3.6-flash"

UNSPLASH_ACCESS_KEY = "14W3nppcnrDp-1qJbpqzxERefLjS25QFZIZ27uYEhhA"
ADMIN_PASSWORD = "1234"

client = genai.Client(api_key=API_KEY)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================================
# 네이버 애널리틱스 추적 스크립트
# ==========================================================
NAVER_ANALYTICS_SCRIPT = """
<script type="text/javascript" src="//wcs.pstatic.net/wcslog.js"></script>
<script type="text/javascript">
if(!wcs_add) var wcs_add = {};
wcs_add["wa"] = "25f06e1fad42a20";
if(window.wcs) {
wcs_do();
}
</script>
"""

# ==========================================================
# 카테고리별 실시간 구글 속보 RSS
# ==========================================================
NEWS_FEEDS = {
    "정치/시사": "https://news.google.com/rss/search?q=정치+시사+국회+이슈&hl=ko&gl=KR&ceid=KR:ko",
    "경제/주식": "https://news.google.com/rss/search?q=증시+주식+테마주+코스피+환율+금리&hl=ko&gl=KR&ceid=KR:ko",
    "세상이야기": "https://news.google.com/rss/search?q=사회+사건+사고+훈훈한+미담&hl=ko&gl=KR&ceid=KR:ko",
    "AI/테크": "https://news.google.com/rss/search?q=생성형AI+챗GPT+제미니+클로드+딥시크+코파일럿&hl=ko&gl=KR&ceid=KR:ko",
    "건강/복지": "https://news.google.com/rss/search?q=시니어+건강+의료+기초연금+복지혜택&hl=ko&gl=KR&ceid=KR:ko",
    "생활정보": "https://news.google.com/rss/search?q=생활정보+부동산+물가+절세+지원금&hl=ko&gl=KR&ceid=KR:ko",
    "연예계뉴스": "https://news.google.com/rss/search?q=방송+연예+드라마+영화+화제인물&hl=ko&gl=KR&ceid=KR:ko",
    "스포츠": "https://news.google.com/rss/search?q=스포츠+경기결과+하이라이트+선수&hl=ko&gl=KR&ceid=KR:ko",
    "지역창": "https://news.google.com/rss/search?q=속초+강원+축제+맛집+관광+문화재&hl=ko&gl=KR&ceid=KR:ko"
}

def get_latest_realtime_news(category_name):
    """카테고리별 실시간 뉴스 헤드라인과 요약 수집"""
    feed_url = NEWS_FEEDS.get(category_name, NEWS_FEEDS["세상이야기"])
    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        items = root.findall('./channel/item')
        if items:
            chosen = random.choice(items[:5])
            title = chosen.findtext('title') or ''
            desc = chosen.findtext('description') or ''
            clean_desc = re.sub(r'<[^>]+>', '', desc).strip()
            return title.strip(), clean_desc
    except Exception as e:
        print(f"[실시간 뉴스 수집 알림]: {e}")
    return "", ""

def init_db():
    if supabase:
        pass
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT DEFAULT '종합',
                title TEXT,
                content TEXT,
                image_url TEXT,
                image_author TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

init_db()

def fetch_bulletproof_image(category_name):
    direct_pools = {
        "정치/시사": [
            ("https://images.unsplash.com/photo-1541872703-74c5e44368f9", "Unsplash"),
            ("https://images.unsplash.com/photo-1529107386315-e1a2ed48a620", "Unsplash"),
            ("https://images.pexels.com/photos/6077326/pexels-photo-6077326.jpeg", "pexels"),
            ("https://images.pexels.com/photos/1550337/pexels-photo-1550337.jpeg", "pexels"),
            ("https://images.pexels.com/photos/696627/pexels-photo-696627.jpeg", "pexels"),
            ("https://images.unsplash.com/photo-1486406146926-c627a92ad1ab", "Unsplash")
        ],
        "경제/주식": [
            ("https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3", "Unsplash"),
            ("https://images.pexels.com/photos/38375328/pexels-photo-38375328.jpeg", "pexels"),
            ("https://images.pexels.com/photos/5059930/pexels-photo-5059930.jpeg", "pexels"),
            ("https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f", "Unsplash"),
            ("https://images.unsplash.com/photo-1486406146926-c627a92ad1ab", "Unsplash"),
            ("https://images.unsplash.com/photo-1460925895917-afdab827c52f", "Unsplash")
        ],
        "세상이야기": [
            ("https://images.unsplash.com/photo-1477959858617-67f30bc75b82", "Unsplash"),
            ("https://images.pexels.com/photos/5059930/pexels-photo-5059930.jpeg", "pexels"),
            ("https://images.pexels.com/photos/36261996/pexels-photo-36261996.jpeg", "pexels"),
            ("https://images.unsplash.com/photo-1449824913935-59a10b8d2000", "Unsplash"),
            ("https://images.unsplash.com/photo-1469571486292-0ba58a3f068b", "Unsplash"),
            ("https://images.unsplash.com/photo-1506744038136-46273834b3fb", "Unsplash")
        ],
        "AI/테크": [
            ("https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5", "Unsplash"),
            ("https://images.unsplash.com/photo-1518770660439-4636190af475", "Unsplash"),
            ("https://images.unsplash.com/photo-1531482615713-2afd69097998", "Unsplash"),
            ("https://images.unsplash.com/photo-1550751827-4bd374c3f58b", "Unsplash")
        ],
        "건강/복지": [
            ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e", "Unsplash"),
            ("https://images.unsplash.com/photo-1501785888041-af3ef285b470", "Unsplash"),
            ("https://images.unsplash.com/photo-1500648767791-00dcc994a43e", "Unsplash"),
            ("https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05", "Unsplash")
        ],
        "생활정보": [
            ("https://images.unsplash.com/photo-1484807352052-23338990c6c8", "Unsplash"),
            ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e", "Unsplash"),
            ("https://images.unsplash.com/photo-1516321318423-f06f85e504b3", "Unsplash")
        ],
        "연예계뉴스": [
            ("https://images.unsplash.com/photo-1492684223066-81342ee5ff30", "Unsplash"),
            ("https://images.unsplash.com/photo-1470225620780-dba8ba36b745", "Unsplash"),
            ("https://images.unsplash.com/photo-1514525253161-7a46d19cd819", "Unsplash"),
            ("https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4", "Unsplash")
        ],
        "스포츠": [
            ("https://images.unsplash.com/photo-1461896836934-ffe607ba8211", "Unsplash"),
            ("https://images.unsplash.com/photo-1517649763962-0c623066013b", "Unsplash"),
            ("https://images.unsplash.com/photo-1574629810360-7efbbe195018", "Unsplash"),
            ("https://images.unsplash.com/photo-1508098682722-e99c43a406b2", "Unsplash")
        ],
        "지역창": [
            ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e", "Unsplash"),
            ("https://images.unsplash.com/photo-1477959858617-67f30bc75b82", "Unsplash"),
            ("https://images.unsplash.com/photo-1449824913935-59a10b8d2000", "Unsplash")
        ]
    }

    pool = direct_pools.get(category_name, direct_pools["세상이야기"])
    
    try:
        search_queries = {
            "정치/시사": "government building architecture wide",
            "경제/주식": "modern city skyscraper architecture wide",
            "세상이야기": "beautiful nature landscape sceneries wide",
            "AI/테크": "futuristic technology abstract background wide",
            "건강/복지": "peaceful nature park scenery wide",
            "생활정보": "lifestyle interior cozy modern wide",
            "연예계뉴스": "empty concert stage lights background wide",
            "스포츠": "empty stadium sports arena field wide",
            "지역창": "korean travel coastal ocean mountain landscape wide"
        }
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        params = {"query": search_queries.get(category_name, "landscape"), "orientation": "landscape", "page": random.randint(1, 50)}
        response = requests.get("https://api.unsplash.com/search/photos", headers=headers, params=params, timeout=4)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                safe_results = [r for r in results if not any(w in str(r.get('description','')).lower() or w in str(r.get('alt_description','')).lower() for w in ['portrait', 'face', 'person', 'woman', 'man', 'girl', 'boy', 'people', 'player', 'athlete'])]
                if not safe_results:
                    safe_results = results
                item = random.choice(safe_results)
                return item["urls"]["regular"], item["user"]["name"]
    except Exception as e:
        print(f"[이미지 API 경고]: {e}")
    
    chosen = random.choice(pool)
    return chosen[0], chosen[1]

def generate_smart_tags(text, title=""):
    try:
        prompt = (
            f"다음 기사 제목과 본문을 분석하여, 포털 검색 유입을 극대화할 수 있는 핵심 키워드 해시태그를 정확히 6개 생성하세요. "
            f"반드시 '#키워드' 형식으로 띄어쓰기로 구분하여 한 줄로 출력하세요. 다른 설명은 일체 쓰지 마세요.\n\n"
            f"제목: {title}\n본문: {text[:800]}"
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        tags_text = response.text.strip()
        tags = re.findall(r'#[\w가-힣]+', tags_text)
        if len(tags) >= 5:
            return " ".join(tags[:7])
    except Exception:
        pass
    
    return "#시사투데이 #이슈분석 #트렌드리포트 #실시간뉴스 #핵심인사이트 #종합분석"

def clean_and_format_content(text, category_name="종합", title=""):
    text = text.replace('**', '').replace('__', '')
    clean_title_str = title.replace('**', '').replace('*', '').strip()

    lines_raw = text.split('\n')
    processed_lines = []

    for line in lines_raw:
        p_str = line.strip()
        if not p_str:
            continue
        
        p_text_pure = re.sub(r'^[#|\s]+', '', p_str).replace('제목:', '').strip()
        if clean_title_str and p_text_pure == clean_title_str:
            continue

        if p_str.startswith('<div class="article-img-box"') or p_str.startswith('<p') or p_str.startswith('<div') or p_str.startswith('<figure'):
            processed_lines.append(p_str)
        elif p_str.startswith('###'):
            title_text = p_str.replace('###', '').strip()
            # 혹시 남아있을 수 있는 구조 라벨 자동 제거 방어
            title_text = re.sub(r'^\[(기|승|전|결)(:\s*[^\]]+)?\]\s*', '', title_text).strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 32px; margin-bottom: 14px; font-size: 1.15em; font-weight: 800; letter-spacing: -0.5px;">{title_text}</h3>')
        elif len(p_str) < 42 and not p_str.endswith(('.', '?', '!')) and not p_str.startswith('<'):
            sub_title = re.sub(r'^\[(기|승|전|결)(:\s*[^\]]+)?\]\s*', '', p_str).strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 32px; margin-bottom: 14px; font-size: 1.15em; font-weight: 800; letter-spacing: -0.5px;">{sub_title}</h3>')
        else:
            processed_lines.append(f'<p style="margin-bottom: 24px; text-align: left !important; word-break: normal; line-height: 1.8; color: #111111; font-size: 1.02em; letter-spacing: -0.3px;">{p_str}</p>')

    final_html = "".join(processed_lines)
    
    if '#시사투데이' not in final_html and '#이슈분석' not in final_html and 'word-spacing: 5px;' not in final_html:
        clean_tags_str = generate_smart_tags(text, title)
        tag_html = f"<div style='margin-top: 35px; padding-top: 15px; border-top: 1px solid #eaecee; color: #2980b9; font-weight: bold; font-size: 0.9em; word-spacing: 5px;'>{clean_tags_str}</div>"
        final_html += tag_html

    return final_html

def save_article_to_db(category, title, content, image_url, image_author):
    kst = timezone(timedelta(hours=9))
    current_time_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    
    if supabase:
        supabase.table("articles").insert({
            "category": category,
            "title": title,
            "content": content,
            "image_url": image_url,
            "image_author": image_author,
            "created_at": current_time_str
        }).execute()
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO articles (category, title, content, image_url, image_author, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
            (category, title, content, image_url, image_author, current_time_str)
        )
        conn.commit()
        conn.close()

def get_all_articles(category=None):
    if supabase:
        query = supabase.table("articles").select("*").order("id", desc=True)
        if category and category != "전체":
            query = query.eq("category", category)
        response = query.execute()
        return response.data
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        if category and category != "전체":
            cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE category = ? ORDER BY id DESC", (category,))
        else:
            cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return [{
            "id": r[0], "category": r[1], "title": r[2], "content": r[3], 
            "image_url": r[4], "image_author": r[5], "created_at": r[6]
        } for r in rows]

def get_article_by_id(article_id):
    if supabase:
        response = supabase.table("articles").select("*").eq("id", article_id).execute()
        return response.data[0] if response.data else None
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE id = ?", (article_id,))
        r = cursor.fetchone()
        conn.close()
        if not r:
            return None
        return {
            "id": r[0], "category": r[1], "title": r[2], "content": r[3], 
            "image_url": r[4], "image_author": r[5], "created_at": r[6]
        }

def update_article_in_db(article_id, category, title, content, image_url, image_author):
    formatted_content = clean_and_format_content(content, category, title)
    clean_url = image_url.strip() if image_url and image_url.strip() else ""
    clean_author = image_author.strip() if image_author and image_author.strip() else ""
    
    if supabase:
        update_data = {
            "category": category,
            "title": title,
            "content": formatted_content,
            "image_url": clean_url,
            "image_author": clean_author
        }
        supabase.table("articles").update(update_data).eq("id", article_id).execute()
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE articles SET category = ?, title = ?, content = ?, image_url = ?, image_author = ? WHERE id = ?", 
            (category, title, formatted_content, clean_url, clean_author, article_id)
        )
        conn.commit()
        conn.close()

def delete_article_from_db(article_id):
    if supabase:
        supabase.table("articles").delete().eq("id", article_id).execute()
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()

# ==========================================================
# 🎯 육하원칙(5W1H) 기반 세련된 저널리즘 기사 생성 엔진
# ==========================================================
def generate_ai_article(category_name):
    news_title, news_desc = get_latest_realtime_news(category_name)
    
    ref_fact_context = ""
    if news_title:
        ref_fact_context = f"""
[실시간 실제 보도 헤드라인]: {news_title}
[실시간 보도 요약 내용]: {news_desc}
* 중요: 위 보도 내용에 나타난 구체적인 사실(실제 인물명, 소속 팀/기관, 대회/행사명, 사건 장소, 정확한 수치 등)을 핵심 뼈대로 사용하여 기사를 작성하세요. 절대 구체적 이름 없이 '어느 팀', '에이스 선수', '관계자' 같은 모호한 표현으로 때우지 마세요.
"""

    CATEGORY_DIRECTIVES = {
        "스포츠": (
            "반드시 실제 특정 종목, 팀명, 선수 이름, 대회명/리그명, 경기 일자나 스코어 등 '구체적인 고유명사'를 명확히 밝히세요. "
            "경기 전후반의 결정적 승부처, 선수의 구체적인 활약상, 감독의 전술적 승부수를 육하원칙에 맞추어 생생하게 전달하세요. "
            "추상적인 미사여구만 늘어놓는 것을 엄격히 금지합니다."
        ),
        "AI/테크": (
            "제미니(Gemini), 클로드(Claude), 챗GPT(ChatGPT), 코파일럿(Copilot), 마누스(Manus), 딥시크(DeepSeek) 등 구체적인 AI 모델명과 "
            "버전, 실제 벤치마크 점수나 기능적 차이점, 직장인/일반인의 실전 프롬프트 사용법 및 테크 기업의 발표 내용을 팩트 위주로 비교 분석하세요."
        ),
        "경제/주식": (
            "실제 시장을 흔드는 특정 테마 업종과 대표 관련 종목명, 코스피/코스닥 지수 흐름, 금리, 환율 수치 등 "
            "민감한 거시경제 지표를 제시하고, 일반 투자자가 알아야 할 실전 재테크 상식을 명확한 데이터와 함께 설명하세요."
        ),
        "정치/시사": (
            "현재 실시간으로 가장 뜨거운 국회 의안, 주요 정당과 핵심 정치인의 실명, 공식 발언 내용, 여야 간의 찬반 쟁점을 "
            "누가, 언제, 어디서, 왜 주장했는지 육하원칙에 입각하여 균형 잡힌 정론 보도로 작성하세요."
        ),
        "연예계뉴스": (
            "실제 화제가 되고 있는 스타의 이름, 방송 프로그램명, 작품명, 차트 순위나 흥행 지표 등 "
            "구체적 사실을 바탕으로 대중문화계의 최신 트렌드와 팬덤 반응을 품격 있게 조명하세요."
        ),
        "지역창": (
            "강원도 속초 및 영동 지역을 중심으로, 실제 지명, 축제명, 문화재 명칭, 로컬 명소와 맛집의 구체적 특징, "
            "방문 정보(교통, 일정, 추천 코스)를 생생하고 정확하게 취재하듯 서술하세요."
        ),
        "세상이야기": (
            "실제 사건/사고 현장 또는 감동적인 미담의 주인공, 발생 시점과 장소, 구체적인 선행 및 사건 경위를 육하원칙에 따라 따뜻하고 설득력 있게 전달하세요."
        ),
        "건강/복지": (
            "공신력 있는 기관의 최신 지침, 질환의 정확한 의학적 명칭, 정부 복지 혜택의 구체적인 신청 자격 요건과 소득 기준액을 명확히 밝히세요."
        ),
        "생활정보": (
            "정부 지원금, 부동산 절세 체크리스트, 에너지 절약법 등 일상에서 즉시 활용할 수 있는 법령 기준, 세액 감면 수치, 신청 사이트를 꼼꼼하게 명시하세요."
        )
    }

    directive = CATEGORY_DIRECTIVES.get(category_name, "정확한 팩트에 기반한 정론 기사를 작성하세요.")

    journalism_directive = f"""
당신은 대한민국 최고 정론지의 20년 차 베테랑 수석 기자입니다.
기사는 논리적 흐름(핵심 리드문 → 구체적 경위 및 수치 → 심층 분석 및 쟁점 → 향후 전망)을 갖추어야 합니다.

[작성 절대 원칙]:
1. **첫 번째 줄**: 따옴표나 특수문자 없이, 독자의 시선을 사로잡는 핵심 팩트 기반의 [기사 제목]을 한 줄로만 작성하세요.
2. **두 번째 줄**: 반드시 빈 줄로 남겨 두세요.
3. **세 번째 줄 (종합 리드문)**: 
   - 기사 서두 첫 문단에서 **[누가, 언제, 어디서, 무엇을, 어떻게, 왜]** 사건이 일어났는지 핵심 팩트를 두괄식으로 완벽히 요약하세요. (모호한 표현 절대 금지, 고유명사 필수)
4. **본문 및 소제목 규칙 (절대 준수)**:
   - 본문은 3~4개의 문단으로 구성하고, 각 문단 시작 전에는 반드시 '### 소제목'을 붙이세요.
   - **절대 소제목에 '[기]', '[승]', '[전]', '[결]', '기:', '승:', '전:', '결:' 같은 구조 설명용 단어나 한자 라벨을 쓰지 마세요.**
   - 실제 메이저 신문 기사처럼 세련되고 자연스러운 핵심 요약 소제목을 붙이세요. (예: '### 27분의 1 비용 혁신... 벤치마크로 입증된 추론 성능')
5. **금지 사항**:
   - 모호한 표현이나 얼버무리는 허위 서술 금지.
   - 본문 첫머리에 제목을 반복하지 마세요. 표준적인 한국어 보도체(~다)로 명료하게 작성하세요.

[취재 대상 카테고리]: {category_name}
[카테고리별 전문 가이드]: {directive}
{ref_fact_context}
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=journalism_directive,
        )
        raw_content = response.text.strip()
    except Exception as e:
        raw_content = f"기사 생성 오류: {e}"

    split_lines = raw_content.split("\n", 1)
    if len(split_lines) > 1 and len(split_lines[0].strip()) <= 60:
        art_title = split_lines[0].replace("#", "").replace("제목:", "").replace("**", "").strip()
        body_content = split_lines[1].strip()
    else:
        art_title = f"{category_name} 실시간 현장 심층 리포트"
        body_content = raw_content

    img_url, author_name = fetch_bulletproof_image(category_name)
    formatted_content = clean_and_format_content(body_content, category_name, art_title)
    save_article_to_db(category_name, art_title, formatted_content, img_url, author_name)

def scheduled_job():
    categories = ["정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]
    target_cat = random.choice(categories)
    generate_ai_article(target_cat)

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_job, 'interval', hours=6)
scheduler.start()

@app.post("/admin/upload-image")
async def upload_image(file: UploadFile = File(...), admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return {"error": "Unauthorized"}
    try:
        os.makedirs("static", exist_ok=True)
        file_ext = file.filename.split(".")[-1]
        unique_filename = f"img_{int(time.time())}_{random.randint(1000,9999)}.{file_ext}"
        file_path = os.path.join("static", unique_filename)
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
            
        image_url = f"/static/{unique_filename}"
        return {"url": image_url}
    except Exception as e:
        return {"error": str(e)}

@app.get("/robots.txt", response_class=PlainResponse)
def robots_txt():
    robots_text = (
        "User-agent: Googlebot\n"
        "Allow: /\n"
        "Crawl-delay: 0\n\n"
        "User-agent: *\n"
        "Allow: /\n\n"
        "Sitemap: https://insight-webzine.onrender.com/sitemap.xml"
    )
    return PlainResponse(content=robots_text, media_type="text/plain", headers={"X-Robots-Tag": "index, follow"})

@app.get("/sitemap.xml", response_class=PlainResponse)
def sitemap():
    articles = get_all_articles()
    base_url = "https://insight-webzine.onrender.com"
    
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml_content += f"  <url>\n    <loc>{base_url}/</loc>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>\n"
    for art in articles:
        art_id = art['id']
        xml_content += f"  <url>\n    <loc>{base_url}/?view={art_id}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n"
    xml_content += '</urlset>'
    return PlainResponse(content=xml_content, media_type="application/xml")

@app.get("/rss", response_class=PlainResponse)
def rss_feed():
    articles = get_all_articles()
    base_url = "https://insight-webzine.onrender.com"
    
    rss_content = '<?xml version="2.0" encoding="UTF-8" ?>\n'
    rss_content += '<rss version="2.0">\n<channel>\n'
    rss_content += '  <title>시사투데이 창</title>\n'
    rss_content += f'  <link>{base_url}/</link>\n'
    rss_content += '  <description>프리미엄 시사투데이 창 - 정치, 경제, 건강 및 지역 소식 트렌드 뉴스</description>\n'
    
    for art in articles:
        art_id = art['id']
        title = art['title'].replace('&', '&amp;')
        date_str = art['created_at']
        rss_content += '  <item>\n'
        rss_content += f'    <title>{title}</title>\n'
        rss_content += f'    <link>{base_url}/?view={art_id}</link>\n'
        rss_content += f'    <guid>{base_url}/?view={art_id}</guid>\n'
        rss_content += f'    <pubDate>{date_str}</pubDate>\n'
        rss_content += '  </item>\n'
        
    rss_content += '</channel>\n</rss>'
    return PlainResponse(content=rss_content, media_type="application/rss+xml")

@app.get("/ads.txt", response_class=PlainResponse)
def ads_txt():
    return PlainResponse("google.com, pub-0517985818592419, DIRECT, f08c47fec0942fa0", media_type="text/plain")

@app.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = None, view: int = None, q: str = None):
    subscribe_card_html = """
    <div class="author-subscribe-card">
        <div class="author-name">
            시사투데이 창 <span class="author-arrow">›</span>
        </div>
        <button type="button" class="btn-subscribe" onclick="subscribeNotice();">
            <svg class="sub-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7.5" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
            구독하기
        </button>
    </div>
    """

    subscribe_js = """
    <script>
    function subscribeNotice() {
        alert("⭐ [구독 및 바로가기 안내]\\n\\n'시사투데이 창'을 구독해 주셔서 감사합니다!\\n\\n아이폰: 하단 공유(📤) → [홈 화면에 추가]\\n갤럭시: 우측 상단 메뉴(⋮) → [현재 페이지 추가] → [홈 화면]\\n\\n스마트폰 바탕화면에서 매일 새로운 프리미엄 시사 칼럼을 바로 만나보실 수 있습니다.");
    }
    </script>
    """

    if view:
        art = get_article_by_id(view)
        if not art:
            return RedirectResponse(url="/", status_code=303)
        
        art_title_clean = art['title'].replace('"', '')
        art_desc_clean = art['content'][:100].replace('<p>', '').replace('</p>', '').replace('"', '')
        art_img = art['image_url']
        art_author = art.get('image_author', '')
        art_link = f"https://insight-webzine.onrender.com/?view={art['id']}"

        img_block = ""
        if art_img and art_img.strip():
            author_html = f'<div class="img-source">📷 Photo by {art_author}</div>' if art_author else ""
            img_block = f'<img src="{art_img}" class="article-img">{author_html}'

        detail_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{art_title_clean} - 시사투데이 창</title>
            <meta name="description" content="{art_desc_clean}">
            <meta property="og:title" content="{art_title_clean}">
            <meta property="og:description" content="{art_desc_clean}">
            <meta property="og:image" content="{art_img}">
            <meta property="og:url" content="{art_link}">
            <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-0517985818592419" crossorigin="anonymous"></script>
            {NAVER_ANALYTICS_SCRIPT}
            <style>
                body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; width: 100%; margin: 0 auto; padding: 15px; background: #f8f9fa; color: #111111; line-height: 1.8; box-sizing: border-box; }}
                .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                .back-btn {{ display: inline-block; padding: 6px 14px; background: #1b4f72; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 0.85em; transition: 0.2s; }}
                .back-btn:hover {{ background: #12334a; }}
                .article-container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }}
                .badge {{ display: none; }}
                h1 {{ font-size: 1.3em; color: #1a252f; margin-top: 10px; margin-bottom: 15px; line-height: 1.4; word-break: keep-all; letter-spacing: -0.5px; }}
                .date {{ font-size: 0.9em; color: #7f8c8d; margin-bottom: 25px; border-bottom: 1px solid #eaecee; padding-bottom: 15px; }}
                .article-img {{ width: 100%; max-height: 480px; object-fit: cover; border-radius: 8px; margin-bottom: 8px; display: block; }}
                .img-source {{ font-size: 0.85em; color: #95a5a6; margin-bottom: 30px; font-style: italic; text-align: left; }}
                .content {{ font-size: 1.02em; color: #111111; word-break: normal; text-align: left !important; line-height: 1.8; letter-spacing: -0.3px; }}
                .content p {{ margin-bottom: 24px; text-align: left !important; word-break: normal; }}
                
                .footer-search-box {{ background: white; padding: 18px 20px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); margin-top: 20px; text-align: center; }}
                .search-form {{ display: flex; gap: 8px; justify-content: center; width: 100%; max-width: 400px; margin: 0 auto; }}
                .search-input {{ padding: 10px 15px; border: 1px solid #ccc; border-radius: 20px; font-size: 0.95em; outline: none; flex-grow: 1; transition: 0.2s; }}
                .search-input:focus {{ border-color: #1b4f72; }}
                .search-btn {{ padding: 10px 20px; background: #1b4f72; color: white; border: none; border-radius: 20px; font-size: 0.95em; font-weight: bold; cursor: pointer; white-space: nowrap; }}
                .search-btn:hover {{ background: #12334a; }}
                
                .author-subscribe-card {{ display: flex; justify-content: space-between; align-items: center; background: white; border: 1px solid #e5e8ec; border-radius: 10px; padding: 14px 20px; margin-top: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); }}
                .author-name {{ font-size: 15px; font-weight: bold; color: #2c3e50; display: flex; align-items: center; gap: 5px; }}
                .author-arrow {{ color: #aaa; font-size: 14px; font-weight: normal; }}
                .btn-subscribe {{ display: inline-flex; align-items: center; gap: 6px; background: #ffffff; color: #333333; border: 1px solid #cfd4d9; border-radius: 4px; padding: 7px 14px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s ease; }}
                .btn-subscribe:hover {{ background: #f8f9fa; border-color: #aeb6bf; color: #111; }}
                .sub-icon {{ width: 14px; height: 14px; color: #555; }}

                img {{ max-width: 100% !important; height: auto !important; }}
                .article-img-box {{ margin: 25px auto !important; text-align: left !important; display: block !important; }}
            </style>
        </head>
        <body>
            <div class="top-bar">
                <a href="/" class="back-btn">← 메인 뉴스로 돌아가기</a>
            </div>

            <div class="article-container">
                <h1>{art['title']}</h1>
                <div class="date">발행일시: {art['created_at']}</div>
                {img_block}
                <div class="content">{art['content']}</div>
            </div>

            <div class="footer-search-box">
                <form action="/" method="get" class="search-form">
                    <input type="text" name="q" class="search-input" placeholder="🔍 기사 제목 또는 내용 검색...">
                    <button type="submit" class="search-btn">검색</button>
                </form>
            </div>
            
            {subscribe_card_html}
            {subscribe_js}
        </body>
        </html>
        """
        return detail_html

    articles = get_all_articles(category)
    
    if q and q.strip():
        keyword = q.strip().lower()
        articles = [a for a in articles if keyword in a['title'].lower() or keyword in a['content'].lower()]

    categories = ["전체", "정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]

    featured_articles = articles[:2] if articles else []
    featured_html = ""
    for art in featured_articles:
        cat_name = art['category'] if art['category'] else '종합'
        img_url = art['image_url'] if art['image_url'] else "https://images.unsplash.com/photo-1451187580459-43490279c0fa"
        featured_html += f"""
        <div class="featured-card">
            <div class="featured-img-wrap">
                <a href="/?view={art['id']}"><img src="{img_url}" class="featured-img"></a>
            </div>
            <div class="featured-body">
                <span class="badge">{cat_name}</span>
                <h3 class="featured-title"><a href="/?view={art['id']}">{art['title']}</a></h3>
                <div class="card-date">발행 | {art['created_at']}</div>
            </div>
        </div>
        """

    list_html = ""
    if category and category != "전체":
        cat_articles = articles if not (q and q.strip()) else articles
        chunked_list = [cat_articles[i:i+5] for i in range(0, len(cat_articles), 5)]
        for chunk in chunked_list:
            list_html += f'<div class="news-section-box">'
            list_html += f'<div class="section-header">📌 {category} 최신 리포트</div>'
            for art in chunk:
                list_html += f"""
                <div class="news-list-item">
                    <a href="/?view={art['id']}" class="list-title">{art['title']}</a>
                    <span class="list-date">{art['created_at'].split()[0]}</span>
                </div>
                """
            list_html += '</div>'
    else:
        display_cats = ["정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]
        for cat in display_cats:
            cat_arts = [a for a in articles if a.get('category') == cat][:5]
            if cat_arts:
                list_html += f'<div class="news-section-box">'
                list_html += f'<div class="section-header">📂 {cat} 최신 소식</div>'
                for art in cat_arts:
                    list_html += f"""
                    <div class="news-list-item">
                        <a href="/?view={art['id']}" class="list-title">{art['title']}</a>
                        <span class="list-date">{art['created_at'].split()[0]}</span>
                    </div>
                    """
                list_html += '</div>'
        
        other_arts = [a for a in articles if a.get('category') not in display_cats][:5]
        if other_arts and not category:
            list_html += f'<div class="news-section-box">'
            list_html += f'<div class="section-header">📰 종합 최신 소식</div>'
            for art in other_arts:
                list_html += f"""
                <div class="news-list-item">
                    <a href="/?view={art['id']}" class="list-title">{art['title']}</a>
                    <span class="list-date">{art['created_at'].split()[0]}</span>
                </div>
                """
            list_html += '</div>'

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>시사투데이 창 - 프리미엄 미디어</title>
        <meta name="description" content="AI, 경제, 주식, 건강 및 지역 소식을 전하는 프리미엄 시사투데이 창 미디어">
        <meta property="og:title" content="시사투데이 창">
        <meta property="og:description" content="AI, 경제, 주식, 건강 및 지역 소식을 전하는 프리미엄 시사투데이 창 미디어">
        <meta property="og:image" content="https://images.unsplash.com/photo-1451187580459-43490279c0fa">
        <meta property="og:url" content="https://insight-webzine.onrender.com/">
        <link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&display=swap" rel="stylesheet">
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-0517985818592419" crossorigin="anonymous"></script>
        {NAVER_ANALYTICS_SCRIPT}
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 900px; width: 100%; margin: 0 auto; padding: 10px; background: #f0f3f4; color: #333; box-sizing: border-box; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 4px solid #1b4f72; padding-bottom: 15px; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.05); flex-wrap: wrap; gap: 10px; }}
            
            .logo-title {{ font-family: 'Gowun Batang', 'Batang', serif; font-size: 1.6em; font-weight: 700; color: #1a252f; letter-spacing: -0.5px; display: flex; align-items: center; gap: 8px; }}
            .logo-chang {{ display: inline-block; background: #ffffff; color: #111111; border: 2.5px solid #111111; padding: 4px 16px; border-radius: 6px; font-family: 'Gowun Batang', 'Batang', serif; font-size: 1.1em; font-weight: 700; transform: rotate(5deg); box-shadow: 3px 3px 6px rgba(0,0,0,0.12); }}
            
            .nav-tabs {{ display: flex; gap: 5px; margin: 15px 0; flex-wrap: wrap; background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }}
            .tab-item {{ flex: 1; min-width: 75px; text-align: center; padding: 6px 4px; background: #ecf0f1; color: #555; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 12px; transition: 0.2s; white-space: nowrap; box-sizing: border-box; }}
            .tab-item:hover, .tab-item.active {{ background: #1b4f72; color: white; }}
            
            .featured-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 15px; margin-bottom: 20px; }}
            .featured-card {{ background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 3px 10px rgba(0,0,0,0.04); display: flex; flex-direction: column; }}
            .featured-img-wrap {{ width: 100%; height: 180px; overflow: hidden; background: #ddd; }}
            .featured-img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }}
            .featured-card:hover .featured-img {{ transform: scale(1.03); }}
            .featured-body {{ padding: 15px; display: flex; flex-direction: column; flex-grow: 1; }}
            .badge {{ display: inline-block; padding: 3px 8px; background: #ebf5fb; color: #2980b9; border-radius: 4px; font-size: 0.75em; font-weight: bold; margin-bottom: 8px; width: fit-content; }}
            .featured-title {{ font-size: 1.1em; color: #2c3e50; margin: 0 0 10px 0; line-height: 1.4; font-weight: 700; word-break: keep-all; }}
            .featured-title a {{ color: inherit; text-decoration: none; }}
            .featured-title a:hover {{ color: #2980b9; }}
            .card-date {{ font-size: 0.75em; color: #95a5a6; margin-top: auto; padding-top: 10px; border-top: 1px solid #f1f2f6; }}

            .news-section-box {{ background: white; border-radius: 10px; padding: 15px 20px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); margin-bottom: 15px; }}
            .section-header {{ font-size: 1.05em; font-weight: bold; color: #1b4f72; border-bottom: 2px solid #ebf5fb; padding-bottom: 8px; margin-bottom: 10px; }}
            
            .news-list-item {{ display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f8f9fa; }}
            .news-list-item:last-child {{ border-bottom: none; }}
            .list-title {{ flex-grow: 1; font-size: 0.96em; color: #2c3e50; text-decoration: none; font-weight: 600; word-break: keep-all; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 15px; }}
            .list-title:hover {{ color: #2980b9; text-decoration: underline; }}
            .list-date {{ font-size: 0.78em; color: #95a5a6; white-space: nowrap; }}

            .footer-search-box {{ background: white; padding: 18px 20px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); margin-top: 20px; text-align: center; }}
            .search-form {{ display: flex; gap: 8px; justify-content: center; width: 100%; max-width: 400px; margin: 0 auto; }}
            .search-input {{ padding: 10px 15px; border: 1px solid #ccc; border-radius: 20px; font-size: 0.95em; outline: none; flex-grow: 1; transition: 0.2s; }}
            .search-input:focus {{ border-color: #1b4f72; }}
            .search-btn {{ padding: 10px 20px; background: #1b4f72; color: white; border: none; border-radius: 20px; font-size: 0.95em; font-weight: bold; cursor: pointer; white-space: nowrap; }}
            .search-btn:hover {{ background: #12334a; }}
            
            .author-subscribe-card {{ display: flex; justify-content: space-between; align-items: center; background: white; border: 1px solid #e5e8ec; border-radius: 10px; padding: 14px 20px; margin-top: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); }}
            .author-name {{ font-size: 15px; font-weight: bold; color: #2c3e50; display: flex; align-items: center; gap: 5px; }}
            .author-arrow {{ color: #aaa; font-size: 14px; font-weight: normal; }}
            .btn-subscribe {{ display: inline-flex; align-items: center; gap: 6px; background: #ffffff; color: #333333; border: 1px solid #cfd4d9; border-radius: 4px; padding: 7px 14px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s ease; }}
            .btn-subscribe:hover {{ background: #f8f9fa; border-color: #aeb6bf; color: #111; }}
            .sub-icon {{ width: 14px; height: 14px; color: #555; }}

            img {{ max-width: 100% !important; height: auto !important; }}
            .article-img-box {{ margin: 25px auto !important; text-align: left !important; display: block !important; }}
        </style>
    </head>
    <body>
        <div class="header-flex">
            <div class="logo-title">
                시사투데이&nbsp;<span class="logo-chang">창</span>
            </div>
        </div>
        <div class="nav-tabs">
    """
    
    for cat in categories:
        active_class = "active" if (not category and cat == "전체") or (category == cat) else ""
        cat_param = "" if cat == "전체" else f"?category={cat}"
        html += f'<a href="/{cat_param}" class="tab-item {active_class}">{cat}</a>'
        
    html += "</div>"

    if not articles:
        html += "<p style='text-align:center; color:#777; margin-top:80px; font-size: 1.1em;'>등록된 기사가 없습니다.</p>"
    else:
        if featured_html:
            html += f'<div class="featured-grid">{featured_html}</div>'
        if list_html:
            html += f'{list_html}'
        
    html += f"""
        <div class="footer-search-box">
            <form action="/" method="get" class="search-form">
                {'<input type="hidden" name="category" value="' + category + '">' if category else ''}
                <input type="text" name="q" class="search-input" placeholder="🔍 기사 제목 또는 내용 검색..." value="{q if q else ''}">
                <button type="submit" class="search-btn">검색</button>
            </form>
        </div>
        
        {subscribe_card_html}
        {subscribe_js}
    """

    html += "</body></html>"
    return html

@app.get("/admin", response_class=HTMLResponse)
def admin_login_page(request: Request, error: str = None):
    err_msg = "<p style='color: #e74c3c; font-size: 0.9em; margin-bottom: 15px;'>비밀번호가 틀렸습니다!</p>" if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>관리자 로그인</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; background: #f0f3f4; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; box-sizing: border-box; padding: 15px; }}
            .login-box {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); width: 100%; max-width: 320px; text-align: center; }}
            h2 {{ color: #1b4f72; margin-bottom: 20px; }}
            input[type="password"] {{ width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; font-size: 16px; text-align: center; }}
            button {{ width: 100%; padding: 12px; background: #1b4f72; color: white; border: none; border-radius: 5px; font-weight: bold; font-size: 16px; cursor: pointer; }}
            button:hover {{ background: #12334a; }}
            .back-link {{ display: block; margin-top: 15px; color: #7f8c8d; text-decoration: none; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 관리자 인증</h2>
            {err_msg}
            <form action="/admin/login" method="post">
                <input type="password" name="password" placeholder="비밀번호를 입력하세요" required autofocus>
                <button type="submit">로그인</button>
            </form>
            <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        </div>
    </body>
    </html>
    """

@app.post("/admin/login")
def admin_login(response: Response, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        resp = RedirectResponse(url="/admin/studio", status_code=303)
        resp.set_cookie(key="admin_auth", value="authenticated", max_age=86400)
        return resp
    else:
        return RedirectResponse(url="/admin?error=true", status_code=303)

@app.get("/admin/studio", response_class=HTMLResponse)
def admin_studio(request: Request, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)

    rows = get_all_articles()

    articles_list_html = ""
    for r in rows:
        articles_list_html += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 12px 10px; font-size: 0.9em; color: #555;">{r['category']}</td>
            <td style="padding: 12px 10px; font-weight: bold;"><a href="/?view={r['id']}" target="_blank" style="color: #2980b9; text-decoration: none;">{r['title']}</a></td>
            <td style="padding: 12px 10px; font-size: 0.85em; color: #777; white-space: nowrap;">{r['created_at']}</td>
            <td style="padding: 12px 10px; text-align: right; white-space: nowrap;">
                <a href="/admin/edit/{r['id']}" style="background: #f39c12; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 4px; display: inline-block;">✏️ 수정</a>
                <a href="/admin/delete/{r['id']}" style="background: #e74c3c; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block;" onclick="return confirm('정말 이 기사를 삭제하시겠습니까?');">🗑️ 삭제</a>
            </td>
        </tr>
        """

    if not articles_list_html:
        articles_list_html = "<tr><td colspan='4' style='padding: 20px; text-align: center; color: #777;'>등록된 기사가 없습니다.</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>시사투데이 창 관리자 스튜디오</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 900px; width: 100%; margin: 0 auto; padding: 15px; background: #f4f6f7; box-sizing: border-box; }}
            h1 {{ color: #2c3e50; font-size: 1.5em; }}
            .box {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #27ae60; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }}
            button:hover {{ background: #219653; }}
            .manual-btn {{ background: #2980b9; }}
            .manual-btn:hover {{ background: #1f618d; }}
            .ai-expand-btn {{ background: #8e44ad; }}
            .ai-expand-btn:hover {{ background: #732d91; }}
            input[type="text"], select, textarea {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }}
            textarea {{ height: 150px; resize: vertical; }}
            label {{ font-weight: bold; color: #34495e; display: block; margin-top: 10px; }}
            .back-link {{ display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            
            .hub-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 12px; }}
            .hub-btn {{ display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 14px; border-radius: 8px; font-weight: bold; font-size: 13.5px; text-decoration: none; color: white; transition: transform 0.2s, opacity 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.08); text-align: center; }}
            .hub-btn:hover {{ opacity: 0.92; transform: translateY(-1px); }}
            .hub-btn-naver-a {{ background: #03c75a; }}
            .hub-btn-naver-s {{ background: #1f9c53; }}
            .hub-btn-google-gsc {{ background: #4285f4; }}
            .hub-btn-google-ga {{ background: #ea4335; }}

            .img-tool-box {{ background: #fdfefe; border: 1px solid #d6dbdf; border-radius: 6px; padding: 12px; margin-bottom: 15px; }}
            .img-tool-title {{ font-size: 13px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
            .img-tool-row {{ display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
            .img-tool-row input[type="text"] {{ margin-top: 0; margin-bottom: 0; }}
            .btn-action {{ width: auto; padding: 8px 14px; font-size: 13px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; color: white; white-space: nowrap; }}
            
            .custom-head-box {{ background: #fcf3cf; border: 1.5px solid #f39c12; border-radius: 6px; padding: 14px; margin-top: 10px; margin-bottom: 15px; }}
            .checkbox-label {{ display: flex; align-items: center; gap: 8px; font-weight: bold; color: #7d6608; cursor: pointer; margin-top: 0; }}
            .preview-box-img {{ max-width: 180px; max-height: 100px; border-radius: 4px; margin-top: 8px; display: none; }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <h1>🛡️ 시사투데이 창 관리자 스튜디오</h1>
        
        <div class="box" style="border-top: 5px solid #2ecc71;">
            <h3>📊 통계 분석 & 검색엔진 허브 센터</h3>
            <p style="color: #666; font-size: 0.9em; margin-top: 6px; line-height: 1.6;">
                네이버와 구글의 공식 대시보드로 바로 연결됩니다. 검색 유입 및 색인 현황, 정밀 트래픽을 안전하게 확인하세요.
            </p>
            <div class="hub-grid">
                <a href="https://analytics.naver.com/" target="_blank" class="hub-btn hub-btn-naver-a">
                    🟢 네이버 애널리틱스
                </a>
                <a href="https://searchadvisor.naver.com/" target="_blank" class="hub-btn hub-btn-naver-s">
                    🟢 네이버 서치어드바이저
                </a>
                <a href="https://search.google.com/search-console" target="_blank" class="hub-btn hub-btn-google-gsc">
                    🔵 구글 서치 콘솔
                </a>
                <a href="https://analytics.google.com/" target="_blank" class="hub-btn hub-btn-google-ga">
                    🔴 구글 애널리틱스(GA4)
                </a>
            </div>
        </div>

        <div class="box" style="border-top: 5px solid #27ae60;">
            <h3>🤖 1. 상단: AI 자동 기사 발행 (실시간 맞춤형 핫이슈 취재)</h3>
            <form action="/admin/create-auto" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사 (국회·실명인물·법안·여야 쟁점)</option>
                    <option value="경제/주식">경제/주식 (주도 테마주·코스피·금리·실전상식)</option>
                    <option value="세상이야기">세상이야기 (구체적 사건경위·감동 미담 팩트)</option>
                    <option value="AI/테크">AI/테크 (제미니·클로드·챗GPT·딥시크 비교분석)</option>
                    <option value="건강/복지">건강/복지 (정부 복지 수혜 자격·의학적 지침)</option>
                    <option value="생활정보">생활정보 (부동산 절세 기준·알짜 생활 꿀팁)</option>
                    <option value="연예계뉴스">연예계뉴스 (화제의 인물 실명·프로그램·트렌드)</option>
                    <option value="스포츠">스포츠 (팀명·선수실명·스코어·결정적 승부처)</option>
                    <option value="지역창">지역창 (속초·강원 명소·축제·맛집 구체정보)</option>
                </select>
                <button type="submit">🚀 타깃 맞춤형 실시간 기사 자동 발행</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #2980b9;">
            <h3>✍️ 2. 중단: 완전 수동 글 작성</h3>
            <form action="/admin/create-manual" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option>
                    <option value="건강/복지">건강/복지</option>
                    <option value="생활정보">생활정보</option>
                    <option value="연예계뉴스">연예계뉴스</option>
                    <option value="스포츠">스포츠</option>
                    <option value="지역창">지역창</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목을 입력하세요" required>
                
                <div class="custom-head-box">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_unsplash" id="manual_use_unsplash" value="yes" checked onchange="toggleHeadImgSection('manual')">
                        <span>🖼️ 언스플래시(Unsplash) 자동 대표 이미지 사용하기 (체크 해제 시 내가 직접 지정한 이미지 적용)</span>
                    </label>
                    <div id="manual_custom_head_wrap" style="display: none; margin-top: 12px; border-top: 1px dashed #e59866; padding-top: 10px;">
                        <small style="color: #a04000; font-weight: bold; display: block; margin-bottom: 6px;">[수동 대표 이미지 설정] 아래에 이미지 URL 또는 내 기기 사진을 올려주세요.</small>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" name="custom_image_url" id="manual_head_url" placeholder="직접 넣을 대표 이미지 주소(URL)" style="margin-bottom: 8px; flex: 1;">
                            <button type="button" class="btn-action" style="background: #16a085; height: 42px; margin-top: 8px;" onclick="document.getElementById('manual_head_file').click()">📁 내 기기 파일</button>
                            <input type="file" id="manual_head_file" style="display: none;" accept="image/*" onchange="uploadDirectHeadImage(this, 'manual_head_url', 'manual_head_preview')">
                        </div>
                        <input type="text" name="custom_image_author" placeholder="대표 이미지 출처 표기 (예: 연합뉴스, 독자 제공, pexels 등)" style="margin-bottom: 4px;">
                        <img id="manual_head_preview" class="preview-box-img">
                    </div>
                </div>

                <label>기사 본문 및 이미지 삽입</label>
                <div class="img-tool-box">
                    <div class="img-tool-title">📷 본문 이미지 삽입 및 출처(Credit) 입력</div>
                    <div class="img-tool-row">
                        <input type="text" id="manual_source" placeholder="출처 표기 (예: pexels, 연합뉴스, 국회방송 캡처 등)" style="flex: 1;">
                    </div>
                    <div class="img-tool-row">
                        <button type="button" class="btn-action" style="background: #e67e22;" onclick="insertImageWithSource('manualContent', 'manual_source')">🌐 URL 주소로 넣기</button>
                        <button type="button" class="btn-action" style="background: #16a085;" onclick="document.getElementById('manual_file_input').click()">📁 내 기기 파일 올리기</button>
                        <input type="file" id="manual_file_input" style="display: none;" accept="image/*" onchange="uploadImageWithSource(this, 'manualContent', 'manual_source')">
                    </div>
                </div>

                <textarea name="content" id="manualContent" placeholder="내용을 직접 작성하세요..." required></textarea>
                <button type="submit" class="manual-btn">📝 직접 작성한 글 발행하기</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #8e44ad;">
            <h3>✨ 3. 하단: AI 프롬프트 확장 발행</h3>
            <form action="/admin/create-ai-expand" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option>
                    <option value="건강/복지">건강/복지</option>
                    <option value="생활정보">생활정보</option>
                    <option value="연예계뉴스">연예계뉴스</option>
                    <option value="스포츠">스포츠</option>
                    <option value="지역창">지역창</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="기사 제목을 입력하세요" required>
                
                <div class="custom-head-box">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_unsplash" id="expand_use_unsplash" value="yes" checked onchange="toggleHeadImgSection('expand')">
                        <span>🖼️ 언스플래시(Unsplash) 자동 대표 이미지 사용하기 (체크 해제 시 내가 직접 지정한 이미지 적용)</span>
                    </label>
                    <div id="expand_custom_head_wrap" style="display: none; margin-top: 12px; border-top: 1px dashed #e59866; padding-top: 10px;">
                        <small style="color: #a04000; font-weight: bold; display: block; margin-bottom: 6px;">[수동 대표 이미지 설정] 아래에 이미지 URL 또는 내 기기 사진을 올려주세요.</small>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" name="custom_image_url" id="expand_head_url" placeholder="직접 넣을 대표 이미지 주소(URL)" style="margin-bottom: 8px; flex: 1;">
                            <button type="button" class="btn-action" style="background: #16a085; height: 42px; margin-top: 8px;" onclick="document.getElementById('expand_head_file').click()">📁 내 기기 파일</button>
                            <input type="file" id="expand_head_file" style="display: none;" accept="image/*" onchange="uploadDirectHeadImage(this, 'expand_head_url', 'expand_head_preview')">
                        </div>
                        <input type="text" name="custom_image_author" placeholder="대표 이미지 출처 표기 (예: 연합뉴스, 독자 제공, pexels 등)" style="margin-bottom: 4px;">
                        <img id="expand_head_preview" class="preview-box-img">
                    </div>
                </div>

                <label>AI 확장용 프롬프트 / 메모 및 본문 추가 이미지</label>
                <div class="img-tool-box">
                    <div class="img-tool-title">📷 본문 추가 이미지 삽입 및 출처(Credit) 입력</div>
                    <div class="img-tool-row">
                        <input type="text" id="expand_source" placeholder="출처 표기 (예: pexels, 연합뉴스, 픽사베이 등)" style="flex: 1;">
                    </div>
                    <div class="img-tool-row">
                        <button type="button" class="btn-action" style="background: #e67e22;" onclick="insertImageWithSource('expandPrompt', 'expand_source')">🌐 URL 주소로 넣기</button>
                        <button type="button" class="btn-action" style="background: #16a085;" onclick="document.getElementById('expand_file_input').click()">📁 내 기기 파일 올리기</button>
                        <input type="file" id="expand_file_input" style="display: none;" accept="image/*" onchange="uploadImageWithSource(this, 'expandPrompt', 'expand_source')">
                    </div>
                </div>

                <textarea name="prompt" id="expandPrompt" placeholder="예: 챗GPT와 제미니의 최신 기능 비교 및 직장인 실무 활용 꿀팁을 알기 쉽게 정리해줘." required></textarea>
                <button type="submit" class="ai-expand-btn">🪄 명품 신문 스타일 기사 발행하기</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #34495e;">
            <h3>📋 4. 발행된 기사 관리 및 삭제 대장</h3>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr style="border-bottom: 2px solid #ccc; text-align: left;">
                            <th style="padding: 10px;">카테고리</th>
                            <th style="padding: 10px;">기사 제목</th>
                            <th style="padding: 10px;">발행일시</th>
                            <th style="padding: 10px; text-align: right;">관리</th>
                        </tr>
                    </thead>
                    <tbody>
                        {articles_list_html}
                    </tbody>
                </table>
            </div>
        </div>

        <script>
        function toggleHeadImgSection(type) {{
            const chk = document.getElementById(type + '_use_unsplash');
            const wrap = document.getElementById(type + '_custom_head_wrap');
            if (!chk.checked) {{
                wrap.style.display = 'block';
            }} else {{
                wrap.style.display = 'none';
            }}
        }}

        async function uploadDirectHeadImage(input, urlInputId, previewImgId) {{
            if (input.files && input.files[0]) {{
                const formData = new FormData();
                formData.append("file", input.files[0]);
                try {{
                    const response = await fetch("/admin/upload-image", {{
                        method: "POST",
                        body: formData
                    }});
                    const data = await response.json();
                    if (data.url) {{
                        document.getElementById(urlInputId).value = data.url;
                        const preview = document.getElementById(previewImgId);
                        preview.src = data.url;
                        preview.style.display = 'block';
                        alert("대표 이미지가 성공적으로 등록되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "오류"));
                    }}
                }} catch (err) {{
                    alert("업로드 오류: " + err);
                }}
                input.value = "";
            }}
        }}

        function injectHtmlTag(elementId, imgUrl, sourceText) {{
            let captionHtml = "";
            let cleanSource = sourceText ? sourceText.trim() : "";
            if (cleanSource !== "") {{
                if (!cleanSource.toLowerCase().startsWith("photo by") && !cleanSource.startsWith("Photo by")) {{
                    cleanSource = "Photo by " + cleanSource;
                }}
                captionHtml = '<div class="img-source" style="margin-top: 8px !important; margin-bottom: 24px !important; font-size: 0.85em !important; color: #95a5a6 !important; font-style: italic !important; text-align: left !important; display: block !important;">📷 ' + cleanSource + '</div>';
            }}
            const tag = '\\n<div class="article-img-box" style="margin: 25px auto 10px auto; text-align: left; max-width: 100%; display: block;"><img src="' + imgUrl.trim() + '" style="width: 100%; max-width: 100%; border-radius: 8px; display: block;" alt="기사 이미지">' + captionHtml + '</div>\\n';
            
            const textarea = document.getElementById(elementId);
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
            textarea.focus();
        }}

        function insertImageWithSource(elementId, sourceInputId) {{
            const url = prompt("넣을 이미지의 웹 주소(URL)를 입력하세요:");
            if (url) {{
                const source = document.getElementById(sourceInputId).value;
                injectHtmlTag(elementId, url, source);
                document.getElementById(sourceInputId).value = "";
            }}
        }}

        async function uploadImageWithSource(input, elementId, sourceInputId) {{
            if (input.files && input.files[0]) {{
                const formData = new FormData();
                formData.append("file", input.files[0]);
                
                try {{
                    const response = await fetch("/admin/upload-image", {{
                        method: "POST",
                        body: formData
                    }});
                    const data = await response.json();
                    if (data.url) {{
                        const source = document.getElementById(sourceInputId).value;
                        injectHtmlTag(elementId, data.url, source);
                        document.getElementById(sourceInputId).value = "";
                        alert("사진과 출처가 성공적으로 본문에 삽입되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "알 수 없는 오류"));
                    }}
                }} catch (err) {{
                    alert("사진 업로드 중 오류 발생: " + err);
                }}
                input.value = "";
            }}
        }}
        </script>
    </body>
    </html>
    """

@app.post("/admin/create-auto")
def create_auto(category: str = Form(...), admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    generate_ai_article(category)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.post("/admin/create-manual")
def create_manual(
    category: str = Form(...), 
    title: str = Form(...), 
    content: str = Form(...), 
    use_unsplash: str = Form(None),
    custom_image_url: str = Form(None),
    custom_image_author: str = Form(None),
    admin_auth: str = Cookie(None)
):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = title.replace('**', '').replace('*', '').strip()
    
    if not use_unsplash and custom_image_url and custom_image_url.strip():
        img_url = custom_image_url.strip()
        author_name = custom_image_author.strip() if custom_image_author else ""
    else:
        img_url, author_name = fetch_bulletproof_image(category)
    
    formatted_content = clean_and_format_content(content, category, clean_title)
    save_article_to_db(category, clean_title, formatted_content, img_url, author_name)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.post("/admin/create-ai-expand")
def create_ai_expand(
    category: str = Form(...), 
    title: str = Form(...), 
    prompt: str = Form(...), 
    use_unsplash: str = Form(None),
    custom_image_url: str = Form(None),
    custom_image_author: str = Form(None),
    admin_auth: str = Cookie(None)
):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = title.replace('**', '').replace('*', '').strip()
    system_directive = (
        "당신은 전문 수석 언론사 기자입니다. "
        "사용자가 제공한 [기사 제목]과 [핵심 취재 메모]를 바탕으로 완성도 높은 정식 뉴스 기사 본문을 작성하세요.\n"
        "1. 서론에서 육하원칙(누가, 언제, 어디서, 무엇을, 어떻게, 왜)을 분명히 서술하고, 최소 4개 이상의 문단으로 구성하세요.\n"
        "2. 각 문단 앞에는 '### 소제목' 형태로 세련된 소제목을 붙이되, '[기]', '[승]', '[전]', '[결]' 같은 설명용 라벨은 절대 쓰지 마세요.\n"
        "3. 만약 사용자의 취재 메모 안에 <div class=\"article-img-box\"나 <img 등 HTML 태그가 있다면 삭제하지 말고 본문 흐름에 맞게 그대로 포함하세요.\n"
        "4. 본문 시작 부분에 기사 제목을 다시 적지 마세요. 바로 첫 단락의 내용으로 시작하세요.\n"
        "5. 마크다운 특수기호(-, *, _)는 쓰지 말고 표준적인 한국어 보도체(~다)로 명확하게 서술하세요.\n"
        "6. 본문 끝에 해시태그는 직접 작성하지 마세요."
    )
    
    full_query = f"{system_directive}\n\n[기사 제목]: {clean_title}\n[핵심 취재 메모]: {prompt}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_query,
        )
        final_content = response.text.strip()
    except Exception as e:
        print(f"🚨 [Gemini 기사 확장 생성 에러]: {e}")
        final_content = f"기사 본문 생성 중 API 오류가 발생했습니다: {e}\n\n취재 메모:\n{prompt}"

    if not use_unsplash and custom_image_url and custom_image_url.strip():
        img_url = custom_image_url.strip()
        author_name = custom_image_author.strip() if custom_image_author else ""
    else:
        img_url, author_name = fetch_bulletproof_image(category)

    final_content = clean_and_format_content(final_content, category, clean_title)
    save_article_to_db(category, clean_title, final_content, img_url, author_name)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.get("/admin/edit/{article_id}", response_class=HTMLResponse)
def edit_page(article_id: int, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)

    art = get_article_by_id(article_id)
    if not art:
        return RedirectResponse(url="/admin/studio", status_code=303)

    current_img = art.get('image_url', '') or ''
    current_author = art.get('image_author', '') or ''

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>기사 수정하기</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; width: 100%; margin: 0 auto; padding: 15px; background: #f4f6f7; box-sizing: border-box; }}
            h1 {{ color: #2c3e50; font-size: 1.5em; }}
            .box {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #f39c12; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }}
            button:hover {{ background: #d68910; }}
            input[type="text"], select, textarea {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }}
            textarea {{ height: 250px; resize: vertical; }}
            label {{ font-weight: bold; color: #34495e; display: block; margin-top: 10px; }}
            .back-link {{ display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }}
            .preview-img {{ max-width: 200px; max-height: 120px; border-radius: 6px; margin-top: 5px; display: block; }}
            
            .img-tool-box {{ background: #fdfefe; border: 1px solid #d6dbdf; border-radius: 6px; padding: 12px; margin-bottom: 15px; }}
            .img-tool-title {{ font-size: 13px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
            .img-tool-row {{ display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
            .img-tool-row input[type="text"] {{ margin-top: 0; margin-bottom: 0; }}
            .btn-action {{ width: auto; padding: 8px 14px; font-size: 13px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; color: white; white-space: nowrap; }}
            
            .header-img-box {{ background: #f8f9fa; border: 1.5px dashed #bdc3c7; border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <a href="/admin/studio" class="back-link">← 관리자 스튜디오로 돌아가기</a>
        <div class="box">
            <h1>✏️ 기사 및 대표 이미지 수정하기</h1>
            <form action="/admin/update/{art['id']}" method="post">
                <label>카테고리</label>
                <select name="category">
                    <option value="정치/시사" {"selected" if art['category']=="정치/시사" else ""}>정치/시사</option>
                    <option value="경제/주식" {"selected" if art['category']=="경제/주식" else ""}>경제/주식</option>
                    <option value="세상이야기" {"selected" if art['category']=="세상이야기" else ""}>세상이야기</option>
                    <option value="AI/테크" {"selected" if art['category']=="AI/테크" else ""}>AI/테크</option>
                    <option value="건강/복지" {"selected" if art['category']=="건강/복지" else ""}>건강/복지</option>
                    <option value="생활정보" {"selected" if art['category']=="생활정보" else ""}>생활정보</option>
                    <option value="연예계뉴스" {"selected" if art['category']=="연예계뉴스" else ""}>연예계뉴스</option>
                    <option value="스포츠" {"selected" if art['category']=="스포츠" else ""}>스포츠</option>
                    <option value="지역창" {"selected" if art['category']=="지역창" else ""}>지역창</option>
                </select>
                
                <label>기사 제목</label>
                <input type="text" name="title" value="{art['title']}" required>
                
                <div class="header-img-box">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <span style="font-weight: bold; color: #2c3e50; font-size: 14px;">🖼️ 기사 상단 대표 이미지 및 출처 설정</span>
                        <button type="button" onclick="clearMainImage()" style="width: auto; background: #e74c3c; padding: 5px 12px; font-size: 12px; border-radius: 4px;">🗑️ 대표 이미지 완전 삭제</button>
                    </div>

                    <label style="margin-top: 5px; font-size: 13px;">대표 이미지 주소(URL)</label>
                    <div style="display: flex; gap: 8px;">
                        <input type="text" id="main_img_url" name="image_url" value="{current_img}" placeholder="새로운 이미지 주소를 입력하세요" style="flex: 1; margin-bottom: 8px;">
                        <button type="button" onclick="document.getElementById('main_img_file').click()" class="btn-action" style="background: #16a085; height: 42px; margin-top: 8px;">📁 내 파일 올리기</button>
                        <input type="file" id="main_img_file" style="display: none;" accept="image/*" onchange="uploadMainImageFile(this)">
                    </div>

                    <label style="margin-top: 5px; font-size: 13px;">대표 이미지 출처 표기</label>
                    <input type="text" id="main_img_author" name="image_author" value="{current_author}" placeholder="출처를 입력하세요 (예: pexels, 연합뉴스, 기본소득당 제공 등)" style="margin-bottom: 8px;">
                    
                    <small style="color: #7f8c8d; display: block; margin-top: 4px;">현재 등록된 대표 이미지 미리보기:</small>
                    <img id="main_img_preview" src="{current_img}" class="preview-img" onerror="this.style.display='none'">
                </div>

                <label>기사 내용 및 본문 추가 이미지</label>
                <div class="img-tool-box">
                    <div class="img-tool-title">📷 본문 이미지 삽입 및 출처(Credit) 입력</div>
                    <div class="img-tool-row">
                        <input type="text" id="edit_source" placeholder="출처 표기 (예: pexels, 연합뉴스, 국회방송 캡처 등)" style="flex: 1;">
                    </div>
                    <div class="img-tool-row">
                        <button type="button" class="btn-action" style="background: #e67e22;" onclick="insertImageWithSource('editContent', 'edit_source')">🌐 URL 주소로 넣기</button>
                        <button type="button" class="btn-action" style="background: #16a085;" onclick="document.getElementById('edit_file_input').click()">📁 내 기기 파일 올리기</button>
                        <input type="file" id="edit_file_input" style="display: none;" accept="image/*" onchange="uploadImageWithSource(this, 'editContent', 'edit_source')">
                    </div>
                </div>

                <textarea name="content" id="editContent" required>{art['content']}</textarea>
                
                <button type="submit">💾 수정 사항 저장하기</button>
            </form>
        </div>

        <script>
        function clearMainImage() {{
            document.getElementById('main_img_url').value = '';
            document.getElementById('main_img_author').value = '';
            const preview = document.getElementById('main_img_preview');
            preview.src = '';
            preview.style.display = 'none';
            alert("대표 이미지와 출처가 삭제되었습니다. 하단의 [수정 사항 저장하기]를 누르면 완전히 반영됩니다.");
        }}

        async function uploadMainImageFile(input) {{
            if (input.files && input.files[0]) {{
                const formData = new FormData();
                formData.append("file", input.files[0]);
                try {{
                    const response = await fetch("/admin/upload-image", {{
                        method: "POST",
                        body: formData
                    }});
                    const data = await response.json();
                    if (data.url) {{
                        document.getElementById('main_img_url').value = data.url;
                        const preview = document.getElementById('main_img_preview');
                        preview.src = data.url;
                        preview.style.display = 'block';
                        alert("대표 이미지가 업로드되었습니다. 아래 출처 입력란에 출처를 적어주세요.");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "알 수 없는 오류"));
                    }}
                }} catch (err) {{
                    alert("사진 업로드 중 오류 발생: " + err);
                }}
                input.value = "";
            }}
        }}

        function injectHtmlTag(elementId, imgUrl, sourceText) {{
            let captionHtml = "";
            let cleanSource = sourceText ? sourceText.trim() : "";
            if (cleanSource !== "") {{
                if (!cleanSource.toLowerCase().startsWith("photo by") && !cleanSource.startsWith("Photo by")) {{
                    cleanSource = "Photo by " + cleanSource;
                }}
                captionHtml = '<div class="img-source" style="margin-top: 8px !important; margin-bottom: 24px !important; font-size: 0.85em !important; color: #95a5a6 !important; font-style: italic !important; text-align: left !important; display: block !important;">📷 ' + cleanSource + '</div>';
            }}
            const tag = '\\n<div class="article-img-box" style="margin: 25px auto 10px auto; text-align: left; max-width: 100%; display: block;"><img src="' + imgUrl.trim() + '" style="width: 100%; max-width: 100%; border-radius: 8px; display: block;" alt="기사 이미지">' + captionHtml + '</div>\\n';
            
            const textarea = document.getElementById(elementId);
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
            textarea.focus();
        }}

        function insertImageWithSource(elementId, sourceInputId) {{
            const url = prompt("넣을 이미지의 웹 주소(URL)를 입력하세요:");
            if (url) {{
                const source = document.getElementById(sourceInputId).value;
                injectHtmlTag(elementId, url, source);
                document.getElementById(sourceInputId).value = "";
            }}
        }}

        async function uploadImageWithSource(input, elementId, sourceInputId) {{
            if (input.files && input.files[0]) {{
                const formData = new FormData();
                formData.append("file", input.files[0]);
                
                try {{
                    const response = await fetch("/admin/upload-image", {{
                        method: "POST",
                        body: formData
                    }});
                    const data = await response.json();
                    if (data.url) {{
                        const source = document.getElementById(sourceInputId).value;
                        injectHtmlTag(elementId, data.url, source);
                        document.getElementById(sourceInputId).value = "";
                        alert("사진과 출처가 성공적으로 본문에 삽입되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "알 수 없는 오류"));
                    }}
                }} catch (err) {{
                    alert("사진 업로드 중 오류 발생: " + err);
                }}
                input.value = "";
            }}
        }}
        </script>
    </body>
    </html>
    """

@app.post("/admin/update/{article_id}")
def update_article(
    article_id: int, 
    category: str = Form(...), 
    title: str = Form(...), 
    content: str = Form(...), 
    image_url: str = Form(None), 
    image_author: str = Form(None), 
    admin_auth: str = Cookie(None)
):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = title.replace('**', '').replace('*', '').strip()
    update_article_in_db(article_id, category, clean_title, content, image_url, image_author)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.get("/admin/delete/{article_id}")
def delete_article(article_id: int, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    delete_article_from_db(article_id)
    return RedirectResponse(url="/admin/studio", status_code=303)
