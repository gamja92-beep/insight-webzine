import os
import sqlite3
import json
import time
import threading
import random
from datetime import datetime

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

app = FastAPI()

ADMIN_STATS_PASSWORD = "admin1234"

client = None
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_api_key:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
except Exception:
    client = None

def get_db():
    conn = sqlite3.connect("webzine.db", timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0
        )
    """)
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN views INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN likes INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

AUTO_TOPIC_POOL = [
    ("정부 지원금/복지 혜택", "2026년 시니어 임플란트 및 틀니 건강보험 적용 혜택과 본인부담금 완벽 가이드"),
    ("문화/예술", "시니어를 위한 전국 힐링 무장애 나눔길 베스트 5 및 코스별 대중교통 상세 안내"),
    ("생활 경제/세무 상식", "2026년 기초연금 수급자격 및 소득인정액 모의계산법과 인상 혜택 총정리"),
    ("시니어 건강/식품", "시니어 무릎 관절염 예방 걷기 운동법과 연골 부담 줄이는 생활 수칙"),
    ("정부 지원금/복지 혜택", "문화누리카드 지원금 100% 알찬 활용법과 KTX 기차여행 할인 연계 꿀팁"),
    ("생활 경제/세무 상식", "주택연금 가입조건과 내 집으로 받는 평생 월 지급금 수령액 비교 분석"),
    ("시니어 건강/식품", "혈관 나이를 10년 젊게 만드는 아침 식습관과 필수 항산화 식단 가이드"),
    ("문화/예술", "국립자연휴양림 시니어 치유 숲 프로그램 예약 방법과 입장료 감면 혜택")
]

def make_base_template_content(topic):
    return """
    <h2>1. 주요 배경과 핵심 정보</h2>
    <p>""" + topic + """에 대해 독자 여러분이 반드시 알아야 할 핵심 정보를 상세히 안내해 드립니다. 본 가이드는 실생활에서 즉시 활용할 수 있는 알찬 지침을 담고 있습니다.</p>
    <h2>2. 한눈에 비교하는 기준 및 혜택 요약</h2>
    <table class="table table-bordered my-3">
        <thead class="table-light">
            <tr><th>구분</th><th>주요 지원 내용</th><th>지원 대상 및 기준</th></tr>
        </thead>
        <tbody>
            <tr><td>기본 지원</td><td>맞춤형 혜택 및 본인부담금 대폭 감면</td><td>만 65세 이상 및 해당 가구</td></tr>
            <tr><td>신청 방법</td><td>정부24 온라인 신청 또는 관할 주민센터 방문</td><td>신분증 및 구비서류 지참</td></tr>
        </tbody>
    </table>
    <h2>3. 실패 없는 실전 신청 절차</h2>
    <ol>
        <li>신청 자격 및 해당 연도 소득인정액 기준을 확인합니다.</li>
        <li>필수 지참 서류를 구비하여 관할 기관 또는 공식 웹사이트에 접수합니다.</li>
        <li>심사 통과 후 혜택을 수령하고 변동 사항을 주기적으로 확인합니다.</li>
    </ol>
    <h2>4. 전문가 주의사항 및 알짜 꿀팁</h2>
    <ul>
        <li>신청 기한을 넘기면 소급 지원이 어려울 수 있으니 사전 신청 기간을 반드시 확인하세요.</li>
        <li>기타 유사 복지 제도와의 중복 수혜 가능 여부를 전담 고객센터에 사전 문의하시기 바랍니다.</li>
    </ul>
    <h2>5. 자주 묻는 질문 (FAQ)</h2>
    <p><strong>Q. 본인 방문이 어려울 때 대리 신청이 가능한가요?</strong><br>A. 네, 배우자나 직계가족이 위임장과 신분증, 가족관계증명서를 지참하시면 가능합니다.</p>
    """

def update_article_with_ai(article_id, category, topic):
    if not client:
        return
    
    prompt = """
    당신은 5060 시니어 전문 웹진의 수석 에디터입니다.
    아래 [주제]와 [카테고리]에 대해 독자가 5분 이상 깊이 읽을 '초고품질 심층 가이드 기사'를 작성해 주세요.

    [주제]: """ + topic + """
    [카테고리]: """ + category + """

    [작성 가이드라인]:
    1. 분량: 한글 1,500자 ~ 2,000자 이상의 매우 상세하고 유익한 내용.
    2. 기사 구성 (HTML 태그 필수 적용):
       - [제목]: 신뢰감 있고 매력적인 고품격 헤드라인
       - [요약]: 핵심 3줄 브리핑 (1., 2., 3. 번호 포함)
       - [본문]: <h2>1. 주요 배경과 핵심 정보</h2>, <h2>2. 한눈에 비교하는 기준 및 혜택 요약</h2> (HTML <table> 표 포함), <h2>3. 실패 없는 실전 신청 절차</h2> (<ol> 리스트), <h2>4. 전문가 주의사항 및 알짜 꿀팁</h2> (<ul> 리스트), <h2>5. 자주 묻는 질문 (FAQ)</h2> (질문 3가지와 명쾌한 답변)
    3. 어조: 뉴스 아나운서처럼 정중하고 신뢰를 주는 어조 ('~합니다', '~하시기 바랍니다').

    [출력 JSON 규격]:
    {
        "title": "기사 제목",
        "summary": "1. ... 2. ... 3. ...",
        "content": "<h2>1. ...</h2><p>...</p><table>...</table><h2>3. ...</h2><ol>...</ol><h2>4. ...</h2><ul>...</ul><h2>5. 자주 묻는 질문 (FAQ)</h2><p><strong>Q1...</strong></p><p>A1...</p>"
    }
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=dict(response_mime_type="application/json")
        )
        raw = response.text.strip()
        
        # 문법 에러 원인이었던 문자열 닫기 완벽 수정
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
            
        if raw.endswith("
