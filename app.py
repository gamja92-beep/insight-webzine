import sys
import os
import sqlite3
import random
import time
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Form, Request, Response, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response as PlainResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from supabase import create_client, Client

app = FastAPI()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

API_KEY = os.environ.get("API_KEY", "")
MODEL_NAME = "gemini-3.6-flash"

ADMIN_PASSWORD = "1234"

client = genai.Client(api_key=API_KEY)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_SITE_URL = "https://insight-webzine.onrender.com"

# 🚀 [IndexNow 자동 전송 함수]: 빙, 야후 등 글로벌 검색엔진에 실시간 색인 요청
def ping_indexnow(url_path):
    try:
        target_url = f"{BASE_SITE_URL}{url_path}"
        host_domain = "insight-webzine.onrender.com"
        key_str = "siyatodaychangkey2026"
        
        payload = {
            "host": host_domain,
            "key": key_str,
            "keyLocation": f"{BASE_SITE_URL}/{key_str}.txt",
            "urlList": [target_url]
        }
        
        req = urllib.request.Request(
            "https://api.indexnow.org/indexnow",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'Mozilla/5.0'}
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"[IndexNow 알림 전송 실패]: {e}")

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

GOOGLE_ANALYTICS_SCRIPT = """
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=YOUR_GA_MEASUREMENT_ID"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'YOUR_GA_MEASUREMENT_ID');
</script>
"""

NEWS_FEEDS = {
    "정치/시사": "https://news.google.com/rss/headlines/section/topic/POLITICS?hl=ko&gl=KR&ceid=KR:ko",
    "경제/주식": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    "세상이야기": "https://news.google.com/rss/headlines/section/topic/NATION?hl=ko&gl=KR&ceid=KR:ko",
    "AI/테크": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
    "건강/복지": "https://news.google.com/rss/search?q=건강+복지+시니어+의료&hl=ko&gl=KR&ceid=KR:ko",
    "생활정보": "https://news.google.com/rss/search?q=부동산+물가+생활정보+지원금&hl=ko&gl=KR&ceid=KR:ko",
    "연예계뉴스": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=ko&gl=KR&ceid=KR:ko",
    "스포츠": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=ko&gl=KR&ceid=KR:ko",
    "지역창": "https://news.google.com/rss/search?q=강원+속초+축제+관광+소식&hl=ko&gl=KR&ceid=KR:ko"
}

def get_latest_realtime_news(category_name):
    feed_url = NEWS_FEEDS.get(category_name, NEWS_FEEDS["세상이야기"])
    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        items = root.findall('./channel/item')
        if items:
            chosen = random.choice(items[:4])
            title = chosen.findtext('title') or ''
            desc = chosen.findtext('description') or ''
            pub_date = chosen.findtext('pubDate') or ''
            clean_desc = re.sub(r'<[^>]+>', '', desc).strip()
            return title.strip(), clean_desc, pub_date.strip()
    except Exception as e:
        print(f"[실시간 뉴스 수집 알림]: {e}")
    return "", "", ""

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

SMART_IMAGE_POOLS = {
    "정치/시사": [
        ("https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=900&auto=format&fit=crop", "Government Briefing"),
        ("https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=900&auto=format&fit=crop", "National Assembly"),
        ("https://images.unsplash.com/photo-1555848962-6e79363ec58f?w=900&auto=format&fit=crop", "Public Policy"),
        ("https://images.unsplash.com/photo-1575505586569-646b2ca898fc?w=900&auto=format&fit=crop", "Political Forum"),
        ("https://images.unsplash.com/photo-1540910419892-4a36d2c3266c?w=900&auto=format&fit=crop", "Diplomacy"),
        ("https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop", "Civic Center"),
        ("https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=900&auto=format&fit=crop", "Global Issue"),
        ("https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=900&auto=format&fit=crop", "Metropolitan Hall"),
        ("https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=900&auto=format&fit=crop", "Conference Room"),
        ("https://images.unsplash.com/photo-1521791136064-7986c2920216?w=900&auto=format&fit=crop", "Strategic Meeting")
    ],
    "경제/주식": [
        ("https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=900&auto=format&fit=crop", "Stock Market"),
        ("https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=900&auto=format&fit=crop", "Trading Floor"),
        ("https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=900&auto=format&fit=crop", "Corporate Tower"),
        ("https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=900&auto=format&fit=crop", "Financial District"),
        ("https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=900&auto=format&fit=crop", "Economic Growth"),
        ("https://images.unsplash.com/photo-1563986768609-322da13575f3?w=900&auto=format&fit=crop", "Digital Banking"),
        ("https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=900&auto=format&fit=crop", "Business Strategy"),
        ("https://images.unsplash.com/photo-1535320903710-d993d3d77d29?w=900&auto=format&fit=crop", "Investment Chart"),
        ("https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop", "Enterprise Plaza"),
        ("https://images.unsplash.com/photo-1579532537598-459ecdaf39cc?w=900&auto=format&fit=crop", "Market Trends")
    ],
    "세상이야기": [
        ("https://images.unsplash.com/photo-1477959858617-67f30bc75b82?w=900&auto=format&fit=crop", "City Scenery"),
        ("https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=900&auto=format&fit=crop", "Nature Valley"),
        ("https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=900&auto=format&fit=crop", "Scenic Horizon"),
        ("https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=900&auto=format&fit=crop", "Forest Pathway"),
        ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=900&auto=format&fit=crop", "Coastal View"),
        ("https://images.unsplash.com/photo-1519681393784-d120267933ba?w=900&auto=format&fit=crop", "Starry Night"),
        ("https://images.unsplash.com/photo-1426604966848-d7adac902bff?w=900&auto=format&fit=crop", "Mountain Stream"),
        ("https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=900&auto=format&fit=crop", "Serene Lake"),
        ("https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=900&auto=format&fit=crop", "Misty Woods"),
        ("https://images.unsplash.com/photo-1511497584788-876761197069?w=900&auto=format&fit=crop", "Deep Forest")
    ],
    "AI/테크": [
        ("https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=900&auto=format&fit=crop", "AI Technology"),
        ("https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=900&auto=format&fit=crop", "Digital Network"),
        ("https://images.unsplash.com/photo-1535378917042-10a22c95931a?w=900&auto=format&fit=crop", "Cyber Matrix"),
        ("https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=900&auto=format&fit=crop", "Global Tech"),
        ("https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=900&auto=format&fit=crop", "Cyber Security"),
        ("https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=900&auto=format&fit=crop", "Innovation Lab"),
        ("https://images.unsplash.com/photo-1518770660439-4636190af475?w=900&auto=format&fit=crop", "Hardware Circuit"),
        ("https://images.unsplash.com/photo-1531482615713-2afd69097998?w=900&auto=format&fit=crop", "Tech Workspace"),
        ("https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=900&auto=format&fit=crop", "Laptop Coding"),
        ("https://images.unsplash.com/photo-1509228468518-180dd4864904?w=900&auto=format&fit=crop", "Quantum Computing")
    ],
    "건강/복지": [
        ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=900&auto=format&fit=crop", "Wellness Center"),
        ("https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=900&auto=format&fit=crop", "Medical Care"),
        ("https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?w=900&auto=format&fit=crop", "Senior Health"),
        ("https://images.unsplash.com/photo-1516549655169-df83a0774514?w=900&auto=format&fit=crop", "Hospital Ward"),
        ("https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=900&auto=format&fit=crop", "Healthcare Team"),
        ("https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?w=900&auto=format&fit=crop", "Pharmacy Lab"),
        ("https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=900&auto=format&fit=crop", "Healthy Living"),
        ("https://images.unsplash.com/photo-1544717305-2782549b5136?w=900&auto=format&fit=crop", "Elderly Care"),
        ("https://images.unsplash.com/photo-1512290900672-8a712b682278?w=900&auto=format&fit=crop", "Active Senior"),
        ("https://images.unsplash.com/photo-1511174511562-5f7f18b874f8?w=900&auto=format&fit=crop", "Mental Support")
    ],
    "생활정보": [
        ("https://images.unsplash.com/photo-1484807352052-23338990c6c8?w=900&auto=format&fit=crop", "Modern Interior"),
        ("https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=900&auto=format&fit=crop", "Real Estate"),
        ("https://images.unsplash.com/photo-1554469384-e58fac16e23a?w=900&auto=format&fit=crop", "Urban Living"),
        ("https://images.unsplash.com/photo-1513694203232-719a280e022f?w=900&auto=format&fit=crop", "Home Design"),
        ("https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=900&auto=format&fit=crop", "Apartment View"),
        ("https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=900&auto=format&fit=crop", "House Exterior"),
        ("https://images.unsplash.com/photo-1582268611958-ebfd161ef9cf?w=900&auto=format&fit=crop", "Consumer Life"),
        ("https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=900&auto=format&fit=crop", "Living Space"),
        ("https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=900&auto=format&fit=crop", "Suburban Home"),
        ("https://images.unsplash.com/photo-1507089947368-19c1da9775ae?w=900&auto=format&fit=crop", "Daily Routine")
    ],
    "연예계뉴스": [
        ("https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=900&auto=format&fit=crop", "Concert Stage"),
        ("https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=900&auto=format&fit=crop", "Music Festival"),
        ("https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=900&auto=format&fit=crop", "Acoustic Stage"),
        ("https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=900&auto=format&fit=crop", "DJ & Lights"),
        ("https://images.unsplash.com/photo-1501386761578-eac5c94b800a?w=900&auto=format&fit=crop", "Live Performance"),
        ("https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=900&auto=format&fit=crop", "Concert Crowd"),
        ("https://images.unsplash.com/photo-1469488865564-c2de10f69f96?w=900&auto=format&fit=crop", "Showbiz Lighting"),
        ("https://images.unsplash.com/photo-1524368535928-5b5e009c74b3?w=900&auto=format&fit=crop", "Band Jamming"),
        ("https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=900&auto=format&fit=crop", "Red Carpet"),
        ("https://images.unsplash.com/photo-1519671482749-fd09be7ccebf?w=900&auto=format&fit=crop", "Festive Vibe")
    ],
    "스포츠": [
        ("https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=900&auto=format&fit=crop", "Stadium Track"),
        ("https://images.unsplash.com/photo-1546519638-68e109498ffc?w=900&auto=format&fit=crop", "Basketball Court"),
        ("https://images.unsplash.com/photo-1508344928928-7165b67de128?w=900&auto=format&fit=crop", "Baseball Diamond"),
        ("https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=900&auto=format&fit=crop", "Soccer Pitch"),
        ("https://images.unsplash.com/photo-1517649763962-0c623266cf10?w=900&auto=format&fit=crop", "Athletic Track"),
        ("https://images.unsplash.com/photo-1569517282132-25d22f4573e6?w=900&auto=format&fit=crop", "Sports Arena"),
        ("https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=900&auto=format&fit=crop", "Football Match"),
        ("https://images.unsplash.com/photo-1519766304817-4f37bda74a29?w=900&auto=format&fit=crop", "Team Training"),
        ("https://images.unsplash.com/photo-1530549387789-4c1017266635?w=900&auto=format&fit=crop", "Swimming Pool"),
        ("https://images.unsplash.com/photo-1518619897877-80efef847e02?w=900&auto=format&fit=crop", "Indoor Gym")
    ],
    "지역창": [
        ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=900&auto=format&fit=crop", "Sokcho Beach"),
        ("https://images.unsplash.com/photo-1533105079780-92b9be482077?w=900&auto=format&fit=crop", "Coastal Horizon"),
        ("https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=900&auto=format&fit=crop", "Mountain Ridge"),
        ("https://images.unsplash.com/photo-1519681393784-d120267933ba?w=900&auto=format&fit=crop", "Sunrise Peak"),
        ("https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=900&auto=format&fit=crop", "Nature Vista"),
        ("https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=900&auto=format&fit=crop", "Calm Waters"),
        ("https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=900&auto=format&fit=crop", "Pine Trail"),
        ("https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=900&auto=format&fit=crop", "Forest Morning"),
        ("https://images.unsplash.com/photo-1426604966848-d7adac902bff?w=900&auto=format&fit=crop", "River Valley"),
        ("https://images.unsplash.com/photo-1511497584788-876761197069?w=900&auto=format&fit=crop", "Deep Woods")
    ]
}

def clean_article_title(raw_title):
    t = raw_title.replace('**', '').replace('*', '').strip()
    t = re.sub(r'^\[[^\]]+\]\s*', '', t).strip()
    return t

def fetch_bulletproof_image(category_name, article_title=""):
    pool = SMART_IMAGE_POOLS.get(category_name, SMART_IMAGE_POOLS["세상이야기"])
    combined_str = (article_title + category_name).lower()
    selected_tuple = random.choice(pool)
    
    if "농구" in combined_str or "국가대표" in combined_str or "8강" in combined_str:
        if category_name == "스포츠":
            selected_tuple = SMART_IMAGE_POOLS["스포츠"][1]
    elif "야구" in combined_str or "홈런" in combined_str:
        if category_name == "스포츠":
            selected_tuple = SMART_IMAGE_POOLS["스포츠"][2]
    elif "축구" in combined_str or "골" in combined_str:
        if category_name == "스포츠":
            selected_tuple = SMART_IMAGE_POOLS["스포츠"][3]
    else:
        idx = abs(hash(article_title)) % len(pool)
        selected_tuple = pool[idx]

    return selected_tuple[0], selected_tuple[1]

def get_safe_image_url(raw_url, category_name, article_title=""):
    if not raw_url or not raw_url.strip() or not (raw_url.startswith("http") or raw_url.startswith("/")):
        fallback_pool = SMART_IMAGE_POOLS.get(category_name, SMART_IMAGE_POOLS["세상이야기"])
        idx = abs(hash(article_title)) % len(fallback_pool)
        return fallback_pool[idx][0]
    if "unsplash.com/search" in raw_url or "api.unsplash.com" in raw_url:
        fallback_pool = SMART_IMAGE_POOLS.get(category_name, SMART_IMAGE_POOLS["세상이야기"])
        idx = abs(hash(article_title)) % len(fallback_pool)
        return fallback_pool[idx][0]
    return raw_url.strip()

def get_safe_image_author(raw_author, category_name):
    if not raw_author or not raw_author.strip():
        fallback_pool = SMART_IMAGE_POOLS.get(category_name, SMART_IMAGE_POOLS["세상이야기"])
        return fallback_pool[0][1]
    return raw_author.strip()

def purify_content_images(content_html, category_name, article_title=""):
    if not content_html:
        return ""
    fallback_pool = SMART_IMAGE_POOLS.get(category_name, SMART_IMAGE_POOLS["세상이야기"])
    
    def replace_img_tag(match):
        full_tag = match.group(0)
        img_src_match = re.search(r'src=["\']([^"\']+)["\']', full_tag, re.IGNORECASE)
        if not img_src_match:
            return full_tag
        current_src = img_src_match.group(1)
        
        if not current_src or not (current_src.startswith("http") or current_src.startswith("/")) or "unsplash.com/search" in current_src or "api.unsplash.com" in current_src:
            idx = abs(hash(article_title + current_src)) % len(fallback_pool)
            safe_url = fallback_pool[idx][0]
            return full_tag.replace(current_src, safe_url)
        return full_tag

    purified_html = re.sub(r'<img\s+[^>]*>', replace_img_tag, content_html, flags=re.IGNORECASE)
    return purified_html

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

def clean_and_format_content(text, category_name="종합", title="", use_subtitles=True):
    text = re.sub(r'^\s*\[?(기사\s*)?제목\]?\s*[:：]\s*.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^\s*\[?본문\]?\s*[:：]?\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    text = text.replace('**', '').replace('__', '')
    clean_title_str = clean_article_title(title)

    lines_raw = text.split('\n')
    processed_lines = []

    for line in lines_raw:
        p_str = line.strip()
        if not p_str:
            continue
        
        p_text_pure = re.sub(r'^[#|\s]+', '', p_str).replace('제목:', '').strip()
        if clean_title_str and p_text_pure == clean_title_str:
            continue

        if p_str.startswith('<div class="article-img-box"') or p_str.startswith('<p') or p_str.startswith('<div') or p_str.startswith('<figure') or p_str.startswith('<img'):
            processed_lines.append(p_str)
        elif use_subtitles and (p_str.startswith('###') or (len(p_str) < 42 and not p_str.endswith(('.', '?', '!')) and not p_str.startswith('<'))):
            title_text = p_str.replace('###', '').strip()
            title_text = re.sub(r'^\[(기|승|전|결)(:\s*[^\]]+)?\]\s*', '', title_text).strip()
            title_text = re.sub(r'^(기|승|전|결):\s*', '', title_text).strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 32px; margin-bottom: 14px; font-size: 1.15em; font-weight: 800; letter-spacing: -0.5px;">{title_text}</h3>')
        else:
            processed_lines.append(f'<p style="margin-bottom: 24px; text-align: left !important; word-break: normal; line-height: 1.8; color: #111111; font-size: 1.02em; letter-spacing: -0.3px;">{p_str}</p>')

    final_html = "".join(processed_lines)
    final_html = purify_content_images(final_html, category_name, clean_title_str)

    if '#시사투데이' not in final_html and '#이슈분석' not in final_html and 'word-spacing: 5px;' not in final_html:
        clean_tags_str = generate_smart_tags(text, title)
        tag_html = f"<div style='margin-top: 35px; padding-top: 15px; border-top: 1px solid #eaecee; color: #2980b9; font-weight: bold; font-size: 0.9em; word-spacing: 5px;'>{clean_tags_str}</div>"
        final_html += tag_html

    return final_html

def save_article_to_db(category, title, content, image_url, image_author):
    kst = timezone(timedelta(hours=9))
    current_time_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    clean_t = clean_article_title(title)
    
    if supabase:
        res = supabase.table("articles").insert({
            "category": category,
            "title": clean_t,
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
            (category, clean_t, content, image_url, image_author, current_time_str)
        )
        conn.commit()
        conn.close()
    
    ping_indexnow("/")

def get_all_articles(category=None):
    if supabase:
        query = supabase.table("articles").select("*").order("id", desc=True)
        if category and category != "전체":
            query = query.eq("category", category)
        response = query.execute()
        rows = response.data
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        if category and category != "전체":
            cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE category = ? ORDER BY id DESC", (category,))
        else:
            cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles ORDER BY id DESC")
        raw_rows = cursor.fetchall()
        conn.close()
        rows = [{
            "id": r[0], "category": r[1], "title": r[2], "content": r[3], 
            "image_url": r[4], "image_author": r[5], "created_at": r[6]
        } for r in raw_rows]

    processed_rows = []
    for r in rows:
        cat = r.get("category") or "세상이야기"
        t = clean_article_title(r.get("title") or "")
        safe_img = get_safe_image_url(r.get("image_url"), cat, t)
        safe_auth = get_safe_image_author(r.get("image_author"), cat)
        safe_content = purify_content_images(r.get("content") or "", cat, t)
        processed_rows.append({
            "id": r["id"],
            "category": cat,
            "title": t,
            "content": safe_content,
            "image_url": safe_img,
            "image_author": safe_auth,
            "created_at": r["created_at"]
        })
    return processed_rows

def get_article_by_id(article_id):
    if supabase:
        response = supabase.table("articles").select("*").eq("id", article_id).execute()
        if response.data:
            art = response.data[0]
            cat = art.get("category") or "세상이야기"
            t = clean_article_title(art.get("title") or "")
            art["title"] = t
            art["image_url"] = get_safe_image_url(art.get("image_url"), cat, t)
            art["image_author"] = get_safe_image_author(art.get("image_author"), cat)
            art["content"] = purify_content_images(art.get("content") or "", cat, t)
            return art
        return None
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE id = ?", (article_id,))
        r = cursor.fetchone()
        conn.close()
        if not r:
            return None
        cat = r[1] or "세상이야기"
        t = clean_article_title(r[2] or "")
        return {
            "id": r[0], "category": cat, "title": t, 
            "content": purify_content_images(r[3], cat, t), 
            "image_url": get_safe_image_url(r[4], cat, t), 
            "image_author": get_safe_image_author(r[5], cat), 
            "created_at": r[6]
        }

def update_article_in_db(article_id, category, title, content, image_url, image_author):
    clean_t = clean_article_title(title)
    formatted_content = clean_and_format_content(content, category, clean_t, use_subtitles=True)
    clean_url = image_url.strip() if image_url and image_url.strip() else ""
    clean_author = image_author.strip() if image_author and image_author.strip() else ""
    
    if supabase:
        update_data = {
            "category": category,
            "title": clean_t,
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
            (category, clean_t, formatted_content, clean_url, clean_author, article_id)
        )
        conn.commit()
        conn.close()
    
    ping_indexnow(f"/?view={article_id}")

def delete_article_from_db(article_id):
    if supabase:
        supabase.table("articles").delete().eq("id", article_id).execute()
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()

def generate_ai_article(category_name, use_subtitles=True):
    news_title, news_desc, pub_date = get_latest_realtime_news(category_name)
    ref_fact_context = f"\n[실시간 핫이슈 헤드라인]: {news_title}\n[핵심 팩트 요약]: {news_desc}\n[보도 일시]: {pub_date}\n" if news_title else ""
    
    if category_name == "정치/시사":
        editorial_prompt = f"""
당신은 팩트를 최우선으로 다루는 정론지의 수석 시사보도 전문 기자입니다.
오늘은 **2026년 9월 15일**입니다.
[취재 분야]: 정치/시사 (국가 정책, 행정, 제도, 정국 주요 현안 중심)
{ref_fact_context}
지침:
1. 최근 발생한 가장 뜨겁고 묵직한 정치/시사 핫이슈를 정밀하게 파고드는 심층보도 형태로 기사를 작성하세요.
2. 첫 번째 줄: 검색 유입을 극대화하는 강력하고 객관적인 보도체 기사 제목 한 줄만 작성. (절대 제목 앞에 [심층분석], [단독] 등의 대괄호 말머리나 수식어를 붙이지 말 것)
3. 두 번째 줄: 빈 줄.
4. 세 번째 줄부터: 4개 이상의 상세 문단으로 구성하고, 정국에 미치는 영향과 향후 파장까지 객관적이고 깊이 있게 서술하세요.
"""
    elif category_name == "세상이야기":
        editorial_prompt = f"""
당신은 따뜻한 시선으로 세상을 관조하는 휴먼 다큐멘터리 전문 칼럼니스트입니다.
오늘은 **2026년 9월 15일**입니다.
[취재 분야]: 세상이야기 (이웃들의 진솔한 삶, 소외된 이웃들의 이야기, 인생 철학과 감동이 담긴 미담 중심)
{ref_fact_context}
지침:
1. 각박한 세상 속에서 우리 주변 이웃들이 살아가는 진솔한 모습과 따뜻한 감동, 깊은 인생 철학이 담긴 휴먼 스토리 형식으로 기사를 작성하세요.
2. 첫 번째 줄: 독자의 마음을 울리는 감성적이고 품격 있는 제목 한 줄만 작성. (대괄호 수식어 금지)
3. 두 번째 줄: 빈 줄.
4. 세 번째 줄부터: 4개 이상의 상세 문단으로 구성하고, 가슴 먹먹한 감동과 삶의 교훈을 전달할 수 있도록 서정적이고 깊이 있게 서술하세요.
"""
    else:
        editorial_prompt = f"""
당신은 팩트를 최우선으로 다루는 정론지의 수석 심층보도 전문 기자입니다.
오늘은 **2026년 9월 15일**입니다.
[취재 분야]: {category_name}
{ref_fact_context}
지침:
1. 최근 발생한 가장 뜨거운 이슈를 정밀하게 파고드는 심층보도 형태로 기사를 작성하세요.
2. 첫 번째 줄: 검색 유입을 극대화하는 강력하고 객관적인 보도체 기사 제목 한 줄만 작성. (대괄호 수식어 금지)
3. 두 번째 줄: 빈 줄.
4. 세 번째 줄부터: 4개 이상의 상세 문단으로 구성하고, 현장감 있는 팩트와 배경, 향후 파장까지 심도 있게 서술하세요.
"""

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=editorial_prompt)
        raw_content = response.text.strip()
    except Exception as e:
        raw_content = f"기사 생성 오류: {e}"

    split_lines = raw_content.split("\n", 1)
    if len(split_lines) > 1 and len(split_lines[0].strip()) <= 60:
        art_title = clean_article_title(split_lines[0])
        body_content = split_lines[1].strip()
    else:
        art_title = f"{category_name} 긴급 현장 심층보도"
        body_content = raw_content

    img_url, author_name = fetch_bulletproof_image(category_name, art_title)
    formatted_content = clean_and_format_content(body_content, category_name, art_title, use_subtitles=use_subtitles)
    save_article_to_db(category_name, art_title, formatted_content, img_url, author_name)

# 🛑 [자동 발행 스케줄러 완전 중단]: 백그라운드 자동 기사 발행 로직을 제거했습니다.

@app.post("/admin/create-auto")
def create_auto(
    category: str = Form(...), 
    use_subtitles: str = Form(None),
    admin_auth: str = Cookie(None)
):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    sub_flag = True if use_subtitles == "yes" else False
    generate_ai_article(category, use_subtitles=sub_flag)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.post("/admin/create-manual")
def create_manual(
    category: str = Form(...), 
    title: str = Form(...), 
    content: str = Form(...), 
    use_unsplash: str = Form(None),
    use_subtitles: str = Form(None),
    custom_image_url: str = Form(None),
    custom_image_author: str = Form(None),
    admin_auth: str = Cookie(None)
):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = clean_article_title(title)
    
    if not use_unsplash and custom_image_url and custom_image_url.strip():
        img_url = custom_image_url.strip()
        author_name = custom_image_author.strip() if custom_image_author else ""
    else:
        img_url, author_name = fetch_bulletproof_image(category, clean_title)
    
    sub_flag = True if use_subtitles == "yes" else False
    formatted_content = clean_and_format_content(content, category, clean_title, use_subtitles=sub_flag)
    save_article_to_db(category, clean_title, formatted_content, img_url, author_name)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.post("/admin/create-ai-expand")
def create_ai_expand(
    category: str = Form(...), 
    title: str = Form(...), 
    prompt: str = Form(...), 
    use_unsplash: str = Form(None),
    use_subtitles: str = Form(None),
    custom_image_url: str = Form(None),
    custom_image_author: str = Form(None),
    admin_auth: str = Cookie(None)
):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    
    clean_title = clean_article_title(title)
    if category == "정치/시사":
        system_directive = "당신은 정통 시사보도 전문 기자로서, 국가 정책과 정국 현안을 객관적이고 무겁게 다루는 표준 보도체(~다)로 기사를 작성하세요."
    elif category == "세상이야기":
        system_directive = "당신은 휴먼 칼럼니스트로서, 이웃들의 따뜻한 삶과 진솔한 인생 이야기를 서정적이고 감동적인 문체로 작성하세요."
    else:
        system_directive = "전문 수석 언론사 기자로서 완성도 높은 정식 뉴스 기사 본문을 표준 보도체(~다)로 작성하세요."

    full_query = f"{system_directive}\n\n[기사 제목]: {clean_title}\n[취재 메모]: {prompt}"

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=full_query)
        final_content = response.text.strip()
    except Exception as e:
        final_content = f"오류: {e}"

    if not use_unsplash and custom_image_url and custom_image_url.strip():
        img_url = custom_image_url.strip()
        author_name = custom_image_author.strip() if custom_image_author else ""
    else:
        img_url, author_name = fetch_bulletproof_image(category, clean_title)

    sub_flag = True if use_subtitles == "yes" else False
    final_content = clean_and_format_content(final_content, category, clean_title, use_subtitles=sub_flag)
    save_article_to_db(category, clean_title, final_content, img_url, author_name)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.post("/admin/upload-image")
async def upload_image(file: UploadFile = File(...), admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return {"error": "Unauthorized"}
    try:
        file_ext = file.filename.split(".")[-1]
        unique_filename = f"img_{int(time.time())}_{random.randint(1000,9999)}.{file_ext}"
        contents = await file.read()
        
        if supabase:
            supabase.storage.from_("images").upload(unique_filename, contents, file_options={"content-type": file.content_type})
            public_url_res = supabase.storage.from_("images").get_public_url(unique_filename)
            return {"url": public_url_res}
        else:
            file_path = os.path.join("static", unique_filename)
            with open(file_path, "wb") as f:
                f.write(contents)
            return {"url": f"/static/{unique_filename}"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/siyatodaychangkey2026.txt", response_class=PlainResponse)
def indexnow_key_file():
    return PlainResponse("siyatodaychangkey2026", media_type="text/plain")

@app.get("/robots.txt", response_class=PlainResponse)
def robots_txt():
    return PlainResponse(f"User-agent: *\nAllow: /\nSitemap: {BASE_SITE_URL}/sitemap.xml", media_type="text/plain")

@app.get("/sitemap.xml", response_class=PlainResponse)
def sitemap():
    articles = get_all_articles()
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml_content += f"  <url><loc>{BASE_SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n"
    for art in articles:
        xml_content += f"  <url><loc>{BASE_SITE_URL}/?view={art['id']}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n"
    xml_content += '</urlset>'
    return PlainResponse(content=xml_content, media_type="application/xml")

@app.get("/rss", response_class=PlainResponse)
def rss_feed():
    articles = get_all_articles()
    rss_content = '<?xml version="1.0" encoding="UTF-8" ?>\n<rss version="2.0">\n<channel>\n  <title>시사투데이 창</title>\n  <link>' + BASE_SITE_URL + '/</link>\n  <description>프리미엄 시사투데이 창</description>\n'
    for art in articles:
        rss_content += f"  <item>\n    <title>{art['title'].replace('&', '&amp;')}</title>\n    <link>{BASE_SITE_URL}/?view={art['id']}</link>\n    <guid>{BASE_SITE_URL}/?view={art['id']}</guid>\n    <pubDate>{art['created_at']}</pubDate>\n  </item>\n"
    rss_content += '</channel>\n</rss>'
    return PlainResponse(content=rss_content, media_type="application/rss+xml")

@app.get("/ads.txt", response_class=PlainResponse)
def ads_txt():
    return PlainResponse("google.com, pub-0517985818592419, DIRECT, f08c47fec0942fa0", media_type="text/plain")

@app.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = None, view: int = None, q: str = None):
    subscribe_card_html = """
    <div class="author-subscribe-card">
        <div class="author-name">시사투데이 창 <span class="author-arrow">›</span></div>
        <button type="button" class="btn-subscribe" onclick="subscribeNotice();">
            <svg class="sub-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7.5" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
            구독하기
        </button>
    </div>
    """
    subscribe_js = """
    <script>
    function subscribeNotice() {
        alert("⭐ [구독 및 바로가기 안내]\\n\\n'시사투데이 창'을 구독해 주셔서 감사합니다!\\n\\n아이폰: 하단 공유(📤) → [홈 화면에 추가]\\n갤럭시: 우측 상단 메뉴(⋮) → [현재 페이지 추가] → [홈 화면]");
    }
    </script>
    """

    if view:
        art = get_article_by_id(view)
        if not art:
            return RedirectResponse(url="/", status_code=303)
        fallback_pool = SMART_IMAGE_POOLS.get(art.get("category"), SMART_IMAGE_POOLS["세상이야기"])
        fallback_url = fallback_pool[0][0]
        raw_img_url = art.get("image_url") or ""
        img_tag_src = raw_img_url if raw_img_url.startswith("http") or raw_img_url.startswith("/") else fallback_url
        img_block = f'<img src="{img_tag_src}" class="article-img" onerror="this.onerror=null; this.src=\'{fallback_url}\';"><div class="img-source">📷 Photo by {art.get("image_author", "")}</div>' if raw_img_url else ""
        return f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{art['title']} - 시사투데이 창</title>
            <meta name="description" content="{art['title']} - 프리미엄 시사투데이 창 실시간 뉴스 리포트">
            <link rel="canonical" href="{BASE_SITE_URL}/?view={art['id']}">
            {NAVER_ANALYTICS_SCRIPT}{GOOGLE_ANALYTICS_SCRIPT}
            <style>
                body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 0 auto; padding: 15px; background: #f8f9fa; color: #111; line-height: 1.8; }}
                .top-bar {{ margin-bottom: 20px; }}
                .back-btn {{ padding: 6px 14px; background: #1b4f72; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 0.85em; }}
                .article-container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }}
                h1 {{ font-size: 1.3em; color: #1a252f; margin-top: 10px; margin-bottom: 15px; }}
                .date {{ font-size: 0.9em; color: #7f8c8d; border-bottom: 1px solid #eaecee; padding-bottom: 15px; margin-bottom: 25px; }}
                .article-img {{ width: 100%; max-height: 480px; object-fit: cover; border-radius: 8px; margin-bottom: 8px; }}
                .img-source {{ font-size: 0.85em; color: #95a5a6; margin-bottom: 30px; font-style: italic; }}
                .content {{ font-size: 1.02em; color: #111; }}
                .content p {{ margin-bottom: 24px; }}
                
                .author-subscribe-card {{ display: flex !important; justify-content: space-between !important; align-items: center !important; background: white !important; border: 1px solid #e5e8ec !important; border-radius: 10px !important; padding: 14px 20px !important; margin-top: 25px !important; box-shadow: 0 2px 6px rgba(0,0,0,0.02) !important; box-sizing: border-box !important; }}
                .author-name {{ font-size: 15px !important; font-weight: bold !important; color: #2c3e50 !important; display: flex !important; align-items: center !important; gap: 5px !important; }}
                .author-arrow {{ color: #aaa !important; font-size: 14px !important; font-weight: normal !important; }}
                .btn-subscribe {{ display: inline-flex !important; align-items: center !important; gap: 6px !important; background: #ffffff !important; color: #333333 !important; border: 1px solid #cfd4d9 !important; border-radius: 4px !important; padding: 7px 14px !important; font-size: 13px !important; font-weight: 500 !important; cursor: pointer !important; white-space: nowrap !important; }}
                .btn-subscribe:hover {{ background: #f8f9fa !important; border-color: #aeb6bf !important; color: #111 !important; }}
                .sub-icon {{ width: 14px !important; height: 14px !important; color: #555 !important; }}
            </style>
        </head>
        <body>
            <div class="top-bar"><a href="/" class="back-btn">← 메인 뉴스로 돌아가기</a></div>
            <div class="article-container">
                <div style="border-bottom: 3px solid #1b4f72; padding-bottom: 12px; margin-bottom: 20px;">
                    <a href="/" style="text-decoration: none; display: inline-block;">
                        <div style="font-family: 'Gowun Batang', serif; font-size: 1.5em; font-weight: 700; color: #1a252f; display: flex; align-items: center; gap: 8px;">
                            시사투데이&nbsp;<span style="display: inline-block; background: #fff; color: #111; border: 2.5px solid #111; padding: 2px 12px; border-radius: 6px; transform: rotate(5deg); box-shadow: 2px 2px 4px rgba(0,0,0,0.12);">창</span>
                        </div>
                    </a>
                </div>
                <h1>{art['title']}</h1>
                <div class="date">발행일시: {art['created_at']}</div>
                {img_block}
                <div class="content">{art['content']}</div>
            </div>
            {subscribe_card_html}
            {subscribe_js}
        </body>
        </html>
        """

    articles = get_all_articles(category)
    if q and q.strip():
        kw = q.strip().lower()
        articles = [a for a in articles if kw in a['title'].lower() or kw in a['content'].lower()]

    categories = ["전체", "정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]

    featured_articles = articles[:2] if articles else []
    featured_html = ""
    for art in featured_articles:
        cat_name = art['category'] if art['category'] else '종합'
        fallback_pool = SMART_IMAGE_POOLS.get(cat_name, SMART_IMAGE_POOLS["세상이야기"])
        fallback_fallback = fallback_pool[0][0]
        raw_img_url = art.get('image_url') or ""
        img_url = raw_img_url if raw_img_url.startswith("http") or raw_img_url.startswith("/") else fallback_fallback
        clean_t = clean_article_title(art['title'])
        featured_html += f"""
        <div class="featured-card">
            <div class="featured-img-wrap">
                <a href="/?view={art['id']}"><img src="{img_url}" class="featured-img" onerror="this.onerror=null; this.src='{fallback_fallback}';"></a>
            </div>
            <div class="featured-body">
                <span class="badge">{cat_name}</span>
                <h3 class="featured-title"><a href="/?view={art['id']}">{clean_t}</a></h3>
                <div class="card-date">발행 | {art['created_at']}</div>
            </div>
        </div>
        """

    list_html = ""
    if category and category != "전체":
        remaining_articles = articles[2:] if len(articles) > 2 else []
        if remaining_articles:
            list_html += f'<div class="news-section-box"><div class="section-header">📌 {category} 이전 리포트</div>'
            for art in remaining_articles:
                clean_t = clean_article_title(art['title'])
                list_html += f"""
                <div class="news-list-item">
                    <a href="/?view={art['id']}" class="list-title">{clean_t}</a>
                    <span class="list-date">{art['created_at'].split()[0]}</span>
                </div>
                """
            list_html += '</div>'
    else:
        display_cats = ["정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]
        for cat in display_cats:
            cat_arts = [a for a in articles if a.get('category'] == cat][:5]
            if cat_arts:
                list_html += f'<div class="news-section-box"><div class="section-header">📂 {cat} 최신 소식</div>'
                for art in cat_arts:
                    clean_t = clean_article_title(art['title'])
                    list_html += f"""
                    <div class="news-list-item">
                        <a href="/?view={art['id']}" class="list-title">{clean_t}</a>
                        <span class="list-date">{art['created_at'].split()[0]}</span>
                    </div>
                    """
                list_html += '</div>'

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>시사투데이 창 - 프리미엄 미디어</title>
        <meta name="description" content="시사투데이 창 - 정치, 경제, 세상이야기, AI테크, 건강복지, 생활정보 등 프리미엄 실시간 뉴스 미디어">
        <link rel="canonical" href="{BASE_SITE_URL}/">
        <link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&display=swap" rel="stylesheet">
        {NAVER_ANALYTICS_SCRIPT}{GOOGLE_ANALYTICS_SCRIPT}
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 900px; margin: 0 auto; padding: 10px; background: #f0f3f4; color: #333; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 4px solid #1b4f72; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.05); }}
            .logo-title {{ font-family: 'Gowun Batang', serif; font-size: 1.6em; font-weight: 700; color: #1a252f; display: flex; align-items: center; gap: 8px; text-decoration: none; }}
            .logo-chang {{ display: inline-block; background: #fff; color: #111; border: 2.5px solid #111; padding: 4px 16px; border-radius: 6px; transform: rotate(5deg); box-shadow: 3px 3px 6px rgba(0,0,0,0.12); }}
            .nav-tabs {{ display: flex; gap: 5px; margin: 15px 0; flex-wrap: wrap; background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }}
            .tab-item {{ flex: 1; min-width: 75px; text-align: center; padding: 6px 4px; background: #ecf0f1; color: #555; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 12px; white-space: nowrap; }}
            .tab-item:hover, .tab-item.active {{ background: #1b4f72; color: white; }}
            
            .featured-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; margin-bottom: 20px; }}
            .featured-card {{ background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 3px 10px rgba(0,0,0,0.04); display: flex; flex-direction: column; }}
            .featured-img-wrap {{ width: 100%; height: 180px; overflow: hidden; background: #ddd; }}
            .featured-img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }}
            .featured-card:hover .featured-img {{ transform: scale(1.03); }}
            .featured-body {{ padding: 15px; display: flex; flex-direction: column; flex-grow: 1; }}
            .badge {{ display: inline-block; padding: 3px 8px; background: #ebf5fb; color: #2980b9; border-radius: 4px; font-size: 0.75em; font-weight: bold; margin-bottom: 8px; width: fit-content; }}
            .featured-title {{ font-size: 1.1em; color: #2c3e50; margin: 0 0 10px 0; line-height: 1.4; font-weight: 700; }}
            .featured-title a {{ color: inherit; text-decoration: none; }}
            .featured-title a:hover {{ color: #2980b9; }}
            .card-date {{ font-size: 0.75em; color: #95a5a6; margin-top: auto; padding-top: 10px; border-top: 1px solid #f1f2f6; }}

            .news-section-box {{ background: white; border-radius: 10px; padding: 15px 20px; margin-bottom: 15px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); }}
            .section-header {{ font-size: 1.05em; font-weight: bold; color: #1b4f72; border-bottom: 2px solid #ebf5fb; padding-bottom: 8px; margin-bottom: 10px; }}
            .news-list-item {{ display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f8f9fa; }}
            .news-list-item:last-child {{ border-bottom: none; }}
            .list-title {{ flex-grow: 1; font-size: 0.96em; color: #2c3e50; text-decoration: none; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 15px; }}
            .list-title:hover {{ color: #2980b9; text-decoration: underline; }}
            .list-date {{ font-size: 0.78em; color: #95a5a6; white-space: nowrap; }}

            .footer-search-box {{ background: white; padding: 18px 20px; border-radius: 10px; margin-top: 20px; text-align: center; box-shadow: 0 3px 10px rgba(0,0,0,0.04); }}
            .search-form {{ display: flex; gap: 8px; justify-content: center; max-width: 400px; margin: 0 auto; }}
            .search-input {{ padding: 10px 15px; border: 1px solid #ccc; border-radius: 20px; flex-grow: 1; outline: none; }}
            .search-btn {{ padding: 10px 20px; background: #1b4f72; color: white; border: none; border-radius: 20px; font-weight: bold; cursor: pointer; }}
            
            .author-subscribe-card {{ display: flex; justify-content: space-between; align-items: center; background: white; border: 1px solid #e5e8ec; border-radius: 10px; padding: 14px 20px; margin-top: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); }}
            .author-name {{ font-size: 15px; font-weight: bold; color: #2c3e50; display: flex; align-items: center; gap: 5px; }}
            .author-arrow {{ color: #aaa; font-size: 14px; font-weight: normal; }}
            .btn-subscribe {{ display: inline-flex; align-items: center; gap: 6px; background: #ffffff; color: #333333; border: 1px solid #cfd4d9; border-radius: 4px; padding: 7px 14px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s ease; }}
            .btn-subscribe:hover {{ background: #f8f9fa; border-color: #aeb6bf; color: #111; }}
            .sub-icon {{ width: 14px; height: 14px; color: #555; }}
        </style>
    </head>
    <body>
        <div class="header-flex">
            <a href="/" style="text-decoration: none;">
                <div class="logo-title">시사투데이&nbsp;<span class="logo-chang">창</span></div>
            </a>
        </div>
        <div class="nav-tabs">
    """
    for cat in categories:
        active = "active" if (not category and cat == "전체") or (category == cat) else ""
        param = "" if cat == "전체" else f"?category={cat}"
        html += f'<a href="/{param}" class="tab-item {active}">{cat}</a>'
    html += "</div>"

    if not articles:
        html += "<p style='text-align:center; color:#777; margin-top:80px;'>등록된 기사가 없습니다.</p>"
    else:
        if featured_html:
            html += f'<div class="featured-grid">{featured_html}</div>'
        if list_html:
            html += list_html

    html += f"""
        <div class="footer-search-box">
            <form action="/" method="get" class="search-form">
                {"<input type='hidden' name='category' value='" + category + "'>" if category else ""}
                <input type="text" name="q" class="search-input" placeholder="🔍 기사 제목 또는 내용 검색..." value="{q if q else ''}">
                <button type="submit" class="search-btn">검색</button>
            </form>
        </div>
        {subscribe_card_html}
        {subscribe_js}
    </body>
    </html>
    """
    return html

@app.get("/admin", response_class=HTMLResponse)
def admin_login_page(request: Request, error: str = None):
    err_msg = "<p style='color: #e74c3c; margin-bottom: 15px;'>비밀번호가 틀렸습니다!</p>" if error else ""
    return f"""
    <!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>관리자 로그인</title>
    <style>body {{ font-family: 'Malgun Gothic', sans-serif; background: #f0f3f4; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .login-box {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); width: 320px; text-align: center; }}
    input[type="password"] {{ width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; text-align: center; }}
    button {{ width: 100%; padding: 12px; background: #1b4f72; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; }}
    </style></head>
    <body><div class="login-box"><h2>🔐 관리자 인증</h2>{err_msg}
    <form action="/admin/login" method="post"><input type="password" name="password" placeholder="비밀번호" required autofocus><button type="submit">로그인</button></form>
    <a href="/" style="display:block; margin-top:15px; color:#7f8c8d; text-decoration:none; font-size:0.9em;">← 메인으로</a></div></body></html>
    """

@app.post("/admin/login")
def admin_login(response: Response, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        resp = RedirectResponse(url="/admin/studio", status_code=303)
        resp.set_cookie(key="admin_auth", value="authenticated", max_age=86400)
        return resp
    return RedirectResponse(url="/admin?error=true", status_code=303)

@app.get("/admin/studio", response_class=HTMLResponse)
def admin_studio(request: Request, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)

    rows = get_all_articles()
    articles_list_html = ""
    for r in rows:
        clean_t = clean_article_title(r['title'])
        articles_list_html += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 12px 10px; font-size: 0.9em; color: #555;">{r['category']}</td>
            <td style="padding: 12px 10px; font-weight: bold;"><a href="/?view={r['id']}" target="_blank" style="color: #2980b9; text-decoration: none;">{clean_t}</a></td>
            <td style="padding: 12px 10px; font-size: 0.85em; color: #777;">{r['created_at']}</td>
            <td style="padding: 12px 10px; text-align: right; white-space: nowrap;">
                <a href="/admin/edit/{r['id']}" style="background: #f39c12; color: white; padding: 7px 14px; text-decoration: none; border-radius: 5px; font-size: 12.5px; font-weight: bold; margin-right: 8px; display: inline-block;">✏️ 수정</a>
                <a href="/admin/delete/{r['id']}" style="background: #e74c3c; color: white; padding: 7px 14px; text-decoration: none; border-radius: 5px; font-size: 12.5px; font-weight: bold; display: inline-block;" onclick="return confirm('정말 이 기사를 삭제하시겠습니까?');">🗑️ 삭제</a>
            </td>
        </tr>
        """
    if not articles_list_html:
        articles_list_html = "<tr><td colspan='4' style='padding: 20px; text-align: center; color: #777;'>등록된 기사가 없습니다.</td></tr>"

    return f"""
    <!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>관리자 스튜디오</title>
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 900px; margin: 0 auto; padding: 15px; background: #f4f6f7; }}
        h1 {{ color: #2c3e50; font-size: 1.5em; }}
        .box {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
        button {{ background: #27ae60; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }}
        .manual-btn {{ background: #2980b9; }} .ai-expand-btn {{ background: #8e44ad; }}
        input[type="text"], select, textarea {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #cbd5e1; border-radius: 4px; box-sizing: border-box; }}
        textarea {{ height: 150px; resize: vertical; }}
        label {{ font-weight: bold; color: #34495e; display: block; margin-top: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        .hub-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 12px; }}
        .hub-btn {{ display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; border-radius: 8px; font-weight: bold; font-size: 13.5px; text-decoration: none; color: white; text-align: center; }}
        .hub-btn-naver-a {{ background: #03c75a; }} .hub-btn-naver-s {{ background: #1f9c53; }} .hub-btn-google-gsc {{ background: #4285f4; }} .hub-btn-google-ga {{ background: #ea4335; }}
        .img-tool-box {{ background: #fdfefe; border: 1px solid #d6dbdf; border-radius: 6px; padding: 12px; margin-bottom: 15px; }}
        .img-tool-row {{ display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
        .btn-action {{ width: auto; padding: 8px 14px; font-size: 13px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; color: white; }}
        .custom-head-box {{ background: #fcf3cf; border: 1.5px solid #f39c12; border-radius: 6px; padding: 14px; margin-top: 10px; margin-bottom: 15px; }}
        .checkbox-label {{ display: flex; align-items: center; gap: 8px; font-weight: bold; color: #7d6608; cursor: pointer; margin-top: 0; }}
        .preview-box-img {{ max-width: 180px; max-height: 100px; border-radius: 4px; margin-top: 8px; display: none; }}
    </style></head>
    <body>
        <a href="/" style="display:inline-block; margin-bottom:15px; color:#3498db; font-weight:bold; text-decoration:none;">← 메인 페이지로</a>
        <h1>🛡️ 시사투데이 창 관리자 스튜디오</h1>
        
        <div class="box" style="border-top: 5px solid #2ecc71;">
            <h3>📊 통계 분석 허브 센터</h3>
            <div class="hub-grid">
                <a href="https://analytics.naver.com/" target="_blank" class="hub-btn hub-btn-naver-a">🟢 네이버 애널리틱스</a>
                <a href="https://searchadvisor.naver.com/" target="_blank" class="hub-btn hub-btn-naver-s">🟢 네이버 서치어드바이저</a>
                <a href="https://search.google.com/search-console" target="_blank" class="hub-btn hub-btn-google-gsc">🔵 구글 서치 콘솔</a>
                <a href="https://analytics.google.com/" target="_blank" class="hub-btn hub-btn-google-ga">🔴 구글 애널리틱스(GA4)</a>
            </div>
        </div>

        <div class="box" style="border-top: 5px solid #27ae60;">
            <h3>🤖 1. 상단: AI 자동 기사 발행 (수동 일회성 발행만 가능)</h3>
            <form action="/admin/create-auto" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사</option><option value="경제/주식">경제/주식</option><option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option><option value="건강/복지">건강/복지</option><option value="생활정보">생활정보</option><option value="연예계뉴스">연예계뉴스</option><option value="스포츠">스포츠</option><option value="지역창">지역창</option>
                </select>

                <div style="background:#f4f6f7; padding:10px; border-radius:6px; margin: 12px 0;">
                    <label class="checkbox-label" style="color:#2c3e50;">
                        <input type="checkbox" name="use_subtitles" value="yes" checked>
                        <span>📌 본문 단락마다 '### 소제목' 자동으로 예쁘게 넣기 (체크 해제 시 평문 출력)</span>
                    </label>
                </div>

                <button type="submit">🚀 최신 핫이슈 심층보도 기사 1회 발행</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #2980b9;">
            <h3>✍️ 2. 중단: 완전 수동 글 작성</h3>
            <form action="/admin/create-manual" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사</option><option value="경제/주식">경제/주식</option><option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option><option value="건강/복지">건강/복지</option><option value="생활정보">생활정보</option><option value="연예계뉴스">연예계뉴스</option><option value="스포츠">스포츠</option><option value="지역창">지역창</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목 입력" required>
                
                <div class="custom-head-box">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_unsplash" id="manual_use_unsplash" value="yes" checked onchange="toggleHeadImgSection('manual')">
                        <span>🖼️ 스마트 고정 이미지 풀 사용하기 (체크 해제 시 직접 지정)</span>
                    </label>
                    <div id="manual_custom_head_wrap" style="display: none; margin-top: 12px; border-top: 1px dashed #e59866; padding-top: 10px;">
                        <small style="color: #a04000; font-weight: bold; display: block; margin-bottom: 6px;">[수동 대표 이미지 설정]</small>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" name="custom_image_url" id="manual_head_url" placeholder="이미지 주소(URL)" style="margin-bottom: 8px; flex: 1;">
                            <button type="button" class="btn-action" style="background: #16a085; height: 42px; margin-top: 8px;" onclick="document.getElementById('manual_head_file').click()">📁 내 기기 파일</button>
                            <input type="file" id="manual_head_file" style="display: none;" accept="image/*" onchange="uploadDirectHeadImage(this, 'manual_head_url', 'manual_head_preview')">
                        </div>
                        <input type="text" name="custom_image_author" placeholder="대표 이미지 출처 표기 (예: 연합뉴스)" style="margin-bottom: 4px;">
                        <img id="manual_head_preview" class="preview-box-img">
                    </div>
                </div>

                <div style="background:#f4f6f7; padding:10px; border-radius:6px; margin-bottom:15px;">
                    <label class="checkbox-label" style="color:#2c3e50;">
                        <input type="checkbox" name="use_subtitles" value="yes" checked>
                        <span>📌 본문 단락마다 '### 소제목' 자동으로 예쁘게 넣기</span>
                    </label>
                </div>

                <label>기사 본문 및 이미지 삽입</label>
                <div class="img-tool-box">
                    <div class="img-tool-title">📷 본문 이미지 삽입 및 출처 입력</div>
                    <div class="img-tool-row"><input type="text" id="manual_source" placeholder="출처 표기 (예: 연합뉴스)" style="flex: 1;"></div>
                    <div class="img-tool-row">
                        <button type="button" class="btn-action" style="background: #e67e22;" onclick="insertImageWithSource('manualContent', 'manual_source')">🌐 URL 주소로 넣기</button>
                        <button type="button" class="btn-action" style="background: #16a085;" onclick="document.getElementById('manual_file_input').click()">📁 내 기기 파일</button>
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
                    <option value="정치/시사">정치/시사</option><option value="경제/주식">경제/주식</option><option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option><option value="건강/복지">건강/복지</option><option value="생활정보">생활정보</option><option value="연예계뉴스">연예계뉴스</option><option value="스포츠">스포츠</option><option value="지역창">지역창</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목 입력" required>
                
                <div class="custom-head-box">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_unsplash" id="expand_use_unsplash" value="yes" checked onchange="toggleHeadImgSection('expand')">
                        <span>🖼️ 스마트 고정 이미지 풀 사용하기 (체크 해제 시 직접 지정)</span>
                    </label>
                    <div id="expand_custom_head_wrap" style="display: none; margin-top: 12px; border-top: 1px dashed #e59866; padding-top: 10px;">
                        <small style="color: #a04000; font-weight: bold; display: block; margin-bottom: 6px;">[수동 대표 이미지 설정]</small>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" name="custom_image_url" id="expand_head_url" placeholder="이미지 주소(URL)" style="margin-bottom: 8px; flex: 1;">
                            <button type="button" class="btn-action" style="background: #16a085; height: 42px; margin-top: 8px;" onclick="document.getElementById('expand_head_file').click()">📁 내 기기 파일</button>
                            <input type="file" id="expand_head_file" style="display: none;" accept="image/*" onchange="uploadDirectHeadImage(this, 'expand_head_url', 'expand_head_preview')">
                        </div>
                        <input type="text" name="custom_image_author" placeholder="대표 이미지 출처 표기 (예: 연합뉴스)" style="margin-bottom: 4px;">
                        <img id="expand_head_preview" class="preview-box-img">
                    </div>
                </div>

                <div style="background:#f4f6f7; padding:10px; border-radius:6px; margin-bottom:15px;">
                    <label class="checkbox-label" style="color:#2c3e50;">
                        <input type="checkbox" name="use_subtitles" value="yes" checked>
                        <span>📌 본문 단락마다 '### 소제목' 자동으로 예쁘게 넣기</span>
                    </label>
                </div>

                <label>AI 확장용 프롬프트 / 메모</label>
                <div class="img-tool-box">
                    <div class="img-tool-title">📷 본문 추가 이미지 삽입 및 출처 입력</div>
                    <div class="img-tool-row"><input type="text" id="expand_source" placeholder="출처 표기" style="flex: 1;"></div>
                    <div class="img-tool-row">
                        <button type="button" class="btn-action" style="background: #e67e22;" onclick="insertImageWithSource('expandPrompt', 'expand_source')">🌐 URL 주소로 넣기</button>
                        <button type="button" class="btn-action" style="background: #16a085;" onclick="document.getElementById('expand_file_input').click()">📁 내 기기 파일</button>
                        <input type="file" id="expand_file_input" style="display: none;" accept="image/*" onchange="uploadImageWithSource(this, 'expandPrompt', 'expand_source')">
                    </div>
                </div>

                <textarea name="prompt" id="expandPrompt" placeholder="AI에게 전달할 취재 메모나 프롬프트를 입력하세요..." required></textarea>
                <button type="submit" class="ai-expand-btn">🪄 명품 신문 스타일 기사 발행하기</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #34495e;">
            <h3>📋 4. 발행된 기사 관리 및 삭제 대장</h3>
            <table><thead><tr style="border-bottom:2px solid #ccc; text-align:left;"><th style="padding:10px;">카테고리</th><th style="padding:10px;">제목</th><th style="padding:10px;">발행일시</th><th style="padding:10px; text-align:right;">관리</th></tr></thead>
            <tbody>{articles_list_html}</tbody></table>
        </div>

        <script>
        function toggleHeadImgSection(type) {{
            const chk = document.getElementById(type + '_use_unsplash');
            const wrap = document.getElementById(type + '_custom_head_wrap');
            wrap.style.display = chk.checked ? 'none' : 'block';
        }}

        async function uploadDirectHeadImage(input, urlInputId, previewImgId) {{
            if (input.files && input.files[0]) {{
                const formData = new FormData();
                formData.append("file", input.files[0]);
                try {{
                    const response = await fetch("/admin/upload-image", {{ method: "POST", body: formData }});
                    const data = await response.json();
                    if (data.url) {{
                        document.getElementById(urlInputId).value = data.url;
                        const preview = document.getElementById(previewImgId);
                        preview.src = data.url;
                        preview.style.display = 'block';
                        alert("대표 이미지가 Supabase 클라우드에 업로드되었습니다!");
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
                    const response = await fetch("/admin/upload-image", {{ method: "POST", body: formData }});
                    const data = await response.json();
                    if (data.url) {{
                        const source = document.getElementById(sourceInputId).value;
                        injectHtmlTag(elementId, data.url, source);
                        document.getElementById(sourceInputId).value = "";
                        alert("사진이 Supabase 클라우드에 업로드되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "오류"));
                    }}
                }} catch (err) {{
                    alert("업로드 오류: " + err);
                }}
                input.value = "";
            }}
        }}
        </script>
    </body></html>
    """

@app.get("/admin/edit/{article_id}", response_class=HTMLResponse)
def edit_page(article_id: int, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    art = get_article_by_id(article_id)
    if not art:
        return RedirectResponse(url="/admin/studio", status_code=303)
    current_img = art.get('image_url', '') or ''
    current_author = art.get('image_author', '') or ''
    clean_t = clean_article_title(art['title'])

    return f"""
    <!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>기사 수정하기</title>
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 0 auto; padding: 15px; background: #f4f6f7; }}
        .box {{ background: white; padding: 20px; border-radius: 8px; }}
        input[type="text"], select, textarea {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
        textarea {{ height: 250px; resize: vertical; }}
        button {{ background: #f39c12; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }}
        .preview-img {{ max-width: 200px; max-height: 120px; border-radius: 6px; margin-top: 5px; display: block; }}
        .header-img-box {{ background: #f8f9fa; border: 1.5px dashed #bdc3c7; border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
        .btn-action {{ width: auto; padding: 8px 14px; font-size: 13px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; color: white; }}
        .img-tool-box {{ background: #fdfefe; border: 1px solid #d6dbdf; border-radius: 6px; padding: 12px; margin-bottom: 15px; }}
        .img-tool-title {{ font-size: 13px; font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
        .img-tool-row {{ display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
    </style></head>
    <body>
        <a href="/admin/studio" style="display:inline-block; margin-bottom:15px; color:#3498db; font-weight:bold; text-decoration:none;">← 관리자 스튜디오로</a>
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
                <input type="text" name="title" value="{clean_t}" required>
                
                <div class="header-img-box">
                    <label style="font-weight: bold; color: #2c3e50; margin-bottom: 8px; display: block;">🖼️ 대표 이미지 설정</label>
                    <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                        <input type="text" id="edit_main_img_url" name="image_url" value="{current_img}" placeholder="대표 이미지 주소(URL)" style="margin-bottom: 0; flex: 1;">
                        <button type="button" class="btn-action" style="background: #16a085; height: 42px;" onclick="document.getElementById('edit_main_file').click()">📁 내 기기 파일</button>
                        <input type="file" id="edit_main_file" style="display: none;" accept="image/*" onchange="uploadEditMainImage(this)">
                    </div>
                    <label>대표 이미지 출처 표기</label>
                    <input type="text" name="image_author" value="{current_author}" placeholder="출처 입력 (예: 연합뉴스)">
                    <img id="edit_main_preview" src="{current_img}" class="preview-img" onerror="this.style.display='none'">
                </div>

                <label>기사 내용 및 본문 추가 이미지 삽입</label>
                <div class="img-tool-box">
                    <div class="img-tool-title">📷 본문 이미지 삽입 및 출처 입력</div>
                    <div class="img-tool-row"><input type="text" id="edit_source" placeholder="출처 표기" style="flex: 1;"></div>
                    <div class="img-tool-row">
                        <button type="button" class="btn-action" style="background: #e67e22;" onclick="insertImageWithSource('editContent', 'edit_source')">🌐 URL 주소로 넣기</button>
                        <button type="button" class="btn-action" style="background: #16a085;" onclick="document.getElementById('edit_file_input').click()">📁 내 기기 파일</button>
                        <input type="file" id="edit_file_input" style="display: none;" accept="image/*" onchange="uploadImageWithSource(this, 'editContent', 'edit_source')">
                    </div>
                </div>

                <textarea name="content" id="editContent" required>{art['content']}</textarea>
                <button type="submit">💾 수정 사항 저장하기</button>
            </form>
        </div>

        <script>
        async function uploadEditMainImage(input) {{
            if (input.files && input.files[0]) {{
                const formData = new FormData();
                formData.append("file", input.files[0]);
                try {{
                    const response = await fetch("/admin/upload-image", {{ method: "POST", body: formData }});
                    const data = await response.json();
                    if (data.url) {{
                        document.getElementById('edit_main_img_url').value = data.url;
                        const preview = document.getElementById('edit_main_preview');
                        preview.src = data.url;
                        preview.style.display = 'block';
                        alert("대표 이미지가 Supabase 클라우드에 업로드되었습니다!");
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
                    const response = await fetch("/admin/upload-image", {{ method: "POST", body: formData }});
                    const data = await response.json();
                    if (data.url) {{
                        const source = document.getElementById(sourceInputId).value;
                        injectHtmlTag(elementId, data.url, source);
                        document.getElementById(sourceInputId).value = "";
                        alert("사진이 Supabase 클라우드에 업로드되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "오류"));
                    }}
                }} catch (err) {{
                    alert("업로드 오류: " + err);
                }}
                input.value = "";
            }}
        }}
        </script>
    </body></html>
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
    clean_t = clean_article_title(title)
    update_article_in_db(article_id, category, clean_t, content, image_url, image_author)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.get("/admin/delete/{article_id}")
def delete_article(article_id: int, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    delete_article_from_db(article_id)
    return RedirectResponse(url="/admin/studio", status_code=303)
