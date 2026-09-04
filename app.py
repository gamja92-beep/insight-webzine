import sys
import os
import sqlite3
import random
import time
import requests
import re
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google import genai
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

API_KEY = os.environ.get("API_KEY", "")
MODEL_NAME = "gemini-3.5-flash"

# Unsplash API 키
UNSPLASH_ACCESS_KEY = "14W3nppcnrDp-1qJbpqzxERefLjS25QFZIZ27uYEhhA"

client = genai.Client(api_key=API_KEY)

def init_db():
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

# 🌟 [괴물 컷 100% 차단] 순수 와이드 풍경/사물/경기장/도시 전용 풀
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

# 🌟 [최종 완성 정제 함수]
def clean_and_format_content(text, category_name="종합"):
    text = text.replace('**', '').replace('__', '')
    
    lines_cleaned = []
    for line in text.split('\n'):
        stripped = line.strip()
        if re.match(r'^[\*\-\_\#\s]+$', stripped):
            continue
        lines_cleaned.append(line)
    text = '\n'.join(lines_cleaned)

    text_for_tags = re.sub(r'###+', '', text)
    all_words = text_for_tags.split()
    hashtags = [w for w in all_words if w.startswith('#') and len(w) > 1 and not w.startswith('#2c')]
    
    for tag in hashtags:
        text = text.replace(tag, '')
        
    processed_lines = []
    for line in text.split('\n'):
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.startswith('###'):
            title_text = line_str.replace('###', '').strip()
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 35px; margin-bottom: 14px; font-size: 1.2em; font-weight: 800; letter-spacing: -0.5px;">{title_text}</h3>')
        elif len(line_str) < 42 and not line_str.endswith(('.', '?', '!')) and not line_str.startswith('<'):
            processed_lines.append(f'<h3 style="color: #1b4f72; border-left: 5px solid #2980b9; padding-left: 12px; margin-top: 35px; margin-bottom: 14px; font-size: 1.2em; font-weight: 800; letter-spacing: -0.5px;">{line_str}</h3>')
        else:
            processed_lines.append(f'<p style="margin-bottom: 16px; text-align: justify; word-break: keep-all; line-height: 1.8;">{line_str}</p>')
            
    final_html = "".join(processed_lines)
    
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
    tag_html = f"<div style='margin-top: 35px; padding-top: 15px; border-top: 1px solid #eaecee; color: #2980b9; font-weight: bold; font-size: 0.9em; word-spacing: 5px;'>{clean_tags_str}</div>"
    final_html += tag_html

    return final_html

# 🌟 [한국 시간(KST) 및 영구 저장]
def save_article_to_db(category, title, content, image_url, image_author):
    kst = timezone(timedelta(hours=9))
    current_time_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO articles (category, title, content, image_url, image_author, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
        (category, title, content, image_url, image_author, current_time_str)
    )
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

# 🌟 [메인 홈 및 상세 보기 / 미디어 스타일 그리드 홈페이지]
@app.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = None, view: int = None):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    
    # 특정 기사 상세 보기 모드인 경우
    if view:
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE id = ?", (view,))
        art = cursor.fetchone()
        conn.close()
        if not art:
            return RedirectResponse(url="/", status_code=303)
        
        detail_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <title>{art[2]} - 인사이트 종합 웹진</title>
            <style>
                body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 40px auto; padding: 30px; background: #f8f9fa; color: #2c3e50; line-height: 1.8; }}
                .back-btn {{ display: inline-block; padding: 10px 20px; background: #2980b9; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; margin-bottom: 25px; transition: 0.2s; }}
                .back-btn:hover {{ background: #1f618d; }}
                .article-container {{ background: white; padding: 45px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }}
                .badge {{ display: inline-block; padding: 5px 14px; background: #ebf5fb; color: #2980b9; border-radius: 4px; font-size: 0.9em; font-weight: bold; margin-bottom: 12px; }}
                h1 {{ font-size: 2.1em; color: #1a252f; margin-top: 10px; margin-bottom: 15px; line-height: 1.35; }}
                .date {{ font-size: 0.9em; color: #7f8c8d; margin-bottom: 25px; border-bottom: 1px solid #eaecee; padding-bottom: 15px; }}
                .article-img {{ width: 100%; max-height: 480px; object-fit: cover; border-radius: 8px; margin-bottom: 10px; }}
                .img-source {{ font-size: 0.85em; color: #95a5a6; margin-bottom: 30px; font-style: italic; }}
                .content {{ font-size: 1.12em; color: #34495e; }}
            </style>
        </head>
        <body>
            <a href="/" class="back-btn">← 메인 뉴스로 돌아가기</a>
            <div class="article-container">
                <span class="badge">{art[1]}</span>
                <h1>{art[2]}</h1>
                <div class="date">발행일시: {art[6]}</div>
                <img src="{art[4]}" class="article-img">
                <div class="img-source">📷 Photo by {art[5]} / Unsplash</div>
                <div class="content">{art[3]}</div>
            </div>
        </body>
        </html>
        """
        return detail_html

    # 메인 뉴스 그리드 리스트 모드
    if category and category != "전체":
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles WHERE category = ? ORDER BY id DESC", (category,))
    else:
        cursor.execute("SELECT id, category, title, content, image_url, image_author, created_at FROM articles ORDER BY id DESC")
        
    rows = cursor.fetchall()
    conn.close()

    articles = [{
        "id": r[0], "category": r[1], "title": r[2], "content": r[3], 
        "image_url": r[4], "image_author": r[5], "created_at": r[6]
    } for r in rows]
    
    categories = ["전체", "AI/테크", "경제/주식", "세상이야기", "시니어/복지", "연예계뉴스", "스포츠"]

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>인사이트 종합 웹진 - 프리미엄 미디어</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 1100px; margin: 30px auto; padding: 20px; background: #f0f3f4; color: #333; }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 4px solid #1b4f72; padding-bottom: 20px; background: white; padding: 25px 30px; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.05); }}
            h1 {{ color: #1a252f; margin: 0; font-size: 1.8em; letter-spacing: -0.5px; }}
            .admin-link {{ display: inline-block; padding: 9px 18px; background: #1b4f72; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px; transition: 0.2s; }}
            .admin-link:hover {{ background: #12334a; }}
            
            .nav-tabs {{ display: flex; gap: 8px; margin: 25px 0; flex-wrap: wrap; background: white; padding: 15px 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }}
            .tab-item {{ padding: 8px 16px; background: #ecf0f1; color: #555; text-decoration: none; border-radius: 20px; font-weight: bold; font-size: 14px; transition: 0.2s; }}
            .tab-item:hover, .tab-item.active {{ background: #1b4f72; color: white; }}

            /* 🌟 방송/신문사 스타일 그리드 카드 레이아웃 */
            .news-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 25px; margin-top: 20px; }}
            .news-card {{ background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); transition: transform 0.2s, box-shadow 0.2s; display: flex; flex-direction: column; position: relative; }}
            .news-card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); }}
            
            .card-img-wrap {{ width: 100%; height: 200px; overflow: hidden; background: #ddd; }}
            .card-img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }}
            .news-card:hover .card-img {{ transform: scale(1.03); }}
            
            .card-body {{ padding: 20px; display: flex; flex-direction: column; flex-grow: 1; }}
            .badge {{ display: inline-block; padding: 3px 10px; background: #ebf5fb; color: #2980b9; border-radius: 4px; font-size: 0.78em; font-weight: bold; margin-bottom: 10px; width: fit-content; }}
            .card-title {{ font-size: 1.25em; color: #2c3e50; margin: 0 0 10px 0; line-height: 1.4; font-weight: 700; }}
            .card-title a {{ color: inherit; text-decoration: none; }}
            .card-title a:hover {{ color: #2980b9; }}
            
            .card-date {{ font-size: 0.8em; color: #95a5a6; margin-top: auto; padding-top: 15px; border-top: 1px solid #f1f2f6; }}
            
            .btn-group {{ position: absolute; top: 15px; right: 15px; display: flex; gap: 5px; background: rgba(255,255,255,0.9); padding: 4px 8px; border-radius: 6px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .edit-btn {{ color: #d68910; text-decoration: none; font-size: 12px; font-weight: bold; }}
            .delete-btn {{ color: #c0392b; text-decoration: none; font-size: 12px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header-flex">
            <h1>📰 인사이트 종합 미디어 (24시 프리미엄 웹진)</h1>
            <a href="/admin" class="admin-link">⚙️ 관리자 스튜디오</a>
        </div>

        <div class="nav-tabs">
    """
    
    for cat in categories:
        active_class = "active" if (not category and cat == "전체") or (category == cat) else ""
        cat_param = "" if cat == "전체" else f"?category={cat}"
        html += f'<a href="/{cat_param}" class="tab-item {active_class}">{cat}</a>'
        
    html += "</div>"

    if not articles:
        html += "<p style='text-align:center; color:#777; margin-top:80px; font-size: 1.1em;'>등록된 기사가 없습니다. 관리자 페이지에서 뉴스를 발행해 보세요!</p>"
    else:
        html += '<div class="news-grid">'
        for art in articles:
            cat_name = art['category'] if art['category'] else '종합'
            img_url = art['image_url'] if art['image_url'] else "https://images.unsplash.com/photo-1451187580459-43490279c0fa"
            
            html += f"""
            <div class="news-card">
                <div class="btn-group">
                    <a href="/admin/edit/{art['id']}" class="edit-btn">✏️수정</a>
                    <a href="/admin/delete/{art['id']}" class="delete-btn" onclick="return confirm('정말 이 기사를 삭제하시겠습니까?');">🗑️삭제</a>
                </div>
                <div class="card-img-wrap">
                    <a href="/?view={art['id']}"><img src="{img_url}" class="card-img"></a>
                </div>
                <div class="card-body">
                    <span class="badge">{cat_name}</span>
                    <h3 class="card-title"><a href="/?view={art['id']}">{art['title']}</a></h3>
                    <div class="card-date">발행 | {art['created_at']}</div>
                </div>
            </div>
            """
        html += "</div>"
        
    html += "</body></html>"
    return html

# 관리자 페이지
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>인사이트 웹진 관리자</title>
        <style>
            body { font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f4f6f7; }
            h1 { color: #2c3e50; }
            .box { background: white; padding: 25px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            button { background: #27ae60; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }
            button:hover { background: #219653; }
            .manual-btn { background: #2980b9; }
            .manual-btn:hover { background: #1f618d; }
            .ai-expand-btn { background: #8e44ad; }
            .ai-expand-btn:hover { background: #732d91; }
            input[type="text"], select, textarea { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }
            textarea { height: 150px; resize: vertical; }
            label { font-weight: bold; color: #34495e; display: block; margin-top: 10px; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <h1>⚙️ 웹진 관리자 스튜디오</h1>
        
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
                <textarea name="content" placeholder="내용을 직접 작성하세요..." required></textarea>
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
                <textarea name="prompt" placeholder="예: AI 거품론과 인프라 투자 포인트에 대해 전문적인 분석 기사로 상세히 작성해줘." required></textarea>
                <button type="submit" class="ai-expand-btn">🪄 명품 신문 스타일 기사 발행하기</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/create-auto")
def create_auto(category: str = Form(...)):
    generate_ai_article(category)
    return RedirectResponse(url="/", status_code=303)

@app.post("/admin/create-manual")
def create_manual(category: str = Form(...), title: str = Form(...), content: str = Form(...)):
    clean_title = title.replace('**', '').replace('*', '').strip()
    img_url, author_name = fetch_bulletproof_image(category)
    
    formatted_content = "".join([f"<p style='margin-bottom: 16px; text-align: justify;'>{p}</p>" for p in content.split('\n') if p.strip()])

    save_article_to_db(category, clean_title, formatted_content, img_url, author_name)
    return RedirectResponse(url="/", status_code=303)

@app.post("/admin/create-ai-expand")
def create_ai_expand(category: str = Form(...), title: str = Form(...), prompt: str = Form(...)):
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
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/edit/{article_id}", response_class=HTMLResponse)
def edit_page(article_id: int):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, title, content FROM articles WHERE id = ?", (article_id,))
    art = cursor.fetchone()
    conn.close()

    if not art:
        return RedirectResponse(url="/", status_code=303)

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>기사 수정하기</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f4f6f7; }}
            h1 {{ color: #2c3e50; }}
            .box {{ background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            button {{ background: #f39c12; color: white; border: none; padding: 12px 20px; font-size: 16px; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; }}
            button:hover {{ background: #d68910; }}
            input[type="text"], select, textarea {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 15px; }}
            textarea {{ height: 250px; resize: vertical; }}
            label {{ font-weight: bold; color: #34495e; display: block; margin-top: 10px; }}
            .back-link {{ display: inline-block; margin-bottom: 15px; color: #3498db; text-decoration: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← 메인 페이지로 돌아가기</a>
        <div class="box">
            <h1>✏️ 기사 수정하기</h1>
            <form action="/admin/update/{art[0]}" method="post">
                <label>카테고리</label>
                <select name="category">
                    <option value="AI/테크" {"selected" if art[1]=="AI/테크" else ""}>AI/테크</option>
                    <option value="경제/주식" {"selected" if art[1]=="경제/주식" else ""}>경제/주식</option>
                    <option value="세상이야기" {"selected" if art[1]=="세상이야기" else ""}>세상이야기</option>
                    <option value="시니어/복지" {"selected" if art[1]=="시니어/복지" else ""}>시니어/복지</option>
                    <option value="연예계뉴스" {"selected" if art[1]=="연예계뉴스" else ""}>연예계뉴스</option>
                    <option value="스포츠" {"selected" if art[1]=="스포츠" else ""}>스포츠</option>
                </select>
                <label>기사 제목</label>
                <input type="text" name="title" value="{art[2]}" required>
                <label>기사 내용</label>
                <textarea name="content" required>{art[3]}</textarea>
                <button type="submit">💾 수정 사항 저장하기</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/admin/update/{article_id}")
def update_article(article_id: int, category: str = Form(...), title: str = Form(...), content: str = Form(...)):
    clean_title = title.replace('**', '').replace('*', '').strip()
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE articles SET category = ?, title = ?, content = ? WHERE id = ?", (category, clean_title, content, article_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/delete/{article_id}")
def delete_article(article_id: int):
    conn = sqlite3.connect("database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)
