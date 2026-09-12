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

FALLBACK_POOL = {
    "야구": "https://images.unsplash.com/photo-1508344928928-7165b67de128?w=800&auto=format&fit=crop",
    "축구": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=800&auto=format&fit=crop",
    "스포츠": "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=800&auto=format&fit=crop",
    "정치/시사": "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=800&auto=format&fit=crop",
    "경제/주식": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&auto=format&fit=crop",
    "AI/테크": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=800&auto=format&fit=crop",
    "건강/복지": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&auto=format&fit=crop",
    "생활정보": "https://images.unsplash.com/photo-1484807352052-23338990c6c8?w=800&auto=format&fit=crop",
    "연예계뉴스": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&auto=format&fit=crop",
    "지역창": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&auto=format&fit=crop",
    "세상이야기": "https://images.unsplash.com/photo-1477959858617-67f30bc75b82?w=800&auto=format&fit=crop"
}

def fetch_bulletproof_image(category_name, article_title=""):
    title_lower = (article_title + " " + category_name).lower()
    
    if category_name == "스포츠":
        if any(k in title_lower for k in ["야구", "kbo", "홈런", "타자", "투수", "안타", "김도영"]):
            keyword = "baseball"
            default_url = FALLBACK_POOL["야구"]
        elif any(k in title_lower for k in ["축구", "손흥민", "골", "epl", "k리그"]):
            keyword = "soccer"
            default_url = FALLBACK_POOL["축구"]
        else:
            keyword = "stadium"
            default_url = FALLBACK_POOL["스포츠"]
    elif category_name == "AI/테크":
        keyword = "technology"
        default_url = FALLBACK_POOL["AI/테크"]
    elif category_name == "경제/주식":
        keyword = "finance"
        default_url = FALLBACK_POOL["경제/주식"]
    elif category_name == "정치/시사":
        keyword = "capitol"
        default_url = FALLBACK_POOL["정치/시사"]
    elif category_name == "연예계뉴스":
        keyword = "concert"
        default_url = FALLBACK_POOL["연예계뉴스"]
    elif category_name == "지역창":
        keyword = "korea scenery"
        default_url = FALLBACK_POOL["지역창"]
    elif category_name == "건강/복지":
        keyword = "wellness"
        default_url = FALLBACK_POOL["건강/복지"]
    elif category_name == "생활정보":
        keyword = "interior"
        default_url = FALLBACK_POOL["생활정보"]
    else:
        keyword = "nature"
        default_url = FALLBACK_POOL["세상이야기"]

    try:
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        params = {"query": keyword, "orientation": "landscape", "page": random.randint(1, 10)}
        res = requests.get("https://api.unsplash.com/search/photos", headers=headers, params=params, timeout=4)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results:
                item = random.choice(results)
                img_url = item["urls"].get("regular") or item["urls"].get("small")
                author = item.get("user", {}).get("name", "Unsplash")
                if img_url:
                    return img_url, author
    except Exception as e:
        print(f"[이미지 API 경고]: {e}")

    return default_url, "Unsplash"

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
        elif use_subtitles and (p_str.startswith('###') or (len(p_str) < 42 and not p_str.endswith(('.', '?', '!')) and not p_str.startswith('<'))):
            title_text = p_str.replace('###', '').strip()
            title_text = re.sub(r'^\[(기|승|전|결)(:\s*[^\]]+)?\]\s*', '', title_text).strip()
            title_text = re.sub(r'^(기|승|전|결):\s*', '', title_text).strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 32px; margin-bottom: 14px; font-size: 1.15em; font-weight: 800; letter-spacing: -0.5px;">{title_text}</h3>')
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
    formatted_content = clean_and_format_content(content, category, title, use_subtitles=True)
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

def generate_ai_article(category_name):
    news_title, news_desc, pub_date = get_latest_realtime_news(category_name)
    ref_fact_context = f"\n[속보 헤드라인]: {news_title}\n[요약]: {news_desc}\n" if news_title else ""
    
    editorial_prompt = f"""
당신은 팩트를 생명으로 여기는 정론지의 수석 논설위원입니다.
오늘은 **2026년 9월 11일**입니다.
[취재 분야]: {category_name}
{ref_fact_context}
1. 첫 번째 줄: 기사 제목 한 줄.
2. 두 번째 줄: 빈 줄.
3. 세 번째 줄부터: 3~4개 단락 본문.
"""
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=editorial_prompt)
        raw_content = response.text.strip()
    except Exception as e:
        raw_content = f"오류: {e}"

    split_lines = raw_content.split("\n", 1)
    if len(split_lines) > 1 and len(split_lines[0].strip()) <= 60:
        art_title = split_lines[0].replace("#", "").replace("제목:", "").replace("**", "").strip()
        body_content = split_lines[1].strip()
    else:
        art_title = f"{category_name} 실시간 현장 리포트"
        body_content = raw_content

    img_url, author_name = fetch_bulletproof_image(category_name, art_title)
    formatted_content = clean_and_format_content(body_content, category_name, art_title, use_subtitles=True)
    save_article_to_db(category_name, art_title, formatted_content, img_url, author_name)

def scheduled_job():
    categories = ["정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]
    generate_ai_article(random.choice(categories))

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_job, 'interval', hours=6)
scheduler.start()

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
    use_subtitles: str = Form(None),
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
    
    clean_title = title.replace('**', '').replace('*', '').strip()
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
        os.makedirs("static", exist_ok=True)
        file_ext = file.filename.split(".")[-1]
        unique_filename = f"img_{int(time.time())}_{random.randint(1000,9999)}.{file_ext}"
        file_path = os.path.join("static", unique_filename)
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        return {"url": f"/static/{unique_filename}"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/robots.txt", response_class=PlainResponse)
def robots_txt():
    return PlainResponse("User-agent: *\nAllow: /\nSitemap: https://insight-webzine.onrender.com/sitemap.xml", media_type="text/plain")

@app.get("/sitemap.xml", response_class=PlainResponse)
def sitemap():
    articles = get_all_articles()
    base_url = "https://insight-webzine.onrender.com"
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml_content += f"  <url><loc>{base_url}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n"
    for art in articles:
        xml_content += f"  <url><loc>{base_url}/?view={art['id']}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n"
    xml_content += '</urlset>'
    return PlainResponse(content=xml_content, media_type="application/xml")

@app.get("/rss", response_class=PlainResponse)
def rss_feed():
    articles = get_all_articles()
    base_url = "https://insight-webzine.onrender.com"
    rss_content = '<?xml version="1.0" encoding="UTF-8" ?>\n<rss version="2.0">\n<channel>\n  <title>시사투데이 창</title>\n  <link>' + base_url + '/</link>\n  <description>프리미엄 시사투데이 창</description>\n'
    for art in articles:
        rss_content += f"  <item>\n    <title>{art['title'].replace('&', '&amp;')}</title>\n    <link>{base_url}/?view={art['id']}</link>\n    <guid>{base_url}/?view={art['id']}</guid>\n    <pubDate>{art['created_at']}</pubDate>\n  </item>\n"
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
        img_block = f'<img src="{art["image_url"]}" class="article-img"><div class="img-source">📷 Photo by {art.get("image_author", "")}</div>' if art.get("image_url") else ""
        return f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{art['title']} - 시사투데이 창</title>
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
            </style>
        </head>
        <body>
            <div class="top-bar"><a href="/" class="back-btn">← 메인 뉴스로 돌아가기</a></div>
            <div class="article-container">
                <h1>{art['title']}</h1>
                <div class="date">발행일시: {art['created_at']}</div>
                {img_block}
                <div class="content">{art['content']}</div>
            </div>
            {subscribe_card_html}{subscribe_js}
        </body>
        </html>
        """

    articles = get_all_articles(category)
    if q and q.strip():
        kw = q.strip().lower()
        articles = [a for a in articles if kw in a['title'].lower() or kw in a['content'].lower()]

    categories = ["전체", "정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]

    # 대표 이미지 카드 생성 (전체보기일 땐 최신 2개, 특정 카테고리일 땐 해당 카테고리 최신 2개)
    featured_articles = articles[:2] if articles else []
    featured_html = ""
    for art in featured_articles:
        cat_name = art['category'] if art['category'] else '종합'
        img_url = art['image_url'] if art['image_url'] else FALLBACK_POOL.get(cat_name, FALLBACK_POOL["세상이야기"])
        featured_html += f"""
        <div class="featured-card">
            <div class="featured-img-wrap">
                <a href="/?view={art['id']}"><img src="{img_url}" class="featured-img" onerror="this.src='{FALLBACK_POOL.get(cat_name, FALLBACK_POOL['세상이야기'])}'"></a>
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
        # 특정 카테고리일 때: 상단에 대표카드 2개를 보여주고, 남은 기사들을 리스트로 출력
        remaining_articles = articles[2:] if len(articles) > 2 else []
        if remaining_articles:
            list_html += f'<div class="news-section-box"><div class="section-header">📌 {category} 이전 리포트</div>'
            for art in remaining_articles:
                list_html += f"""
                <div class="news-list-item">
                    <a href="/?view={art['id']}" class="list-title">{art['title']}</a>
                    <span class="list-date">{art['created_at'].split()[0]}</span>
                </div>
                """
            list_html += '</div>'
    else:
        # 전체보기일 때: 카테고리별로 리스트 묶어서 출력
        display_cats = ["정치/시사", "경제/주식", "세상이야기", "AI/테크", "건강/복지", "생활정보", "연예계뉴스", "스포츠", "지역창"]
        for cat in display_cats:
            cat_arts = [a for a in articles if a.get('category') == cat][:5]
            if cat_arts:
                list_html += f'<div class="news-section-box"><div class="section-header">📂 {cat} 최신 소식</div>'
                for art in cat_arts:
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
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>시사투데이 창 - 프리미엄 미디어</title>
        <link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&display=swap" rel="stylesheet">
        {NAVER_ANALYTICS_SCRIPT}{GOOGLE_ANALYTICS_SCRIPT}
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 900px; margin: 0 auto; padding: 10px; background: #f0f3f4; color: #333; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 4px solid #1b4f72; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.05); }}
            .logo-title {{ font-family: 'Gowun Batang', serif; font-size: 1.6em; font-weight: 700; color: #1a252f; display: flex; align-items: center; gap: 8px; }}
            .logo-chang {{ display: inline-block; background: #fff; color: #111; border: 2.5px solid #111; padding: 4px 16px; border-radius: 6px; transform: rotate(5deg); box-shadow: 3px 3px 6px rgba(0,0,0,0.12); }}
            .nav-tabs {{ display: flex; gap: 5px; margin: 15px 0; flex-wrap: wrap; background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }}
            .tab-item {{ flex: 1; min-width: 75px; text-align: center; padding: 6px 4px; background: #ecf0f1; color: #555; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 12px; white-space: nowrap; }}
            .tab-item:hover, .tab-item.active {{ background: #1b4f72; color: white; }}
            
            .featured-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 15px; margin-bottom: 20px; }}
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
        <div class="header-flex"><div class="logo-title">시사투데이&nbsp;<span class="logo-chang">창</span></div></div>
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
        articles_list_html += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 12px 10px; font-size: 0.9em; color: #555;">{r['category']}</td>
            <td style="padding: 12px 10px; font-weight: bold;"><a href="/?view={r['id']}" target="_blank" style="color: #2980b9; text-decoration: none;">{r['title']}</a></td>
            <td style="padding: 12px 10px; font-size: 0.85em; color: #777;">{r['created_at']}</td>
            <td style="padding: 12px 10px; text-align: right;">
                <a href="/admin/edit/{r['id']}" style="background: #f39c12; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 4px;">✏️ 수정</a>
                <a href="/admin/delete/{r['id']}" style="background: #e74c3c; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;" onclick="return confirm('삭제하시겠습니까?');">🗑️ 삭제</a>
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
            <h3>🤖 1. 상단: AI 자동 기사 발행</h3>
            <form action="/admin/create-auto" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사</option><option value="경제/주식">경제/주식</option><option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option><option value="건강/복지">건강/복지</option><option value="생활정보">생활정보</option>
                    <option value="연예계뉴스">연예계뉴스</option><option value="스포츠">스포츠</option><option value="지역창">지역창</option>
                </select>
                <button type="submit">🚀 최신 속보 기반 기사 발행</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #2980b9;">
            <h3>✍️ 2. 중단: 완전 수동 글 작성</h3>
            <form action="/admin/create-manual" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="정치/시사">정치/시사</option><option value="경제/주식">경제/주식</option><option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option><option value="건강/복지">건강/복지</option><option value="생활정보">생활정보</option>
                    <option value="연예계뉴스">연예계뉴스</option><option value="스포츠">스포츠</option><option value="지역창">지역창</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목 입력" required>
                
                <div class="custom-head-box">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_unsplash" id="manual_use_unsplash" value="yes" checked onchange="toggleHeadImgSection('manual')">
                        <span>🖼️ 언스플래시 자동 대표 이미지 사용하기 (체크 해제 시 직접 지정)</span>
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
                    <option value="AI/테크">AI/테크</option><option value="건강/복지">건강/복지</option><option value="생활정보">생활정보</option>
                    <option value="연예계뉴스">연예계뉴스</option><option value="스포츠">스포츠</option><option value="지역창">지역창</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목 입력" required>
                
                <div class="custom-head-box">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_unsplash" id="expand_use_unsplash" value="yes" checked onchange="toggleHeadImgSection('expand')">
                        <span>🖼️ 언스플래시 자동 대표 이미지 사용하기 (체크 해제 시 직접 지정)</span>
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
                        alert("대표 이미지가 성공적으로 업로드되었습니다!");
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
                        alert("사진이 성공적으로 삽입되었습니다!");
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
                <input type="text" name="title" value="{art['title']}" required>
                <div class="header-img-box">
                    <label>대표 이미지 주소(URL)</label>
                    <input type="text" id="main_img_url" name="image_url" value="{current_img}">
                    <label>대표 이미지 출처 표기</label>
                    <input type="text" name="image_author" value="{current_author}">
                    <img id="main_img_preview" src="{current_img}" class="preview-img" onerror="this.style.display='none'">
                </div>
                <label>기사 내용</label>
                <textarea name="content" required>{art['content']}</textarea>
                <button type="submit">💾 수정 사항 저장하기</button>
            </form>
        </div></body></html>
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
