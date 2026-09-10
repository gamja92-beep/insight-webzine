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

# ==========================================
# 영구 보존용 40대 마스터 기사 데이터베이스 (자동 복원용)
# ==========================================
RESTORE_ARTICLES = [
    # 1. 정치/시사
    ("정치/시사", "신산업 입법의 골든타임: 규제 혁신과 안전망 구축의 조화", "급변하는 글로벌 신산업 경쟁 속에서 입법부의 선제적 제도 정비가 절실합니다.", 
     "<h3>1. 현안 배경</h3><p>글로벌 기술 패권 경쟁이 격화되는 가운데, 국내 신산업 규제 완화와 국민 안전망 구축 사이의 정책 조율이 핵심 과제로 떠올랐습니다.</p><h3>2. 쟁점 분석</h3><p>산업계는 과감한 규제 샌드박스 확대를 요구하는 반면, 노동·시민단체는 사회적 안전장치 확보를 우선순위로 꼽고 있습니다.</p><h3>3. 향후 전망</h3><p>국회 상임위 중심의 후속 법안 논의가 분수령이 될 전망입니다.</p>"),
    ("정치/시사", "연금개혁 입법의 교착과 차기 대선 정국의 정책적 과제", "국민연금 모수개혁과 구조개혁을 둘러싼 여야의 셈법이 복잡해지고 있습니다.",
     "<h3>1. 현안 배경</h3><p>기금 고갈 우려가 가시화되며 보험료율과 소득대체율 조정을 둘러싼 사회적 합의 필요성이 최고조에 달했습니다.</p><h3>2. 쟁점 분석</h3><p>세대 간 형평성 제고와 노후 소득 보장의 지속가능성을 둘러싸고 치열한 공방이 이어집니다.</p>"),
    ("정치/시사", "인공지능 시대의 K-콘텐츠 보호와 입법적 과제", "생성형 AI의 저작물 무단 학습 논란과 창작자 권익 보호 대책을 진단합니다.",
     "<h3>1. 현안 배경</h3><p>생성 AI 시장이 급성장함에 따라 국내 문화 창작 생태계 보호를 위한 저작권법 개정이 시급해졌습니다.</p>"),
    ("정치/시사", "지방소멸 위기 극복을 위한 균형발전 특별법 평가", "지역 경제 거점 육성과 청년 정주 여건 조성을 위한 전략적 대안을 모색합니다.",
     "<h3>1. 현안 배경</h3><p>수도권 집중화 현상 심화로 지방 소멸 위험도가 역대 최고치를 기록 중입니다.</p>"),

    # 2. 경제/주식
    ("경제/주식", "1세대 1주택 비과세 요건 및 시니어 부동산 합법적 절세 체크리스트", "고령층 자산 구성의 80%를 차지하는 부동산 세금 부담 완화 노하우를 정리했습니다.",
     "<h3>1. 핵심 절세 포인트</h3><p>보유 기간과 거주 요건의 정밀 점검을 통해 양도세 감면 혜택을 극대화해야 합니다.</p><h3>2. 증여와 상속</h3><p>사전 증여 시점과 공제 한도 활용법을 사전에 숙지하는 것이 유리합니다.</p>"),
    ("경제/주식", "국제유가 급등과 금리 정책의 딜레마: 한국 경제 영향", "원자재 가격 변동성이 무역수지와 가계 실질소득에 미치는 연쇄 파장을 분석합니다.",
     "<h3>1. 시장 현황</h3><p>지정학적 리스크로 인한 공급 불안이 물가 안정 목표 달성에 새로운 변수로 작용하고 있습니다.</p>"),
    ("경제/주식", "배당소득 분리과세 추진과 고배당 가치주 시장의 지각변동", "자본시장 밸류업 정책과 맞물린 배당 투자 전략의 대전환점을 짚어봅니다.",
     "<h3>1. 투자자 관점</h3><p>안정적인 현금흐름을 추구하는 장기 투자자들에게 절세와 수익을 동시에 잡는 기회가 될 수 있습니다.</p>"),
    ("경제/주식", "공실 상가 리모델링과 시니어 실버타운 전환 사업성 분석", "도심 공동화 상가를 시니어 복합 케어 시설로 재편하는 신수익 모델을 고찰합니다.",
     "<h3>1. 사업 구조</h3><p>단순 임대업을 넘어 헬스케어와 복지 시설이 융합된 고부가가치 모델로 진화하고 있습니다.</p>"),

    # 3. 건강/복지
    ("건강/복지", "2026년 기초연금 수급 자격 선정기준액 및 감액 없는 신청 요령", "어르신들의 든든한 버팀목인 기초연금 수급 자격과 핵심 변경사항을 점검합니다.",
     "<h3>1. 자격 기준</h3><p>소득인정액 계산 시 공제되는 기본재산액과 금융재산 평가 방식을 꼼꼼히 확인해야 합니다.</p><h3>2. 직종별 주의점</h3><p>국민연금 연계 감액 조항과 부부 감액 규정을 숙지하여 불이익을 방지할 수 있습니다.</p>"),
    ("건강/복지", "혈관 나이를 10년 젊게 만드는 아침 식습관과 필수 항산화 식단", "중장년층 뇌심혈관 질환 예방을 위한 과학적 영양 가이드라인을 소개합니다.",
     "<h3>1. 아침 첫 끼니의 중요성</h3><p>기상 직후 미온수 섭취와 정제 탄수화물 절제가 혈당 스파이크를 방지합니다.</p>"),
    ("건강/복지", "노인장기요양보험 1~5등급 판정 기준과 재가급여 200% 활용 팁", "가족 간병 부담을 덜어주는 장기요양 제도의 최신 혜택과 신청 절차를 총정리했습니다.",
     "<h3>1. 등급 판정 요령</h3><p>의사소견서 준비와 공단 방문 조사 시 일상생활 수행 능력(ADL)을 명확히 전달해야 합니다.</p>"),
    ("건강/복지", "치매 조기 발견을 위한 인지선별검사(CIST)와 지역 안심센터 이용법", "보건소 치매안심센터를 통한 무료 조기 검진과 정서 지원 프로그램의 실전 혜택입니다.",
     "<h3>1. 검사 절차</h3><p>기억력 감퇴가 의심될 때 즉시 인근 센터를 방문해 전문 상담을 받을 수 있습니다.</p>"),

    # 4. 세상이야기
    ("세상이야기", "국내 힐링 명소 가이드 및 시니어를 위한 문화누리카드 알찬 활용법", "연 13만 원 지원되는 문화누리카드를 100% 누리는 숨은 명소와 여행 팁입니다.",
     "<h3>1. 이용 혜택</h3><p>KTX 할인 및 주요 국립공원·문화재 무료 입장 등 폭넓은 시니어 우대 혜택을 연계할 수 있습니다.</p>"),
    ("세상이야기", "팬덤이 이끄는 스포츠 기부 생태계의 변화와 미래 전망", "단순 응원을 넘어 사회적 연대와 나눔으로 확장되는 대중문화 현상을 조명합니다.",
     "<h3>1. 문화적 현상</h3><p>선한 영향력을 확산하는 팬덤 기부 문화가 새로운 공익 기여 모델로 정착하고 있습니다.</p>"),
    ("세상이야기", "초고령사회 마을공동체 회복과 은퇴자 재능나눔 우수 사례", "마을 도서관, 골목 안전 지킴이로 활약하는 시니어 액티브 세대의 따뜻한 현장입니다.",
     "<h3>1. 현장 르포</h3><p>자신의 전문 분야를 지역 청소년과 이웃에게 환원하며 보람찬 인생 2막을 여는 사례가 늘고 있습니다.</p>"),
    ("세상이야기", "보이스피싱·스미싱 신종 수법 분석과 어르신 금융사기 예방 백서", "가족 사칭 AI 음성 복제 등 지능화된 금융 사기로부터 소중한 자산을 지키는 안전 수칙입니다.",
     "<h3>1. 핵심 대응</h3><p>의심스러운 인터넷 주소(URL) 클릭 금지와 112 즉시 신고 원칙을 철저히 지켜야 합니다.</p>"),

    # 5. AI/테크
    ("AI/테크", "생성형 AI 시대, 중장년층을 위한 실전 스마트폰 음성 비서 100% 활용기", "복잡한 앱 설치 없이 말 한마디로 일정 정리, 병원 예약, 정보 검색을 끝내는 비결입니다.",
     "<h3>1. 실전 팁</h3><p>음성 인식 기능을 통해 문자 작성과 길 찾기를 손쉽게 처리할 수 있습니다.</p>"),
    ("AI/테크", "자율주행 대중교통 도입 현주소: 노약자 이동권 혁신 어디까지 왔나", "지방 소도시 수요응답형 버스(DRT)와 자율주행 셔틀의 도입 성과를 분석합니다.",
     "<h3>1. 기술 전망</h3><p>벽지 노선 교통 소외 문제를 해결할 대안으로 자율주행 모빌리티가 급부상하고 있습니다.</p>"),
    ("AI/테크", "휴머노이드 돌봄 로봇의 노인 요양 시설 보급과 윤리적 과제", "식사 보조, 말벗 대화, 낙상 감지 로봇이 바꿀 미래 복지 현장을 조망합니다.",
     "<h3>1. 기술 트렌드</h3><p>돌봄 인력 부족을 해소하는 동시에 인간적 온기를 유지하기 위한 가이드라인이 요구됩니다.</p>"),
    ("AI/테크", "디지털 헬스케어 웨어러블: 심전도·혈압 실시간 체크가 바꾼 응급 체계", "손목시계 하나로 부정맥과 고혈압을 사전 감지해 골든타임을 지키는 첨단 의학입니다.",
     "<h3>1. 현장 적용</h3><p>병원 전자의무기록(EMR)과 연동되어 만성질환자의 원격 관리가 현실화되고 있습니다.</p>"),

    # 6. 생활정보
    ("생활정보", "2026년 대중교통 K-패스 환급률 확대와 어르신 무임교통 혜택 가이드", "매달 지출되는 교통비를 최대 53%까지 돌려받는 스마트한 절약법입니다.",
     "<h3>1. 환급 혜택</h3><p>전국 지하철, 시내버스 이용 시 월 최대 환급액과 적립 요건을 상세히 정리했습니다.</p>"),
    ("생활정보", "단독주택 및 아파트 에너지 효율 개선 보조금 지원 사업 총정리", "창호 교체, 친환경 보일러 설치 시 정부가 최대 70%까지 지원하는 꿀팁 정보입니다.",
     "<h3>1. 지원 대상</h3><p>노후 주택 단열 성능 강화를 위한 그린리모델링 이자 지원 사업을 활용하세요.</p>"),
    ("생활정보", "상속세 부담 줄이는 사전 증여 10년 주기 법칙과 필수 증빙 서류", "자녀와 배우자에게 미리 합법적으로 자산을 배분해 분쟁을 예방하는 재테크 전략입니다.",
     "<h3>1. 전략 수립</h3><p>증여 재산 공제 한도를 10년 주기로 갱신하여 절세 폭을 극대화할 수 있습니다.</p>"),
    ("생활정보", "여름·겨울철 냉난방비 반값으로 줄이는 실내 온도 조절기 세팅 비법", "온돌 모드와 실내 모드의 차이점을 정확히 알고 가스비를 아끼는 생활 상식입니다.",
     "<h3>1. 사용법</h3><p>외출 시 보일러 끄기보다 외출 모드 또는 설정 온도 2~3도 하향이 효율적입니다.</p>"),

    # 7. 연예뉴스
    ("연예뉴스", "트로트 열풍의 진화: 중장년층이 주도하는 콘서트 티켓팅 문화와 경제 효과", "공연 문화를 새롭게 견인하는 중장년 팬덤의 활약과 건전한 소비 트렌드를 짚어봅니다.",
     "<h3>1. 문화적 현상</h3><p>지역 경제를 살리고 세대 간 소통을 이끄는 트로트 축제의 긍정적 파급 효과입니다.</p>"),
    ("연예뉴스", "추억의 가요무대와 7080 레전드 스타들의 화려한 귀환", "오랜 세월 대중과 함께 울고 웃었던 명곡들이 현대적 감각으로 재탄생하는 현장입니다.",
     "<h3>1. 감성 리포트</h3><p>세대 공감을 이끌어내는 불멸의 명곡들이 주는 치유와 위로의 메시지를 전합니다.</p>"),

    # 8. 스포츠
    ("스포츠", "시니어 파크골프 열풍: 전국 구장 현황과 부상 없는 스윙 테크닉", "관절 부담 없이 온 가족이 즐기는 파크골프의 인기 비결과 입문 가이드입니다.",
     "<h3>1. 운동 효과</h3><p>하루 만 보 걷기와 근력 강화를 동시에 충족하는 중장년 최고의 생활 스포츠입니다.</p>"),
    ("스포츠", "걷기 운동의 기적: 인터벌 보행법으로 혈당 낮추고 하체 근육 키우기", "단순 산책을 넘어 효과를 3배로 끌어올리는 바른 걷기 자세와 보폭 설정법입니다.",
     "<h3>1. 실천 가이드</h3><p>빠른 걸음과 보통 걸음을 3분씩 교차하는 인터벌 걷기의 놀라운 의학적 효과입니다.</p>"),

    # 9. 지역창
    ("지역창", "동해안 해양치유 힐링 코스: 속초·고성 바다 산책로와 솔숲 쉼터 가이드", "푸른 파도와 울창한 해송 숲을 따라 걷는 강원 영동권의 숨겨진 보물 쉼터입니다.",
     "<h3>1. 추천 코스</h3><p>영랑호 둘레길부터 외옹치 바다향기로까지 무장애 힐링 트레킹 코스를 소개합니다.</p>"),
    ("지역창", "강원권 산불 예방과 산림 생태 복원: 주민 참여형 숲 가꾸기 현주소", "소중한 자연유산을 지키고 푸른 숲을 미래 세대에 물려주기 위한 지역민의 노력입니다.",
     "<h3>1. 보전 노력</h3><p>밀원수 식재와 산림 감시 체계 고도화로 안전한 산림 환경을 가꾸어 갑니다.</p>")
]


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_and_auto_restore_db():
    conn = get_db_connection()
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

    # 기사가 10개 미만으로 리셋되어 있을 때 40대 마스터 기사 즉시 자동 복원
    cur.execute("SELECT COUNT(*) as cnt FROM articles")
    cnt = cur.fetchone()['cnt']
    if cnt < 10:
        base_date = datetime.datetime.now()
        for idx, item in enumerate(RESTORE_ARTICLES):
            date_str = (base_date - datetime.timedelta(hours=idx*3)).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO articles (category, title, lead_text, content, image_url, source_link, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (item[0], item[1], item[2], item[3], "", "", date_str))
        conn.commit()
    conn.close()

init_and_auto_restore_db()


# ==========================================
# 1. 텍스트 추출 & 실시간 속보 작성 엔진
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
    if any(k in clean for k in ['논란', '의혹', '충격', '폭등', '급락', '비상']):
        return f"\"{clean}\"... 핵심 쟁점과 파급 효과 총정리"
    elif '?' in clean:
        return f"{clean} 현장 분석 및 전문가 전망"
    else:
        return f"\"{clean}\"... 지금 실시간 주목받는 진짜 이유는?"

def compose_depth_article(category: str, raw_title: str, summary: str) -> dict:
    clean_title = strip_html_tags(raw_title)
    click_title = generate_click_worthy_title(clean_title)
    lead = f"최근 {category} 분야에서 '{clean_title}' 현안이 대두되며 대중과 학계·업계의 시선이 집중되고 있습니다."

    body_html = f"""
    <p class="article-lead"><b>[시사투데이 실시간 기획분석]</b> {lead}</p>
    
    <h3>1. 사건 경위 및 최근 발생 배경</h3>
    <p>{summary if summary else clean_title}와 관련하여 당사자 및 관계 기관 간의 견해차가 가시화되면서 온·오프라인 전반에서 뜨거운 논쟁이 촉발되었습니다. 단순 단발성 이슈에 그치지 않고 시장 전반에 구조적 파장을 가져올 가능성이 제기됩니다.</p>

    <h3>2. 핵심 쟁점 및 찬반 대립 구도</h3>
    <p>이번 사안의 가장 첨예한 분기점은 실효성과 부작용의 충돌입니다. 신속한 개혁과 현실적인 대책 마련을 촉구하는 목소리가 높은 반면, 안전망과 신중한 영향 평가가 선행되어야 한다는 반론도 만만치 않습니다.</p>

    <h3>3. 독자 및 실생활에 미치는 파급 영향</h3>
    <p>이 이슈는 일반 국민들의 일상생활 및 경제적 의사결정에 직결되어 있습니다. 후속 규제나 시장 변화의 폭에 따라 실질적인 혜택과 부담 요인이 엇갈릴 수 있는 만큼 면밀한 대응이 요구됩니다.</p>

    <h3>4. 향후 관전 포인트 및 대응 전략</h3>
    <p>주요 부처의 공식 입장 발표와 추가 입법 논의가 예고되어 있습니다. 시사투데이 특별취재팀은 향후 전개될 세부 변동사항을 현장에서 밀착 추적하여 심층 보도할 예정입니다.</p>
    """
    return {"title": click_title, "lead": lead, "content": body_html}

def fetch_and_publish_bulk(limit_per_category: int = 2):
    conn = get_db_connection()
    cur = conn.cursor()
    for cat_name, feed_url in CRAWL_TARGETS.items():
        items = get_rss_items(feed_url)
        added = 0
        for entry in items:
            if added >= limit_per_category:
                break
            cur.execute("SELECT id FROM articles WHERE source_link = ?", (entry['link'],))
            if cur.fetchone():
                continue
            raw_summary = strip_html_tags(entry['description'])
            article_data = compose_depth_article(cat_name, entry['title'], raw_summary)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute("""
                INSERT INTO articles (category, title, lead_text, content, image_url, source_link, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cat_name, article_data["title"], article_data["lead"], article_data["content"], "", entry['link'], now_str))
            added += 1
    conn.commit()
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
    <title>시사투데이 창 - 정론 심층 분석 웹진</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Pretendard", sans-serif; background-color: #f4f6f9; color: #222; }
        .header { background: #fff; border-bottom: 2px solid #002d5b; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 26px; font-weight: 900; color: #002d5b; text-decoration: none; }
        .logo span { background: #002d5b; color: #fff; padding: 2px 8px; border-radius: 4px; margin-left: 5px; }
        .btn-group { display: flex; gap: 10px; align-items: center; }
        .btn-crawl { background: #ff0055; color: #fff; text-decoration: none; padding: 9px 16px; border-radius: 4px; font-size: 13px; font-weight: bold; }
        .btn-admin { background: #2c3e50; color: #fff; text-decoration: none; padding: 9px 16px; border-radius: 4px; font-size: 13px; font-weight: bold; }

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
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">시사투데이<span>창</span></a>
        <div class="btn-group">
            <a href="/crawl-bulk" class="btn-crawl">⚡ 최신 이슈 추가 취재</a>
            <a href="/admin" class="btn-admin">⚙️ 관리자 홈</a>
        </div>
    </header>

    <nav class="nav-bar">
        <a href="/" class="nav-item {% if not current_cat %}active{% endif %}">전체 기사 ({{ total_count }})</a>
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
    </main>
</body>
</html>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>시사투데이 - 관리자 대시보드</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", sans-serif; background-color: #f1f4f8; color: #333; }
        .topbar { background: #1e293b; color: #fff; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
        .topbar h2 { font-size: 20px; font-weight: 800; }
        .topbar a { color: #94a3b8; text-decoration: none; font-size: 13px; font-weight: bold; }
        .topbar a:hover { color: #fff; }
        .wrap { max-width: 1100px; margin: 24px auto; padding: 0 16px; }
        .box { background: #fff; border-radius: 8px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
        .box h3 { font-size: 17px; margin-bottom: 16px; color: #0f172a; border-left: 4px solid #0284c7; padding-left: 8px; }
        input, select, textarea { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-family: inherit; font-size: 14px; }
        textarea { height: 160px; resize: vertical; }
        .btn-submit { background: #0284c7; color: #fff; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 14px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: left; }
        th { background: #f8fafc; color: #475569; font-weight: bold; }
        .btn-del { background: #ef4444; color: #fff; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 12px; }
    </style>
</head>
<body>
    <div class="topbar">
        <h2>⚙️ 시사투데이 창 웹진 관리자 시스템</h2>
        <a href="/">← 웹진 사용자 메인으로 이동</a>
    </div>
    <div class="wrap">
        <div class="box">
            <h3>📝 새 기사 직접 발행</h3>
            <form action="/admin/add" method="POST">
                <select name="category" required>
                    <option value="정치/시사">정치/시사</option>
                    <option value="경제/주식">경제/주식</option>
                    <option value="세상이야기">세상이야기</option>
                    <option value="AI/테크">AI/테크</option>
                    <option value="건강/복지">건강/복지</option>
                    <option value="생활정보">생활정보</option>
                    <option value="연예뉴스">연예뉴스</option>
                    <option value="스포츠">스포츠</option>
                    <option value="지역창">지역창</option>
                </select>
                <input type="text" name="title" placeholder="기사 제목을 입력하세요" required>
                <input type="text" name="lead_text" placeholder="기사 리드문 (한 줄 핵심 요약)">
                <textarea name="content" placeholder="기사 본문 내용 (HTML 태그 지원)" required></textarea>
                <button type="submit" class="btn-submit">기사 정식 발행</button>
            </form>
        </div>
        <div class="box">
            <h3>📑 발행된 기사 관리 (총 {{ articles|length }}건)</h3>
            <table>
                <thead>
                    <tr>
                        <th style="width: 50px;">ID</th>
                        <th style="width: 100px;">분류</th>
                        <th>제목</th>
                        <th style="width: 140px;">발행일시</th>
                        <th style="width: 70px; text-align: center;">관리</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in articles %}
                    <tr>
                        <td>{{ item['id'] }}</td>
                        <td><b>{{ item['category'] }}</b></td>
                        <td><a href="/article/{{ item['id'] }}" target="_blank" style="text-decoration:none; color:#111;">{{ item['title'] }}</a></td>
                        <td>{{ item['created_at'][:16] }}</td>
                        <td style="text-align: center;">
                            <a href="/admin/delete/{{ item['id'] }}" class="btn-del" onclick="return confirm('정말 삭제하시겠습니까?');">삭제</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""


# ==========================================
# 3. 라우트 정의
# ==========================================
@flask_app.route("/")
def index():
    cat = request.args.get("cat", "").strip()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
    db_cats = [row['category'] for row in cur.fetchall()]
    all_categories = list(dict.fromkeys(list(CRAWL_TARGETS.keys()) + db_cats))

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

@flask_app.route("/crawl-bulk")
def crawl_bulk():
    fetch_and_publish_bulk(limit_per_category=2)
    return redirect(url_for("index"))

@flask_app.route("/admin")
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles ORDER BY id DESC")
    articles = cur.fetchall()
    conn.close()
    return render_template_string(ADMIN_TEMPLATE, articles=articles)

@flask_app.route("/admin/add", methods=["POST"])
def admin_add():
    category = request.form.get("category")
    title = request.form.get("title")
    lead_text = request.form.get("lead_text")
    content = request.form.get("content")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO articles (category, title, lead_text, content, image_url, source_link, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (category, title, lead_text, content, "", "", now_str))
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
# 4. Render Uvicorn 호환 내장 ASGI 브리지
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
