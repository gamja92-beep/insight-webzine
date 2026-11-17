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
        import xml.etree.ElementTree as ET
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
        ("
