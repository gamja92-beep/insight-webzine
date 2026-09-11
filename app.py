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
flask_app.secret_key = "sisatoday_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "webzine.db")

# 9대 정규 카테고리와 영문 slug 매핑
CATEGORIES = [
    ("정치/시사", "politics"),
    ("경제/주식", "economy"),
    ("세상이야기", "society"),
    ("AI/테크", "tech"),
    ("건강/복지", "welfare"),
    ("생활정보", "life"),
    ("연예뉴스", "entertainment"),
    ("스포츠", "sports"),
    ("지역창", "local")
]

CATEGORY_MAP = dict(CATEGORIES)
SLUG_MAP = {v: k for k, v in CATEGORIES}

CATEGORY_COLORS = {
    "정치/시사": ("#0f2027", "#203a43"),
    "경제/주식": ("#134e5e", "#71b280"),
    "세상이야기": ("#2c3e50", "#4ca1af"),
    "AI/테크": ("#141e30", "#243b55"),
    "건강/복지": ("#1d976c", "#93f9b9"),
    "생활정보": ("#3a6073", "#3a7bd5"),
    "연예뉴스": ("#4b134f", "#c94b4b"),
    "스포츠": ("#16222f", "#3a6073"),
    "지역창": ("#1e3c72", "#2a5298")
}

# 40여 편 완성형 마스터 아카이브 (cat_slug 포함)
MASTER_ARTICLES = [
    # 1. 정치/시사
    ("정치/시사", "politics", "신산업 규제 혁신과 사회적 안전망 구축의 상생 해법", "글로벌 기술 경쟁 시대, 신성장 동력 확보와 국민 안전을 위한 입법적 과제를 진단합니다.",
     "<h3>1. 현안 배경</h3><p>글로벌 기술 패권 경쟁이 격화되면서 신산업 규제 샌드박스 완화와 국민 안전망 구축 사이의 전략적 균형이 국회 입법의 핵심 화두로 떠올랐습니다.</p><h3>2. 핵심 쟁점</h3><p>산업계는 과감한 규제 완화를 요구하는 반면 시민사회는 사전 검증과 부작용 방지 장치가 선행되어야 한다고 맞서고 있습니다.</p><h3>3. 향후 전망</h3><p>국회 상임위 중심의 후속 법안 논의 과정에서 실효성 있는 대안이 도출될지 주목됩니다.</p>"),
    ("정치/시사", "politics", "국민연금 모수개혁과 구조개혁을 둘러싼 여야의 쟁점 총정리", "지속 가능한 노후 복지를 위한 보험료율 및 소득대체율 조정 합의점을 심층 분석합니다.",
     "<h3>1. 개혁 배경</h3><p>기금 소진 시기가 앞당겨질 것이라는 우려 속에 세대 간 형평성과 노후 소득 보장의 지속가능성을 담보할 제도 개혁이 시급해졌습니다.</p>"),
    ("정치/시사", "politics", "지방소멸 대응 특별법 실효성 논란과 지역 거점 육성 전략", "지방 소멸 위험도가 역대 최고치를 기록하는 가운데 균형발전을 위한 국가적 지원책을 점검합니다.",
     "<h3>1. 현장 르포</h3><p>청년 인구 유출을 막고 지역 자립 기반을 마련하기 위한 특화 산업 육성 및 정주 여건 개선이 시급합니다.</p>"),
    ("정치/시사", "politics", "인공지능(AI) 기본법 제정과 저작물 권익 보호 가이드라인", "생성형 AI의 급성장에 따른 데이터 학습 투명성과 창작자 권리 보호 방안입니다.",
     "<h3>1. 입법 현황</h3><p>국내외 빅테크와 창작자 간의 저작권 갈등을 합리적으로 중재하기 위한 법적 가이드라인 마련이 초읽기에 들어갔습니다.</p>"),

    # 2. 경제/주식
    ("경제/주식", "economy", "1세대 1주택 비과세 요건 및 시니어 부동산 합법적 절세 체크리스트", "고령층 자산의 큰 비중을 차지하는 주택 양도세와 보유세 경감 실전 가이드입니다.",
     "<h3>1. 양도세 비과세 요건</h3><p>보유 기간과 실제 거주 기간의 충족 여부를 확인하고, 상생임대주택 특례 활용 여부를 꼼꼼히 점검해야 합니다.</p><h3>2. 증여와 상속</h3><p>사전 증여 시 10년 주기 공제 한도를 활용하고, 고령자 세액공제를 최대한 확보하는 것이 유리합니다.</p>"),
    ("경제/주식", "economy", "글로벌 금리 인하 기조와 원·달러 환율 변동에 따른 자산 배분 전략", "환율 및 물가 불확실성 속에서 안정적인 배당 수익과 채권 비중을 높이는 투자법입니다.",
     "<h3>1. 거시경제 진단</h3><p>미 연준의 기준금리 행보에 따른 국내 금융시장의 파급 효과를 분석하고 가계 자산 방어책을 수립해야 합니다.</p>"),
    ("경제/주식", "economy", "자본시장 밸류업 정책과 고배당 가치주의 새로운 투자 기회", "기업 지배구조 개선 및 주주 환원 확대 정책이 증시에 미치는 중장기적 파장입니다.",
     "<h3>1. 투자 포인트</h3><p>배당소득 분리과세 추진과 자사주 소각 유도 정책이 우량 가치주의 재평가 계기가 되고 있습니다.</p>"),
    ("경제/주식", "economy", "도심 상가 공실 해소와 시니어 케어 복합시설 전환 사업성", "상권 침체 속에서 도심 상업시설을 시니어 주거 및 복지 공간으로 재편하는 신수익 모델입니다.",
     "<h3>1. 시장 트렌드</h3><p>의료 연계형 실버 시설과 맞춤형 임대 서비스가 결합된 신개념 공간 비즈니스가 부상하고 있습니다.</p>"),

    # 3. 건강/복지
    ("건강/복지", "welfare", "2026년 기초연금 수급 자격 선정기준액 및 감액 없는 신청 요령", "어르신들의 노후 기본소득인 기초연금의 변동 기준과 수급 혜택을 상세히 알아봅니다.",
     "<h3>1. 선정기준액 계산</h3><p>단독가구 및 부부가구의 소득인정액 계산 시 공제되는 기본재산액과 금융소득 평가 기준을 확인하세요.</p><h3>2. 감액 방지 팁</h3><p>국민연금 연계 감액 및 부부 동시 수급 감액 규정을 사전에 파악하여 불이익을 최소화해야 합니다.</p>"),
    ("건강/복지", "welfare", "혈관 나이를 10년 젊게 만드는 아침 식습관과 필수 항산화 식단", "중장년층 뇌심혈관 질환 예방을 위한 과학적인 식단 구성과 기상 후 루틴입니다.",
     "<h3>1. 아침 첫 식사의 원칙</h3><p>미온수 섭취로 혈액 점도를 낮추고 정제 탄수화물 대신 단백질과 식이섬유 중심의 식단이 필수적입니다.</p>"),
    ("건강/복지", "welfare", "노인장기요양보험 1~5등급 판정 기준과 재가급여 200% 활용 팁", "가족 간병 부담을 덜어주는 장기요양보험의 혜택과 공단 방문 조사 대비법입니다.",
     "<h3>1. 등급 판정 요령</h3><p>의사소견서 발급과 조사원의 현장 실사 시 일상생활 수행 능력(ADL)을 명확하게 전달해야 합니다.</p>"),
    ("건강/복지", "welfare", "치매 조기 발견을 위한 인지선별검사(CIST)와 지역 안심센터 이용법", "보건소 치매안심센터를 통한 무료 조기 검진과 체계적인 예방 관리 서비스입니다.",
     "<h3>1. 조기 진단의 중요성</h3><p>단순 건망증과 경도인지장애를 정확히 구분하고 조기에 맞춤형 인지 훈련을 시작하는 것이 핵심입니다.</p>"),

    # 4. 세상이야기
    ("세상이야기", "society", "국내 힐링 명소 가이드 및 시니어를 위한 문화누리카드 알찬 활용법", "정부 지원 문화누리카드를 100% 누릴 수 있는 전국 문화·관광 여행 코스입니다.",
     "<h3>1. 혜택 활용</h3><p>철도 코레일 할인, 국립자연휴양림, 온천 및 숙박 시설에서 연간 지원금을 알차게 사용할 수 있습니다.</p>"),
    ("세상이야기", "society", "팬덤이 이끄는 나눔과 선한 영향력: 대중문화 기부 생태계의 진화", "단순한 스타 응원을 넘어 지역사회와 취약계층에 온기를 전하는 성숙한 팬덤 문화입니다.",
     "<h3>1. 문화적 파급</h3><p>콘서트 기념 화환 대신 쌀과 연탄을 기부하며 사회적 연대를 실천하는 아름다운 풍경이 자리잡고 있습니다.</p>"),
    ("세상이야기", "society", "초고령사회 마을공동체 회복과 은퇴자 재능나눔 우수 사례", "마을 도서관 지킴이, 숲 해설사로 인생 2막을 당당하게 열어가는 액티브 시니어의 일상입니다.",
     "<h3>1. 현장 목소리</h3><p>평생 쌓아온 전문 지식을 이웃과 청소년에게 나누며 삶의 활력과 자긍심을 되찾고 있습니다.</p>"),
    ("세상이야기", "society", "AI 딥페이크 사칭 금융사기 예방 백서: 부모님 자산 지키기", "가족의 목소리와 얼굴을 복제해 금전을 요구하는 신종 사기 수법과 철저한 차단법입니다.",
     "<h3>1. 대처 수칙</h3><p>금전 요구 시 반드시 별도 번호로 통화하고 개인정보 및 원격 제어 앱 설치를 일체 거부해야 합니다.</p>"),

    # 5. AI/테크
    ("AI/테크", "tech", "중장년층을 위한 실전 스마트폰 음성 비서 100% 활용기", "복잡한 자판 입력 없이 목소리 하나로 일정 관리, 병원 길 찾기, 사진 검색을 끝내는 방법입니다.",
     "<h3>1. 실전 음성 명령</h3><p>'내일 아침 9시 알람 맞춰줘', '가장 가까운 내과 병원 찾아줘' 등 일상 밀착형 명령어를 익혀보세요.</p>"),
    ("AI/테크", "tech", "자율주행 대중교통 도입과 교통 취약계층 이동권 혁신", "지방 소도시와 농어촌 지역의 수요응답형 셔틀(DRT)이 가져온 편리한 일상 변화입니다.",
     "<h3>1. 교통 복지의 미래</h3><p>병원과 장터까지 문앞으로 찾아오는 친환경 스마트 모빌리티가 어르신들의 든든한 발이 되어줍니다.</p>"),
    ("AI/테크", "tech", "웨어러블 헬스케어 기기: 손목시계 하나로 부정맥과 고혈압 잡는다", "실시간 생체 신호 모니터링을 통해 심장 마비와 뇌졸중의 전조 증상을 감지하는 기술입니다.",
     "<h3>1. 스마트 건강 관리</h3><p>이상 징후 발생 시 지정된 보호자나 119에 긴급 알림이 전송되어 골든타임을 확보합니다.</p>"),

    # 6. 생활정보
    ("생활정보", "life", "2026년 K-패스 대중교통비 환급 확대와 시니어 무임교통 총정리", "전국 지하철과 시내버스 이용 시 교통비를 최대 53%까지 환급받는 절약 팁입니다.",
     "<h3>1. 환급 혜택</h3><p>월 15회 이상 대중교통 이용 시 적립되며 신용카드 청구 할인과 연계하여 혜택을 극대화할 수 있습니다.</p>"),
    ("생활정보", "life", "난방비 반값으로 줄이는 실내 보일러 온도 조절기 세팅 비법", "온돌 모드와 실내 모드의 정확한 차이를 알고 효율적인 보온을 유지하는 겨울철 상식입니다.",
     "<h3>1. 효율적인 사용법</h3><p>외출 시 보일러를 끄지 말고 외출 모드 또는 현재 온도보다 2~3도 낮추는 것이 가스비를 아낍니다.</p>"),
    ("생활정보", "life", "노후 주택 단열 및 친환경 보일러 정부 지원금 신청 가이드", "그린리모델링 사업을 통해 샷시 교체와 보일러 교체 비용을 지원받는 방법입니다.",
     "<h3>1. 지원 절차</h3><p>지자체별 선착순 예산을 확인하고 등록 업체를 통해 서류 대행을 진행하면 편리합니다.</p>"),

    # 7. 연예뉴스
    ("연예뉴스", "entertainment", "가요무대와 7080 콘서트 열풍: 중장년이 주도하는 라이브 공연 시장", "추억의 명곡들이 현대적인 오케스트라 편곡과 함께 관객들에게 벅찬 감동을 선사합니다.",
     "<h3>1. 현장 열기</h3><p>세대를 아우르는 음악과 따뜻한 무대 매너가 관객들의 마음을 치유하며 공연계의 큰 축으로 자리잡았습니다.</p>"),

    # 8. 스포츠
    ("스포츠", "sports", "시니어 파크골프 입문 가이드: 부상 없는 스윙 자세와 전국 명품 구장", "관절에 무리 없이 잔디 위를 걸으며 친목을 다지는 최고의 국민 생활체육입니다.",
     "<h3>1. 스윙 팁</h3><p>상체 힘을 빼고 골반 회전을 이용해 부드럽게 밀어치는 정석 자세를 유지하는 것이 부상을 막습니다.</p>"),
    ("스포츠", "sports", "인터벌 걷기 운동법: 3분 빠르게 3분 천천히가 가져온 혈당 변화", "일반 산책 대비 심폐지구력과 하체 근력을 2배 이상 키워주는 과학적 보행 요령입니다.",
     "<h3>1. 올바른 보행법</h3><p>시선은 15미터 전방을 응시하고 턱을 당기며 뒤꿈치부터 발바닥 전체로 착지하는 것이 좋습니다.</p>"),

    # 9. 지역창
    ("지역창", "local", "동해안 무장애 해안 힐링길: 속초 영랑호 둘레길과 외옹치 바다향기로", "푸른 동해 바다와 설악산의 비경을 감상하며 편안하게 걸을 수 있는 무장애 데크로드입니다.",
     "<h3>1. 추천 코스</h3><p>휠체어나 유모차도 편안히 통행 가능한 완만한 경사로로 조성되어 온 가족 산책 코스로 각광받고 있습니다.</p>"),
    ("지역창", "local", "강원 영동권 산림 복원과 주민 참여형 청정 숲 가꾸기 현주소", "산불 피해지를 주민들의 땀과 정성으로 치유하고 밀원수를 심어 푸른 숲을 일구는 현장입니다.",
     "<h3>1. 미래를 위한 숲</h3><p>지역 특화 수종 식재와 산림 감시 체계 구축을 통해 안전하고 아름다운 자연유산을 지켜나갑니다.</p>")
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 원본 규격의 테이블 생성 (cat_slug 포함)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            cat_slug TEXT DEFAULT '',
            title TEXT,
            lead_text TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            content TEXT,
            image_url TEXT DEFAULT '',
            source_link TEXT DEFAULT '',
            created_at TEXT
        )
    """)
    conn.commit()

    # 2. 기존 테이블 컬럼 점검
    cur.execute("PRAGMA table_info(articles)")
    cols = [r['name'] for r in cur.fetchall()]
    for col in ['cat_slug', 'lead_text', 'summary', 'image_url', 'source_link']:
        if col not in cols:
            try:
                cur.execute(f"ALTER TABLE articles ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass
    conn.commit()

    # 3. 기사가 비어있을 경우 원본 규격으로 40여 편 자동 복구
    cur.execute("SELECT COUNT(*) as cnt FROM articles")
    cnt = cur.fetchone()['cnt']
    if cnt < 10:
        base_time = datetime.datetime.now()
        for i, item in enumerate(MASTER_ARTICLES):
            t_str = (base_time - datetime.timedelta(hours=i*2)).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO articles (category, cat_slug, title, lead_text, summary, content, image_url, source_link, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (item[0], item[1], item[2], item[3], item[3], item[4], "", "", t_str))
        conn.commit()
    conn.close()

init_db()


# ==========================================
# 사용자 화면 (오늘 아침 모던 카드 그리드 UI)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>시사투데이 창 - 정론 심층 분석 웹진</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Pretendard", sans-serif; background-color: #f4f6f9; color: #222; }
        
        .header { background: #fff; border-bottom: 2px solid #002d5b; padding: 18px 28px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 26px; font-weight: 900; color: #002d5b; text-decoration: none; }
        .logo span { background: #002d5b; color: #fff; padding: 2px 8px; border-radius: 4px; margin-left: 6px; }
        .btn-admin { background: #2c3e50; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: bold; }

        .nav-bar { background: #fff; padding: 12px 28px; display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid #e0e4e9; }
        .nav-item { padding: 8px 16px; text-decoration: none; font-size: 13px; font-weight: bold; border-radius: 20px; color: #4b5563; background: #eef2f6; white-space: nowrap; }
        .nav-item:hover { background: #dde3eb; }
        .nav-item.active { background: #002d5b; color: #fff; }

        .container { max-width: 1200px; margin: 26px auto; padding: 0 16px; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; margin-bottom: 40px; }
        
        .card-link { text-decoration: none; color: inherit; display: block; }
        .card { background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 3px 10px rgba(0,0,0,0.06); display: flex; flex-direction: column; height: 100%; border: 1px solid #e9edf2; transition: transform 0.2s; }
        .card:hover { transform: translateY(-4px); }
        
        .card-visual { width: 100%; height: 180px; display: flex; flex-direction: column; justify-content: space-between; padding: 20px; color: #fff; }
        .card-visual .badge { align-self: flex-start; background: rgba(0,0,0,0.35); padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .card-visual .hl-text { font-size: 17px; font-weight: 800; line-height: 1.4; }

        .card-body { padding: 20px; flex: 1; display: flex; flex-direction: column; }
        .cat-tag { align-self: flex-start; background: #e0f2fe; color: #0284c7; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px; margin-bottom: 10px; }
        .card-title { font-size: 16px; font-weight: 700; line-height: 1.5; color: #111; margin-bottom: 10px; word-break: keep-all; }
        .card-lead { font-size: 13px; color: #666; line-height: 1.6; margin-bottom: 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .card-date { font-size: 12px; color: #999; margin-top: auto; }

        .detail-box { background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 3px 10px rgba(0,0,0,0.06); border: 1px solid #e9edf2; }
        .detail-cat { display: inline-block; background: #e0f2fe; color: #0284c7; font-weight: bold; font-size: 13px; padding: 4px 12px; border-radius: 4px; }
        .detail-title { font-size: 28px; font-weight: 800; margin: 16px 0; line-height: 1.4; word-break: keep-all; }
        .detail-date { font-size: 13px; color: #666; border-bottom: 1px solid #eee; padding-bottom: 16px; margin-bottom: 24px; }
        .article-lead { background: #f8fafc; padding: 18px; border-radius: 8px; border-left: 4px solid #0284c7; font-size: 16px; line-height: 1.7; margin-bottom: 24px; }
        .detail-content h3 { font-size: 19px; margin: 26px 0 12px 0; color: #002d5b; border-left: 4px solid #002d5b; padding-left: 10px; }
        .detail-content p { font-size: 16px; line-height: 1.85; color: #333; margin-bottom: 16px; word-break: keep-all; }
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">시사투데이<span>창</span></a>
        <a href="/admin" class="btn-admin">⚙️ 관리자 홈</a>
    </header>

    <nav class="nav-bar">
        <a href="/" class="nav-item {% if not current_cat %}active{% endif %}">전체 기사 ({{ total_count }})</a>
        {% for cat_name, cat_slug in nav_categories %}
        <a href="/?cat={{ cat_name }}" class="nav-item {% if current_cat == cat_name or current_cat == cat_slug %}active{% endif %}">{{ cat_name }}</a>
        {% endfor %}
    </nav>

    <main class="container">
        {% if is_detail %}
            <article class="detail-box">
                <span class="detail-cat">{{ article['category'] }}</span>
                <h1 class="detail-title">{{ article['title'] }}</h1>
                <div class="detail-date">발행일시: {{ article['created_at'] }} | 시사투데이 특별취재팀</div>
                
                {% if article['lead_text'] or article['summary'] %}
                    <div class="article-lead"><b>[핵심 개요]</b> {{ article['lead_text'] if article['lead_text'] else article['summary'] }}</div>
                {% endif %}

                <div class="detail-content">{{ article['content']|safe }}</div>
                
                <div style="margin-top: 36px;">
                    <a href="/" class="nav-item active">← 전체 목록으로 돌아가기</a>
                </div>
            </article>
        {% else %}
            <div class="main-grid">
                {% for item in articles %}
                <a href="/article/{{ item['id'] }}" class="card-link">
                    <div class="card">
                        <div class="card-visual" style="background: linear-gradient(135deg, {{ colors.get(item['category'], ('#1e3c72', '#2a5298'))[0] }}, {{ colors.get(item['category'], ('#1e3c72', '#2a5298'))[1] }});">
                            <span class="badge">{{ item['category'] }}</span>
                            <div class="hl-text">{{ item['title'][:26] }}{% if item['title']|length > 26 %}...{% endif %}</div>
                            <span style="font-size:11px; opacity:0.8;">SISATODAY REPORT</span>
                        </div>
                        <div class="card-body">
                            <span class="cat-tag">{{ item['category'] }}</span>
                            <div class="card-title">{{ item['title'] }}</div>
                            {% if item['lead_text'] or item['summary'] %}
                                <div class="card-lead">{{ item['lead_text'] if item['lead_text'] else item['summary'] }}</div>
                            {% endif %}
                            <span class="card-date">발행: {{ item['created_at'][:10] }}</span>
                        </div>
                    </div>
                </a>
                {% endfor %}
            </div>
        {% endif %}
    </main>
</body>
</html>
"""

# ==========================================
# 관리자 시스템 (/admin)
# ==========================================
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>시사투데이 관리자 시스템</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: "Malgun Gothic", sans-serif; background: #f1f4f8; padding: 20px; color: #333; }
        .topbar { background: #1e293b; color: #fff; padding: 16px 24px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .topbar a { color: #94a3b8; text-decoration: none; font-weight: bold; }
        .box { background: #fff; border-radius: 8px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
        input, select, textarea { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; font-family: inherit; }
        textarea { height: 160px; }
        .btn-submit { background: #0284c7; color: #fff; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: left; }
        th { background: #f8fafc; }
        .btn-del { background: #ef4444; color: #fff; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 12px; }
    </style>
</head>
<body>
    <div class="topbar">
        <h2>⚙️ 시사투데이 창 웹진 관리자 시스템</h2>
        <a href="/">← 웹진 홈으로 이동</a>
    </div>

    <div class="box">
        <h3>📝 새 기사 직접 발행</h3>
        <form action="/admin/add" method="POST">
            <select name="category" required>
                {% for cat_name, cat_slug in categories %}
                <option value="{{ cat_name }}">{{ cat_name }}</option>
                {% endfor %}
            </select>
            <input type="text" name="title" placeholder="기사 제목" required>
            <input type="text" name="lead_text" placeholder="기사 리드문 (한 줄 핵심 요약)">
            <textarea name="content" placeholder="기사 본문 내용 (HTML 지원: &lt;p&gt;, &lt;h3&gt; 등)" required></textarea>
            <button type="submit" class="btn-submit">기사 등록</button>
        </form>
    </div>

    <div class="box">
        <h3>📑 전체 발행 기사 목록 (총 {{ articles|length }}건)</h3>
        <table>
            <thead>
                <tr>
                    <th style="width: 50px;">ID</th>
                    <th style="width: 110px;">분류</th>
                    <th>제목</th>
                    <th style="width: 140px;">발행일시</th>
                    <th style="width: 70px; text-align: center;">관리</th>
                </tr>
            </thead>
            <tbody>
                {% for it in articles %}
                <tr>
                    <td>{{ it['id'] }}</td>
                    <td><b>{{ it['category'] }}</b></td>
                    <td><a href="/article/{{ it['id'] }}" target="_blank" style="text-decoration:none; color:#111;">{{ it['title'] }}</a></td>
                    <td>{{ it['created_at'][:16] }}</td>
                    <td style="text-align: center;">
                        <a href="/admin/delete/{{ it['id'] }}" class="btn-del" onclick="return confirm('삭제하시겠습니까?');">삭제</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

# ==========================================
# 라우트 핸들러
# ==========================================
@flask_app.route("/")
def index():
    cat = request.args.get("cat", "").strip()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as cnt FROM articles")
    total_count = cur.fetchone()['cnt']

    if cat:
        # 한글 이름 또는 영문 slug 둘 다 매칭되도록 조회
        cur.execute("SELECT * FROM articles WHERE category = ? OR cat_slug = ? ORDER BY id DESC", (cat, cat))
    else:
        cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()
    conn.close()

    return render_template_string(
        HTML_TEMPLATE,
        articles=articles,
        nav_categories=CATEGORIES,
        current_cat=cat,
        total_count=total_count,
        colors=CATEGORY_COLORS,
        is_detail=False
    )

@flask_app.route("/article/<int:article_id>")
def article_detail(article_id):
    conn = get_db_connection()
    cur = conn.cursor()

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
        nav_categories=CATEGORIES,
        current_cat=article['category'],
        total_count=total_count,
        colors=CATEGORY_COLORS,
        is_detail=True
    )

@flask_app.route("/admin")
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()
    conn.close()
    return render_template_string(ADMIN_TEMPLATE, articles=articles, categories=CATEGORIES)

@flask_app.route("/admin/add", methods=["POST"])
def admin_add():
    category = request.form.get("category")
    cat_slug = CATEGORY_MAP.get(category, "etc")
    title = request.form.get("title")
    lead_text = request.form.get("lead_text", "")
    content = request.form.get("content")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO articles (category, cat_slug, title, lead_text, summary, content, image_url, source_link, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (category, cat_slug, title, lead_text, lead_text, content, "", "", now_str))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

@flask_app.route("/admin/delete/<int:article_id>")
def admin_delete(article_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))


# ==========================================
# Render 구동용 ASGI 어댑터
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
