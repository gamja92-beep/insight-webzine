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
        ("
