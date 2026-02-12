import streamlit as st
import pandas as pd
import requests
from openai import OpenAI
from datetime import datetime, timedelta

# --- 1. 설정 및 API 키 ---
# 실제 운영 시에는 st.secrets를 사용하여 키를 관리하는 것이 안전합니다.
client = OpenAI(api_key="YOUR_OPENAI_API_KEY")

# --- 2. 날짜 계산 및 논문 검색 함수 ---
def get_recent_papers(query, days=14):
    """
    최근 N일 이내의 논문을 검색하고 필터링합니다.
    Semantic Scholar는 정확한 일자 검색이 어렵으므로, 최근 연도 데이터를 가져와서 Python으로 필터링합니다.
    """
    # 넉넉하게 최근 2년치 데이터를 가져옴 (API 효율성을 위해)
    current_year = datetime.now().year
    year_range = f"{current_year-1}-{current_year}"
    
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&year={year_range}&limit=30&fields=title,abstract,url,publicationDate,venue"
    
    response = requests.get(url)
    filtered_papers = []
    
    if response.status_code == 200:
        data = response.json().get('data', [])
        cutoff_date = datetime.now() - timedelta(days=days)
        
        for paper in data:
            pub_date_str = paper.get('publicationDate')
            if pub_date_str:
                try:
                    pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
                    # 날짜 비교: 설정한 기간(2주) 이내인지 확인
                    if pub_date >= cutoff_date:
                        filtered_papers.append(paper)
                except ValueError:
                    continue # 날짜 형식이 안 맞으면 패스
                    
    return filtered_papers

# --- 3. AI 요약 함수 (개별 요약 + 종합 리포트) ---
def generate_weekly_report(papers):
    """
    수집된 논문들의 초록을 모아서 '주간 기술 트렌드'를 작성합니다.
    """
    if not papers:
        return "분석할 논문이 없습니다."

    # 초록들을 하나로 합침 (토큰 제한 고려하여 앞부분만 일부 발췌 가능)
    combined_abstracts = ""
    for i, p in enumerate(papers):
        combined_abstracts += f"[{i+1}] {p['title']}: {p.get('abstract', 'No abstract')} \n\n"

    prompt = f"""
    당신은 바이오 연료 공정 엔지니어링 전문가입니다. 
    아래는 최근 2주간 발표된 바이오디젤/SAF 관련 논문들의 초록 모음입니다.
    
    이 내용들을 바탕으로 '주간 기술 동향 리포트'를 작성해주세요.
    다음 세 가지 항목으로 나누어 한국어로 정리하세요:
    
    1. **핵심 트렌드**: 이번 주 연구들이 공통적으로 주목하는 기술이나 이슈는 무엇인가? (예: 특정 촉매, 전처리 방식 등)
    2. **주목할 만한 성과**: 수율 향상이나 비용 절감 등 구체적인 숫자가 언급된 획기적인 연구가 있다면 1~2개 꼽아주세요.
    3. **현장 적용 가능성**: 실제 공장에 적용해볼 만한 아이디어가 있는가?

    [논문 데이터]
    {combined_abstracts}
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# --- 4. 메인 UI ---
st.set_page_config(page_title="Weekly Bio-Tech Report", layout="wide")

st.title("📅 주간 바이오 기술 트렌드 리포트")

# 사이드바 설정
st.sidebar.header("설정")
search_query = st.sidebar.text_input("검색어", value="Biodiesel production optimization")
days_filter = st.sidebar.slider("기간 설정 (일)", 7, 30, 14) # 기본 14일(2주)

if st.sidebar.button("리포트 생성하기"):
    with st.spinner(f'최근 {days_filter}일간의 논문을 수집하고 분석 중입니다...'):
        # 1. 논문 수집
        recent_papers = get_recent_papers(search_query, days=days_filter)
        
        if not recent_papers:
            st.error(f"최근 {days_filter}일 동안 발행된 관련 논문이 없습니다. 기간을 늘리거나 검색어를 변경해보세요.")
        else:
            st.success(f"총 {len(recent_papers)}건의 최신 논문을 발견했습니다!")
            
            # 2. 종합 리포트 생성 (가장 상단에 배치)
            st.subheader("📊 AI 기술 분석 리포트")
            report_content = generate_weekly_report(recent_papers)
            st.info(report_content)
            
            st.divider()
            
            # 3. 개별 논문 리스트
            st.subheader("📝 개별 논문 목록")
            for paper in recent_papers:
                with st.expander(f"[{paper['publicationDate']}] {paper['title']}"):
                    st.write(f"**저널:** {paper.get('venue', 'N/A')}")
                    st.write(f"**링크:** {paper['url']}")
                    st.caption(paper.get('abstract', '초록 없음'))

st.sidebar.markdown("---")
st.sidebar.caption("Data source: Semantic Scholar API")