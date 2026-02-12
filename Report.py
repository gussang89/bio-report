import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai  # OpenAI 대신 구글 라이브러리 사용
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 ---
# Streamlit Secrets에서 키를 가져와 설정
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except Exception as e:
    st.error("API 키 설정이 잘못되었습니다. Secrets에 GOOGLE_API_KEY를 확인해주세요.")

# --- 2. 논문 검색 함수 (Semantic Scholar) ---
def get_recent_papers(query, days=14):
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
                    if pub_date >= cutoff_date:
                        filtered_papers.append(paper)
                except ValueError:
                    continue
    return filtered_papers

# --- 3. 제미나이 요약 함수 ---
def generate_weekly_report(papers):
    if not papers:
        return "분석할 논문이 없습니다."

    combined_abstracts = ""
    for i, p in enumerate(papers[:20]): # 제미나이는 입력창이 커서 20개도 거뜬합니다
        combined_abstracts += f"[{i+1}] {p['title']}: {p.get('abstract', 'No abstract')} \n\n"

    # 제미나이에게 보낼 프롬프트
    prompt = f"""
    당신은 바이오 에너지 공정 수석 엔지니어입니다.
    아래는 최근 발표된 바이오디젤/SAF 관련 논문들의 초록입니다.
    
    이 내용들을 바탕으로 한국어로 '주간 기술 동향 리포트'를 작성해주세요.
    
    [형식]
    1. 💡 **핵심 트렌드**: 이번 주 연구들이 공통적으로 주목하는 기술 키워드 (3줄 요약)
    2. 🏆 **주목할 만한 성과**: 수율 향상, 비용 절감 등 구체적 수치가 있는 연구 2~3개 선정
    3. 🏭 **현장 적용 아이디어**: 실제 공장에 적용해볼 만한 점
    
    [논문 데이터]
    {combined_abstracts}
    """

    # Gemini 1.5 Flash 모델 사용 (빠르고 저렴함)
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    
    return response.text

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech Report (Gemini)", layout="wide")
st.title("🌿 주간 바이오 기술 리포트 (Powered by Gemini)")

st.sidebar.header("설정")
search_query = st.sidebar.text_input("검색어", value="Biodiesel production optimization")
days_filter = st.sidebar.slider("기간 설정 (일)", 7, 30, 14)

if st.sidebar.button("리포트 생성하기"):
    with st.spinner('Gemini가 최신 논문을 읽고 있습니다...'):
        recent_papers = get_recent_papers(search_query, days=days_filter)
        
        if not recent_papers:
            st.error(f"최근 {days_filter}일 동안 발행된 논문이 없습니다.")
        else:
            st.success(f"총 {len(recent_papers)}건의 논문 발견!")
            
            # 종합 리포트
            st.subheader("📊 Gemini 기술 분석")
            report_content = generate_weekly_report(recent_papers)
            st.markdown(report_content)
            
            st.divider()
            
            # 개별 리스트
            st.subheader("📝 논문 목록")
            for paper in recent_papers:
                with st.expander(f"[{paper['publicationDate']}] {paper['title']}"):
                    st.write(f"**저널:** {paper.get('venue', 'N/A')}")
                    st.write(f"**링크:** {paper['url']}")
                    st.caption(paper.get('abstract', '초록 없음'))
