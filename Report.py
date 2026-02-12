import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except Exception as e:
    st.error("API 키 설정 에러: Secrets에 GOOGLE_API_KEY가 있는지 확인해주세요.")

# --- 2. 논문 검색 함수 (멀티 키워드 지원) ---
def get_recent_papers(keywords, days=14):
    """
    여러 키워드를 받아 OR 조건으로 한 번에 검색합니다.
    """
    current_year = datetime.now().year
    year_range = f"{current_year-1}-{current_year}"
    
    # 키워드 리스트를 "keyword1 | keyword2" 형태(OR 검색)로 변환
    # Semantic Scholar는 '|' 기호를 사용하여 OR 검색을 지원합니다.
    combined_query = " | ".join(keywords)
    
    # URL 인코딩 문제 방지를 위해 requests param 사용 권장
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": combined_query,
        "year": year_range,
        "limit": 50,  # 검색어가 많으므로 가져올 논문 수를 50개로 늘림
        "fields": "title,abstract,url,publicationDate,venue"
    }
    
    response = requests.get(base_url, params=params)
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
def generate_weekly_report(papers, keywords):
    if not papers:
        return "분석할 논문이 없습니다."

    # 논문이 너무 많으면 상위 30개만 분석 (Gemini Flash는 컨텍스트가 큼)
    target_papers = papers[:30]
    
    combined_abstracts = ""
    for i, p in enumerate(target_papers):
        combined_abstracts += f"[{i+1}] {p['title']}: {p.get('abstract', 'No abstract')} \n\n"

    keyword_str = ", ".join(keywords)

    prompt = f"""
    당신은 바이오 에너지 공정 수석 엔지니어입니다.
    사용자가 관심 있어 하는 키워드는 [{keyword_str}] 입니다.
    아래는 이와 관련하여 최근 2주간 발표된 논문들의 초록입니다.
    
    이 내용들을 종합하여 한국어로 '주간 기술 트렌드 리포트'를 작성해주세요.
    단순 나열하지 말고, 서로 연관된 기술끼리 묶어서 인사이트를 제공하세요.
    
    [보고서 형식]
    1. 💡 **핵심 트렌드 요약**: 이번 주 검색된 키워드들과 관련된 기술 흐름 (3~5줄)
    2. 🏭 **주요 카테고리별 동향**: (예: SAF 촉매, 전처리 공정, 수율 개선 등으로 나누어 설명)
    3. 🏆 **주목할 만한 성과 (Best Pick)**: 현업에 바로 적용 가능하거나 수치가 획기적인 연구 3개 선정
    
    [논문 데이터]
    {combined_abstracts}
    """

    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech Multi Report", layout="wide")
st.title("🌿 주간 바이오 기술 멀티 리포트")
st.caption("여러 관심사를 한 번에 검색하고 종합적인 트렌드를 파악하세요.")

# 사이드바 설정
st.sidebar.header("🔍 검색 설정")

# 기본 키워드 예시
default_keywords = """Biodiesel production
Sustainable Aviation Fuel (SAF)
HVO process
Transesterification catalyst
Used Cooking Oil (UCO) pretreatment"""

# Text Area로 변경하여 여러 줄 입력 가능하게 함
raw_keywords = st.sidebar.text_area(
    "검색어 입력 (줄바꿈으로 구분, 최대 10개)", 
    value=default_keywords,
    height=200
)

days_filter = st.sidebar.slider("기간 설정 (일)", 7, 30, 14)

if st.sidebar.button("종합 리포트 생성하기 🚀"):
    # 입력된 텍스트를 줄바꿈 기준으로 잘라서 리스트로 만듦
    keyword_list = [k.strip() for k in raw_keywords.split('\n') if k.strip()]
    
    if not keyword_list:
        st.error("검색어를 입력해주세요.")
    else:
        st.info(f"다음 키워드들을 분석합니다: {', '.join(keyword_list)}")
        
        with st.spinner('여러 주제의 최신 논문을 수집하고 트렌드를 분석 중입니다...'):
            recent_papers = get_recent_papers(keyword_list, days=days_filter)
            
            if not recent_papers:
                st.error(f"최근 {days_filter}일 동안 발행된 관련 논문이 없습니다. 기간을 늘려보세요.")
            else:
                st.success(f"총 {len(recent_papers)}건의 최신 논문을 발견했습니다!")
                
                # 종합 리포트
                st.subheader("📊 Gemini 종합 기술 분석")
                report_content = generate_weekly_report(recent_papers, keyword_list)
                st.markdown(report_content)
                
                st.divider()
                
                # 개별 리스트
                st.subheader("📝 수집된 논문 목록")
                for paper in recent_papers:
                    with st.expander(f"[{paper['publicationDate']}] {paper['title']}"):
                        st.write(f"**저널:** {paper.get('venue', 'N/A')}")
                        st.write(f"**링크:** {paper['url']}")
                        st.caption(paper.get('abstract', '초록 없음'))

st.sidebar.markdown("---")
st.sidebar.caption("Powered by Gemini 1.5 Flash & Semantic Scholar")
