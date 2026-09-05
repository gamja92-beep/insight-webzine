import sys
import os
import sqlite3
import random
import time
import requests
import re
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
MODEL_NAME = "gemini-3.5-flash"

UNSPLASH_ACCESS_KEY = "14W3nppcnrDp-1qJbpqzxERefLjS25QFZIZ27uYEhhA"
ADMIN_PASSWORD = "1234"

client = genai.Client(api_key=API_KEY)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visited_at TEXT
            )
        """)
        conn.commit()
        conn.close()

init_db()

def log_visitor():
    kst = timezone(timedelta(hours=9))
    current_time_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    if supabase:
        try:
            supabase.table("visitors").insert({"visited_at": current_time_str}).execute()
        except Exception:
            pass
    else:
        try:
            conn = sqlite3.connect("database.db", check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO visitors (visited_at) VALUES (?)", (current_time_str,))
            conn.commit()
            conn.close()
        except Exception:
            pass

def get_visitor_stats():
    if supabase:
        try:
            res = supabase.table("visitors").select("*", count="exact").execute()
            total_count = res.count if res.count is not None else len(res.data or [])
            
            kst = timezone(timedelta(hours=9))
            today_str = datetime.now(kst).strftime("%Y-%m-%d")
            res_today = supabase.table("visitors").select("*", count="exact").gte("visited_at", f"{today_str} 00:00:00").execute()
            today_count = res_today.count if res_today.count is not None else len(res_today.data or [])
            
            recent_res = supabase.table("visitors").select("*").order("id", desc=True).limit(5).execute()
            recent_logs = recent_res.data or []
            return total_count, today_count, recent_logs
        except Exception:
            return 0, 0, []
    else:
        try:
            conn = sqlite3.connect("database.db", check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM visitors")
            total_count = cursor.fetchone()[0]
            
            kst = timezone(timedelta(hours=9))
            today_str = datetime.now(kst).strftime("%Y-%m-%d")
            cursor.execute("SELECT COUNT(*) FROM visitors WHERE visited_at >= ?", (f"{today_str} 00:00:00",))
            today_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT id, visited_at FROM visitors ORDER BY id DESC LIMIT 5")
            rows = cursor.fetchall()
            conn.close()
            recent_logs = [{"visited_at": r[1]} for r in rows]
            return total_count, today_count, recent_logs
        except Exception:
            return 0, 0, []

def fetch_bulletproof_image(category_name):
    direct_pools = {
        "AI/테크": [
            ("https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5", "Unsplash"),
            ("https://images.unsplash.com/photo-1518770660439-4636190af475", "Unsplash"),
            ("https://images.unsplash.com/photo-1531482615713-2afd69097998", "Unsplash"),
            ("https://images.unsplash.com/photo-1550751827-4bd374c3f58b", "Unsplash")
        ],
        "경제/주식": [
            ("https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3", "Unsplash"),
            ("https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f", "Unsplash"),
            ("https://images.unsplash.com/photo-1486406146926-c627a92ad1ab", "Unsplash"),
            ("https://images.unsplash.com/photo-1460925895917-afdab827c52f", "Unsplash")
        ],
        "세상이야기": [
            ("https://images.unsplash.com/photo-1477959858617-67f30bc75b82", "Unsplash"),
            ("https://images.unsplash.com/photo-1449824913935-59a10b8d2000", "Unsplash"),
            ("https://images.unsplash.com/photo-1469571486292-0ba58a3f068b", "Unsplash"),
            ("https://images.unsplash.com/photo-1506744038136-46273834b3fb", "Unsplash")
        ],
        "시니어/복지": [
            ("https://images.unsplash.com/photo-1507525428034-b723cf961d3e", "Unsplash"),
            ("https://images.unsplash.com/photo-1501785888041-af3ef285b470", "Unsplash"),
            ("https://images.unsplash.com/photo-1500648767791-00dcc994a43e", "Unsplash"),
            ("https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05", "Unsplash")
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
        ]
    }

    pool = direct_pools.get(category_name, direct_pools["세상이야기"])
    
    try:
        search_queries = {
            "AI/테크": "futuristic technology abstract background wide",
            "경제/주식": "modern city skyscraper architecture wide",
            "세상이야기": "beautiful nature landscape sceneries wide",
            "시니어/복지": "peaceful nature park scenery wide",
            "연예계뉴스": "empty concert stage lights background wide",
            "스포츠": "empty stadium sports arena field wide"
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

def clean_and_format_content(text, category_name="종합"):
    text = text.replace('**', '').replace('__', '')
    
    if '<p' in text or '<img' in text:
        return text

    paragraphs = text.split('\n')
    processed_lines = []
    
    for p in paragraphs:
        p_str = p.strip()
        if not p_str:
            continue
        if p_str.startswith('<img') or p_str.startswith('<div'):
            processed_lines.append(p_str)
        elif p_str.startswith('###'):
            title_text = p_str.replace('###', '').strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 32px; margin-bottom: 14px; font-size: 1.15em; font-weight: 800; letter-spacing: -0.5px;">{title_text}</h3>')
        elif len(p_str) < 42 and not p_str.endswith(('.', '?', '!')) and not p_str.startswith('<'):
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 32px; margin-bottom: 14px; font-size: 1.15em; font-weight: 800; letter-spacing: -0.5px;">{p_str}</h3>')
        else:
            processed_lines.append(f'<p style="margin-bottom: 24px; text-align: left !important; word-break: normal; line-height: 1.8; color: #111111; font-size: 1.02em; letter-spacing: -0.3px;">{p_str}</p>')
            
    final_html = "".join(processed_lines)
    
    text_for_tags = re.sub(r'###+', '', text)
    all_words = text_for_tags.split()
    hashtags = [w for w in all_words if w.startswith('#') and len(w) > 1 and not w.startswith('#2c')]
    
    unique_tags = list(dict.fromkeys(hashtags))
    fallback_tags = {
        "AI/테크": ["#인공지능", "#테크트렌드", "#AI반도체", "#디지털혁신", "#미래기술"],
        "경제/주식": ["#주식투자", "#경제동향", "#시장분석", "#자산관리", "#투자전략"],
        "세상이야기": ["#세상이야기", "#라이프스타일", "#감동글", "#일상소통", "#휴식"],
        "시니어/복지": ["#시니어복지", "#은퇴설계", "#건강관리", "#노후준비", "#행복한삶"],
        "연예계뉴스": ["#연예계트렌드", "#방송가전망", "#문화예술", "#엔터인사이트", "#미디어분석"],
        "스포츠": ["#스포츠분석", "#기록전망", "#스포츠인사이트", "#전술연구", "#스포츠칼럼"]
    }
    
    if len(unique_tags) < 3:
        unique_tags = fallback_tags.get(category_name, ["#종합뉴스", "#트렌드", "#인사이트", "#정보", "#공유"])

    cleaned_tags = []
    for t in unique_tags[:5]:
        t_clean = re.sub(r'^[#\s#]+', '#', str(t).strip())
        if not t_clean.startswith('#'):
            t_clean = '#' + t_clean
        cleaned_tags.append(t_clean)

    clean_tags_str = " ".join(cleaned_tags)
    tag_html = f"<div style='margin-top: 35px; padding-top: 15px; border-top: 1px solid #eaecee; color: #2980b9; font-weight: bold; font-size: 0.85em; word-spacing: 5px;'>{clean_tags_str}</div>"
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

def update_article_in_db(article_id, category, title, content, image_url):
    formatted_content = clean_and_format_content(content, category)
    
    if supabase:
        update_data = {
            "category": category,
            "title": title,
            "content": formatted_content
        }
        if image_url and image_url.strip():
            update_data["image_url"] = image_url.strip()
            update_data["image_author"] = "User Custom"
            
        supabase.table("articles").update(update_data).eq("id", article_id).execute()
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        cursor = conn.cursor()
        if image_url and image_url.strip():
            cursor.execute("UPDATE articles SET category = ?, title = ?, content = ?, image_url = ?, image_author = ? WHERE id = ?", (category, title, formatted_content, image_url.strip(), "User Custom", article_id))
        else:
            cursor.execute("UPDATE articles SET category = ?, title = ?, content = ? WHERE id = ?", (category, title, formatted_content, article_id))
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
    strict_insight_context = (
        "STRICT EDITORIAL RULE: Today is September 4, 2026. "
        "For Sports and Entertainment categories, DO NOT write match results, past game scores, or retrospective match recaps. "
        "Instead, write professional, analytical insight columns focusing on sports/entertainment industry trends, tactical evolution, player milestone predictions, structural issues, or future outlooks. "
        "Never fabricate past game scores or fake match results."
    )

    prompts = {
        "AI/테크": ("AI/테크", f"{strict_insight_context} 첫 번째 줄에는 반드시 명확하고 짧은 기사 제목을 한 줄로 작성해 주고, 두 번째 줄부터는 빈 줄을 두고 본문을 작성해 줘. 2026년 9월 현재 주목받는 AI 기술 트렌드에 대한 전문적인 뉴스 기사를 작성해 주고, 소제목 앞에는 반드시 '### ' 기호를 붙여 줘. 마지막 줄에는 검색용 해시태그 5개를 #인공지능 #테크 형태로 공백을 두고 붙여 줘."),
        "경제/주식": ("경제/주식", f"{strict_insight_context} 첫 번째 줄에는 반드시 명확하고 짧은 기사 제목을 한 줄로 작성해 주고, 두 번째 줄부터는 빈 줄을 두고 본문을 작성해 줘. 2026년 9월 현재 주식 시장과 경제 동향에 대한 전문적인 뉴스 기사를 작성해 주고, 소제목 앞에는 반드시 '### ' 기호를 붙여 줘. 마지막 줄에는 검색용 해시태그 5개를 #주식투자 #경제동향 형태로 공백을 두고 붙여 줘."),
        "세상이야기": ("세상이야기", f"{strict_insight_context} 첫 번째 줄에는 반드시 명확하고 짧은 기사 제목을 한 줄로 작성해 주고, 두 번째 줄부터는 빈 줄을 두고 본문을 작성해 줘. 2026년 9월 현재 우리 주변의 따뜻한 세상 이야기나 트렌드에 대한 뉴스 기사를 작성해 주고, 소제목 앞에는 반드시 '### ' 기호를 붙여 줘. 마지막 줄에는 검색용 해시태그 5개를 #세상이야기 #라이프 형태로 공백을 두고 붙여 줘."),
        "시니어/복지": ("시니어/복지", f"{strict_insight_context} 첫 번째 줄에는 반드시 명확하고 짧은 기사 제목을 한 줄로 작성해 주고, 두 번째 줄부터는 빈 줄을 두고 본문을 작성해 줘. 2026년 9월 현재 시니어 세대를 위한 유용한 복지 정책과 건강 관리에 대한 뉴스 기사를 작성해 주고, 소제목 앞에는 반드시 '### ' 기호를 붙여 줘. 마지막 줄에는 검색용 해시태그 5개를 #시니어복지 #은퇴설계 형태로 공백을 두고 붙여 줘."),
        "연예계뉴스": ("연예계뉴스", f"{strict_insight_context} 첫 번째 줄에는 반드시 명확하고 짧은 기사 제목을 한 줄로 작성해 주고, 두 번째 줄부터는 빈 줄을 두고 본문을 작성해 줘. 2026년 9월 현재 방송가와 대중문화계의 구조적 트렌드, 콘텐츠 제작 방식의 변화, 미디어 산업 전망 등을 다루는 깊이 있는 분석/인사이트 칼럼 기사를 작성해 주세요. 절대 가짜 스캔들나 찌라시성 가십을 쓰지 마세요. 소제목 앞에는 반드시 '### ' 기호를 붙여 줘. 마지막 줄에는 검색용 해시태그 5개를 #연예계트렌드 #방송가전망 형태로 공백을 두고 붙여 줘."),
        "스포츠": ("스포츠", f"{strict_insight_context} 첫 번째 줄에는 반드시 명확하고 짧은 기사 제목을 한 줄로 작성해 주고, 두 번째 줄부터는 빈 줄을 두고 본문을 작성해 줘. 2026년 9월 현재 스포츠계의 전술적 트렌디함, 유망주 육성 시스템의 변화, 선수의 대기록 달성 가능성 예측, 스포츠 산업의 구조적 과제 등을 다루는 전문적이고 품격 있는 '스포츠 인사이트 칼럼'을 작성해 주세요. 절대 지난 경기 스코어나 가짜 경기 결과를 기사로 쓰지 마세요. 소제목 앞에는 반드시 '### ' 기호를 붙여 줘. 마지막 줄에는 검색용 해시태그 5개를 #스포츠분석 #기록전망 형태로 공백을 두고 붙여 줘.")
    }
    
    cat_info = prompts.get(category_name, ("종합", f"{strict_insight_context} 최신 트렌드 뉴스 기사 작성"))
    prompt = cat_info[1]
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        raw_content = response.text.strip()
    except Exception as e:
        raw_content = f"기사 생성 오류: {e}"

    split_lines = raw_content.split("\n", 1)
    if len(split_lines) > 1 and len(split_lines[0].strip()) <= 55:
        art_title = split_lines[0].replace("#", "").replace("제목:", "").replace("**", "").strip()
        body_content = split_lines[1].strip()
    else:
        art_title = f"{category_name} 인사이트 리포트"
        body_content = raw_content

    img_url, author_name = fetch_bulletproof_image(category_name)
    formatted_content = clean_and_format_content(body_content, category_name)
    save_article_to_db(category_name, art_title, formatted_content, img_url, author_name)

def scheduled_job():
    categories = ["AI/테크", "경제/주식", "세상이야기", "시니어/복지", "연예계뉴스", "스포츠"]
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

# 🌟 [구글 봇 방화벽을 완전히 해제하는 초강력 스매싱 robots.txt 엔드포인트]
@app.get("/robots.txt", response_class=PlainResponse)
def robots_txt():
    robots_text = (
        "User-agent: *\n"
        "Allow: /\n\n"
        "User-agent: Googlebot\n"
        "Allow: /\n\n"
        "Sitemap: https://insight-webzine.onrender.com/sitemap.xml"
    )
    return PlainResponse(content=robots_text, media_type="text/plain")

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
    
    rss_content = '<?xml version="1.0" encoding="UTF-8" ?>\n'
    rss_content += '<rss version="2.0">\n<channel>\n'
    rss_content += '  <title>인사이트 종합 미디어</title>\n'
    rss_content += f'  <link>{base_url}/</link>\n'
    rss_content += '  <description>프리미엄 인사이트 웹진 - AI와 경제, 시니어 트렌드 뉴스</description>\n'
    
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

@app.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = None, view: int = None):
    log_visitor()

    if view:
        art = get_article_by_id(view)
        if not art:
            return RedirectResponse(url="/", status_code=303)
        
        art_title_clean = art['title'].replace('"', '')
        art_desc_clean = art['content'][:100].replace('<p>', '').replace('</p>', '').replace('"', '')
        art_img = art['image_url']
        art_link = f"https://insight-webzine.onrender.com/?view={art['id']}"

        detail_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{art_title_clean} - 인사이트 종합 웹진</title>
            <meta name="description" content="{art_desc_clean}">
            <meta property="og:title" content="{art_title_clean}">
            <meta property="og:description" content="{art_desc_clean}">
            <meta property="og:image" content="{art_img}">
            <meta property="og:url" content="{art_link}">
            <style>
                body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; width: 100%; margin: 0 auto; padding: 15px; background: #f8f9fa; color: #111111; line-height: 1.8; box-sizing: border-box; }}
                .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }}
                .back-btn {{ display: inline-block; padding: 10px 20px; background: #1b4f72; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; transition: 0.2s; }}
                .back-btn:hover {{ background: #12334a; }}
                
                .article-container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }}
                .badge {{ display: inline-block; padding: 5px 14px; background: #ebf5fb; color: #2980b9; border-radius: 4px; font-size: 0.9em; font-weight: bold; margin-bottom: 12px; }}
                h1 {{ font-size: 1.6em; color: #1a252f; margin-top: 10px; margin-bottom: 15px; line-height: 1.35; word-break: keep-all; letter-spacing: -0.5px; }}
                .date {{ font-size: 0.9em; color: #7f8c8d; margin-bottom: 25px; border-bottom: 1px solid #eaecee; padding-bottom: 15px; }}
                .article-img {{ width: 100%; max-height: 480px; object-fit: cover; border-radius: 8px; margin-bottom: 10px; }}
                .img-source {{ font-size: 0.85em; color: #95a5a6; margin-bottom: 30px; font-style: italic; }}
                .content {{ font-size: 1.02em; color: #111111; word-break: normal; text-align: left !important; line-height: 1.8; letter-spacing: -0.3px; }}
                .content p {{ margin-bottom: 24px; text-align: left !important; word-break: normal; }}
                
                .article-footer {{ text-align: center; margin-top: 40px; padding-top: 25px; border-top: 1px solid #eaecee; }}
                .subscribe-btn-compact {{ display: inline-block; padding: 8px 22px; background: #e74c3c; color: white; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 0.92em; box-shadow: 0 2px 8px rgba(231, 76, 60, 0.25); transition: 0.2s; }}
                .subscribe-btn-compact:hover {{ background: #c0392b; transform: scale(1.03); }}

                img {{ max-width: 100% !important; height: auto !important; }}
            </style>
        </head>
        <body>
            <div class="top-bar">
                <a href="/" class="back-btn">← 메인 뉴스로 돌아가기</a>
            </div>

            <div class="article-container">
                <span class="badge">{art['category']}</span>
                <h1>{art['title']}</h1>
                <div class="date">발행일시: {art['created_at']}</div>
                <img src="{art['image_url']}" class="article-img">
                <div class="img-source">📷 Photo by {art['image_author']}</div>
                <div class="content">{art['content']}</div>
                
                <div class="article-footer">
                    <a href="javascript:alert('⭐ [구독(즐겨찾기) 안내]\\n\\n아이폰: 하단 공유(📤) 버튼 → [책갈피 추가] 또는 [홈 화면에 추가]\\n갤럭시: 우측 상단 메뉴(⋮) → [⭐ 북마크 추가]\\n\\n언제든 쉽고 빠르게 다시 찾아오실 수 있습니다!');" class="subscribe-btn-compact">🔔 구독하기 (즐겨찾기)</a>
                </div>
            </div>
        </body>
        </html>
        """
        return detail_html

    articles = get_all_articles(category)
    categories = ["전체", "AI/테크", "경제/주식", "세상이야기", "시니어/복지", "연예계뉴스", "스포츠"]

    featured_articles = articles[:2] if articles else []
    list_articles = articles[2:] if len(articles) > 2 else []

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
    for art in list_articles:
        list_html += f"""
        <div class="news-list-item">
            <a href="/?view={art['id']}" class="list-title">{art['title']}</a>
            <span class="list-date">{art['created_at'].split()[0]}</span>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>인사이트 종합 미디어 - 프리미엄 미디어</title>
        <meta name="description" content="AI, 경제, 주식, 시니어 복지 및 세상 이야기를 전하는 프리미엄 인사이트 종합 미디어">
        <meta property="og:title" content="인사이트 종합 미디어">
        <meta property="og:description" content="AI, 경제, 주식, 시니어 복지 및 세상 이야기를 전하는 프리미엄 인사이트 종합 미디어">
        <meta property="og:image" content="https://images.unsplash.com/photo-1451187580459-43490279c0fa">
        <meta property="og:url" content="https://insight-webzine.onrender.com/">
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 900px; width: 100%; margin: 0 auto; padding: 10px; background: #f0f3f4; color: #333; box-sizing: border-box; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 4px solid #1b4f72; padding-bottom: 15px; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.05); flex-wrap: wrap; gap: 10px; }}
            h1 {{ color: #1a252f; margin: 0; font-size: 1.5em; letter-spacing: -0.5px; word-break: keep-all; }}
            
            .main-subscribe-btn {{ padding: 6px 14px; background: #e74c3c; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 0.85em; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .main-subscribe-btn:hover {{ background: #c0392b; }}

            .nav-tabs {{ display: flex; gap: 6px; margin: 15px 0; flex-wrap: wrap; background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }}
            .tab-item {{ padding: 6px 12px; background: #ecf0f1; color: #555; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 13px; transition: 0.2s; white-space: nowrap; }}
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

            .news-list-box {{ background: white; border-radius: 10px; padding: 10px 20px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); margin-top: 15px; }}
            .news-list-item {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid #f1f2f6; }}
            .news-list-item:last-child {{ border-bottom: none; }}
            .list-title {{ flex-grow: 1; font-size: 0.98em; color: #2c3e50; text-decoration: none; font-weight: 600; word-break: keep-all; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 15px; }}
            .list-title:hover {{ color: #2980b9; text-decoration: underline; }}
            .list-date {{ font-size: 0.78em; color: #95a5a6; white-space: nowrap; }}

            img {{ max-width: 100% !important; height: auto !important; }}
        </style>
    </head>
    <body>
        <div class="header-flex">
            <h1>📰 인사이트 종합 미디어</h1>
            <a href="javascript:alert('⭐ [즐겨찾기 안내]\\n\\n아이폰: 하단 공유(📤) 버튼 → [책갈피 추가] 또는 [홈 화면에 추가]\\n갤럭시: 우측 상단 메뉴(⋮) → [⭐ 북마크 추가]\\n\\n언제든 쉽고 빠르게 다시 찾아오실 수 있습니다!');" class="main-subscribe-btn">⭐ 즐겨찾기</a>
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
            html += f'<div class="news-list-box">{list_html}</div>'
        
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
    total_v, today_v, recent_logs = get_visitor_stats()

    recent_logs_html = ""
    for log in recent_logs:
        recent_logs_html += f"<li style='margin-bottom: 5px; color: #555;'>🕒 방문 시각: {log['visited_at']}</li>"
    if not recent_logs_html:
        recent_logs_html = "<li style='color: #777;'>최근 방문 기록이 없습니다.</li>"

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
        <title>인사이트 웹진 관리자 스튜디오</title>
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
            .stat-card {{ display: inline-block; width: 45%; background: #ebf5fb; padding: 15px; border-radius: 6px; text-align: center; margin-right: 4%; }}
            .stat-num {{ font-size: 1.8em; font-weight: bold; color: #2980b9; margin-top: 5px; }}
            .img-btn-group {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }}
            .img-btn {{ background: #e67e22; color: white; border: none; padding: 8px 14px; font-size: 13px; border-radius: 4px; cursor: pointer; font-weight: bold; display: inline-block; }}
            .img-btn:hover {{ background: #d35400; }}
            .file-input {{ display: none; }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <h1>🛡️ 철옹성 웹진 관리자 스튜디오 (클라우드 연동됨)</h1>
        
        <div class="box" style="border-top: 5px solid #e67e22;">
            <h3>📊 실시간 방문자 현황</h3>
            <div style="margin-top: 15px; display: flex; justify-content: space-between;">
                <div class="stat-card" style="width: 48%;">
                    <div style="color: #555; font-weight: bold;">오늘 방문 수</div>
                    <div class="stat-num">{today_v} 명</div>
                </div>
                <div class="stat-card" style="width: 48%; margin-right: 0; background: #e8f8f5;">
                    <div style="color: #555; font-weight: bold;">누적 총 방문 수</div>
                    <div class="stat-num" style="color: #16a085;">{total_v} 명</div>
                </div>
            </div>
            <div style="margin-top: 20px;">
                <h4 style="margin-bottom: 8px; color: #333;">최근 방문 로그 (최신 5건)</h4>
                <ul style="padding-left: 20px; font-size: 0.9em; margin: 0;">
                    {recent_logs_html}
                </ul>
            </div>
        </div>

        <div class="box" style="border-top: 5px solid #27ae60;">
            <h3>🤖 1. 상단: AI 자동 기사 발행</h3>
            <form action="/admin/create-auto" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                    <option value="연예계뉴스">연예계뉴스</option>
                    <option value="스포츠">스포츠</option>
                </select>
                <button type="submit">🚀 즉시 자동 기사 발행하기</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #2980b9;">
            <h3>✍️ 2. 중단: 완전 수동 글 작성</h3>
            <form action="/admin/create-manual" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                    <option value="연예계뉴스">연예계뉴스</option>
                    <option value="스포츠">스포츠</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="제목을 입력하세요" required>
                <label>기사 내용</label>
                
                <div class="img-btn-group">
                    <button type="button" class="img-btn" onclick="insertImageByUrl('manualContent')">🌐 웹 주소(URL)로 이미지 넣기</button>
                    <button type="button" class="img-btn" style="background: #16a085;" onclick="document.getElementById('manualFile').click()">📁 내 기기 파일(JPEG/PNG) 바로 올리기</button>
                    <input type="file" id="manualFile" class="file-input" accept="image/*" onchange="uploadImageFile(this, 'manualContent')">
                </div>

                <textarea name="content" id="manualContent" placeholder="내용을 직접 작성하세요..." required></textarea>
                <button type="submit" class="manual-btn">📝 직접 작성한 글 발행하기</button>
            </form>
        </div>

        <div class="box" style="border-top: 5px solid #8e44ad;">
            <h3>✨ 3. 하단: AI 프롬프트 확장 발행 (신문 스타일 자동 적용)</h3>
            <form action="/admin/create-ai-expand" method="post">
                <label>카테고리 선택</label>
                <select name="category">
                    <option value="AI/테크">AI/테크</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="시니어/복지">시니어/복지</option>
                    <option value="연예계뉴스">연예계뉴스</option>
                    <option value="스포츠">스포츠</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" placeholder="기사 제목을 입력하세요" required>
                <label>AI 확장용 프롬프트 / 메모</label>
                
                <div class="img-btn-group">
                    <button type="button" class="img-btn" onclick="insertImageByUrl('expandPrompt')">🌐 웹 주소(URL)로 이미지 넣기</button>
                    <button type="button" class="img-btn" style="background: #16a085;" onclick="document.getElementById('expandFile').click()">📁 내 기기 파일(JPEG/PNG) 바로 올리기</button>
                    <input type="file" id="expandFile" class="file-input" accept="image/*" onchange="uploadImageFile(this, 'expandPrompt')">
                </div>

                <textarea name="prompt" id="expandPrompt" placeholder="예: AI 거품론과 인프라 투자 포인트에 대해 전문적인 분석 기사로 상세히 작성해줘." required></textarea>
                <button type="submit" class="ai-expand-btn">🪄 명품 신문 스타일 기사 발행하기</button>
            </form>
        </div>

        <script>
        function insertImageByUrl(elementId) {{
            const url = prompt("넣을 이미지의 웹 주소(URL)를 입력하세요:");
            if (url) {{
                const tag = '\\n<img src="' + url.trim() + '" style="width: 100%; border-radius: 8px; margin: 20px 0;">\\n';
                const textarea = document.getElementById(elementId);
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
                textarea.focus();
            }}
        }}

        async function uploadImageFile(input, elementId) {{
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
                        const tag = '\\n<img src="' + data.url + '" style="width: 100%; border-radius: 8px; margin: 20px 0;">\\n';
                        const textarea = document.getElementById(elementId);
                        const start = textarea.selectionStart;
                        const end = textarea.selectionEnd;
                        textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
                        textarea.focus();
                        alert("사진이 성공적으로 업로드되어 커서 위치에 삽입되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "알 수 없는 오류"));
                    }}
                }} catch (err) {{
                    alert("사진 업로드 중 오류가 발생했습니다: " + err);
                }}
                input.value = "";
            }}
        }}
        </script>

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
def create_manual(category: str = Form(...), title: str = Form(...), content: str = Form(...), admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = title.replace('**', '').replace('*', '').strip()
    img_url, author_name = fetch_bulletproof_image(category)
    
    formatted_content = clean_and_format_content(content, category)

    save_article_to_db(category, clean_title, formatted_content, img_url, author_name)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.post("/admin/create-ai-expand")
def create_ai_expand(category: str = Form(...), title: str = Form(...), prompt: str = Form(...), admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = title.replace('**', '').replace('*', '').strip()
    system_directive = (
        "당신은 전문 수석 뉴스 기자입니다. "
        "사용자가 제공한 [기사 제목]과 [작성 요청사항/메모]를 바탕으로, "
        "독자들이 읽기 편하도록 여러 개의 명확한 단락과 깔끔한 소제목(반드시 ### 소제목 형태)을 포함하여 풍성하고 상세한 SEO 최적화 뉴스 기사 본문을 작성해 주세요. "
        "마크다운 특수기호(-, *, _)는 절대 사용하지 말고 오직 자연스러운 문장과 ### 소제목만 사용해 주세요. "
        "마지막 줄에는 반드시 검색에 유용한 해시태그 5개를 #인공지능 #테크 형태로 공백을 두고 포함해 주세요."
    )
    
    full_query = f"{system_directive}\n\n[기사 제목]: {clean_title}\n[작성 요청사항/메모]: {prompt}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_query,
        )
        final_content = response.text.strip()
    except Exception as e:
        final_content = prompt

    img_url, author_name = fetch_bulletproof_image(category)
    final_content = clean_and_format_content(final_content, category)

    save_article_to_db(category, clean_title, final_content, img_url, author_name)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.get("/admin/edit/{article_id}", response_class=HTMLResponse)
def edit_page(article_id: int, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)

    art = get_article_by_id(article_id)
    if not art:
        return RedirectResponse(url="/admin/studio", status_code=303)

    current_img = art.get('image_url', '')

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
            .img-btn-group {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }}
            .img-btn {{ background: #e67e22; color: white; border: none; padding: 8px 14px; font-size: 13px; border-radius: 4px; cursor: pointer; font-weight: bold; display: inline-block; }}
            .img-btn:hover {{ background: #d35400; }}
            .file-input {{ display: none; }}
        </style>
    </head>
    <body>
        <a href="/admin/studio" class="back-link">← 관리자 스튜디오로 돌아가기</a>
        <div class="box">
            <h1>✏️ 기사 및 이미지 수정하기</h1>
            <form action="/admin/update/{art['id']}" method="post">
                <label>카테고리</label>
                <select name="category">
                    <option value="AI/테크" {"selected" if art['category']=="AI/테크" else ""}>AI/테크</option>
                    <option value="경제/주식" {"selected" if art['category']=="경제/주식" else ""}>경제/주식</option>
                    <option value="세상이야기" {"selected" if art['category']=="세상이야기" else ""}>세상이야기</option>
                    <option value="시니어/복지" {"selected" if art['category']=="시니어/복지" else ""}>시니어/복지</option>
                    <option value="연예계뉴스" {"selected" if art['category']=="연예계뉴스" else ""}>연예계뉴스</option>
                    <option value="스포츠" {"selected" if art['category']=="스포츠" else ""}>스포츠</option>
                </select>
                
                <label>기사 제목</label>
                <input type="text" name="title" value="{art['title']}" required>
                
                <label>이미지 주소 (URL)</label>
                <input type="text" name="image_url" value="{current_img}" placeholder="새로운 이미지 주소(URL)를 입력하세요">
                <small style="color: #7f8c8d; display: block; margin-top: -10px; margin-bottom: 15px;">현재 등록된 이미지 미리보기:</small>
                <img src="{current_img}" class="preview-img" onerror="this.style.display='none'">

                <label>기사 내용</label>
                
                <div class="img-btn-group">
                    <button type="button" class="img-btn" onclick="insertImageByUrl('editContent')">🌐 웹 주소(URL)로 이미지 넣기</button>
                    <button type="button" class="img-btn" style="background: #16a085;" onclick="document.getElementById('editFile').click()">📁 내 기기 파일(JPEG/PNG) 바로 올리기</button>
                    <input type="file" id="editFile" class="file-input" accept="image/*" onchange="uploadImageFile(this, 'editContent')">
                </div>

                <textarea name="content" id="editContent" required>{art['content']}</textarea>
                
                <button type="submit">💾 수정 사항 저장하기</button>
            </form>
        </div>

        <script>
        function insertImageByUrl(elementId) {{
            const url = prompt("넣을 이미지의 웹 주소(URL)를 입력하세요:");
            if (url) {{
                const tag = '\\n<img src="' + url.trim() + '" style="width: 100%; border-radius: 8px; margin: 20px 0;">\\n';
                const textarea = document.getElementById(elementId);
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
                textarea.focus();
            }}
        }}

        async function uploadImageFile(input, elementId) {{
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
                        const tag = '\\n<img src="' + data.url + '" style="width: 100%; border-radius: 8px; margin: 20px 0;">\\n';
                        const textarea = document.getElementById(elementId);
                        const start = textarea.selectionStart;
                        const end = textarea.selectionEnd;
                        textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
                        textarea.focus();
                        alert("사진이 성공적으로 업로드되어 커서 위치에 삽입되었습니다!");
                    }} else {{
                        alert("업로드 실패: " + (data.error || "알 수 없는 오류"));
                    }}
                }} catch (err) {{
                    alert("사진 업로드 중 오류가 발생했습니다: " + err);
                }}
                input.value = "";
            }}
        }}
        </script>
    </body>
    </html>
    """

@app.post("/admin/update/{article_id}")
def update_article(article_id: int, category: str = Form(...), title: str = Form(...), content: str = Form(...), image_url: str = Form(None), admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    clean_title = title.replace('**', '').replace('*', '').strip()
    update_article_in_db(article_id, category, clean_title, content, image_url)
    return RedirectResponse(url="/admin/studio", status_code=303)

@app.get("/admin/delete/{article_id}")
def delete_article(article_id: int, admin_auth: str = Cookie(None)):
    if admin_auth != "authenticated":
        return RedirectResponse(url="/admin", status_code=303)
    delete_article_from_db(article_id)
    return RedirectResponse(url="/admin/studio", status_code=303)
