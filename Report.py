import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
import time
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    else:
        st.error("Secrets에 GOOGLE_API_KEY가 설정되지 않았습니다.")
except Exception as e:
    st.error(f"API 키 설정 중 에러 발생: {e}")

# --- 2. 논문 검색 함수 (캐싱 적용 + 에러 방지) ---
# @st.cache_data: 이 데코레이터가 있으면 똑같은 검색어는 1시간(3600초) 동안 API를 호출하지 않고 저장된 결과를 보여줍니다.
@st.cache_data(ttl=3600, show_spinner=False)
def get_recent_papers(keywords, months):
    # API에 무리를 주지 않기 위해 잠시 대기
    time.sleep(1)
    
    today = datetime.now()
    cutoff_date = today - timedelta(days=months*30)
    
    # 검색어 결합
    combined_query = " | ".join(keywords)
    
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    # 검색 범위 설정
    current_year = today.year
    year_range = f"{current_year-1}-{current_year}"

    params = {
        "query": combined_query,
        "year": year_range,
        "limit": 100, 
        "fields": "title,abstract,url,publicationDate,venue,citationCount"
    }
    
    try:
        response = requests.get(base_url, params=params)
        
        # 429 에러(너무 많은 요청) 처리
        if response.status_code == 429:
            st.error("🚦 API 요청이 너무 많아 잠시 차단되었습니다. 1~2분 뒤에 다시 시도해주세요.")
            return []
            
        if response.status_code != 200:
            st.error(f"논문 검색 API 오류: {response.status_code}")
            return []

        data = response.json().get('data', [])
        
        filtered_papers = []
        for paper in data:
            pub_date_str = paper.get('publicationDate')
            if pub_date_str:
                try:
                    pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
                    if pub_date >= cutoff_date:
                        filtered_papers.append(paper)
                except ValueError:
                    continue
        
        # 최신순 정렬
        filtered_papers.sort(key=lambda x: x['publicationDate'], reverse=True)
        return filtered_papers

    except Exception as e:
        st.error(f"검색 중 예기치 않은 오류 발생: {e}")
        return []

# --- 3. 제미나이 리포트 작성 ---
def generate_trend_report(papers, keywords, months):
    if not papers:
        return "분석할 논문이 없습니다."

    target_papers = papers[:20]
    
    combined_text = ""
    for i, p in enumerate(target_papers):
        abstract = p.get('abstract')
        if not abstract:
            abstract = "초록 없음"
        combined_text += f"[{i+1}] 날짜: {p['publicationDate']} / 제목: {p['title']} / 초록: {abstract[:200]}...\n"

    prompt = f"""
    당신은 바이오 에너지 공정 전문가입니다.
    사용자 관심 키워드: {', '.join(keywords)}
    
    아래는 최근 {months}개월간 발표된 관련 논문 리스트입니다.
    이들을 분석하여 한국어로 '기술 트렌드 브리핑'을 작성해주세요.
    
    [작성 포인트]
    1. 🔍 **검색 요약**: "총 {len(papers)}건의 최신 논문이 검색되었습니다."
    2. 📈 **핵심 동향**: 최근 연구들이 집중하고 있는 주제 요약
    3. ⭐ **주목할 논문 3선**: 실용적인 연구 3개를 선정하여 이유 설명.
    
    [논문 데이터]
    {combined_text}
    """
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech Trends", layout="wide")
st.title("🔬 최신 바이오 논문 탐색기")
st.caption("팁: 잦은 에러가 발생하면 1~2분 정도 쉬었다가 검색하세요.")

# 사이드바
with st.sidebar:
    st.header("설정")
    
    # 기본값
    default_keywords = "Biodiesel production\nSustainable Aviation Fuel\nTransesterification process"
    
    keywords_input = st.text_area("검색어 (영어, 줄바꿈으로 구분)", value=default_keywords, height=150)
    months = st.slider("검색 기간 (개월)", 1, 24, 6)
    
    search_btn = st.button("검색 시작 🔍", type="primary")

# 메인 화면 로직
if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("검색어를 입력해주세요.")
    else:
        with st.spinner(f"최근 {months}개월간의 논문을 찾고 있습니다..."):
            # 이제 캐싱 덕분에 중복 호출 시 API를 쓰지 않습니다!
            papers = get_recent_papers(keywords, months)
            
            if not papers:
                st.info("검색 결과가 없습니다. 잠시 후 다시 시도하거나 검색어를 변경해보세요.")
            else:
                tab1, tab2 = st.tabs(["📊 AI 요약 리포트", "📝 논문 리스트"])
                
                with tab1:
                    st.success(f"분석 완료! 총 {len(papers)}건의 논문을 찾았습니다.")
                    report = generate_trend_report(papers, keywords, months)
                    st.markdown(report)
                    
                with tab2:
                    for p in papers:
                        with st.expander(f"[{p['publicationDate']}] {p['title']}"):
                            st.write(f"**저널:** {p.get('venue', 'N/A')}")
                            st.write(f"**인용수:** {p.get('citationCount', 0)}")
                            st.markdown(f"[원문 보러가기]({p['url']})")
                            st.caption(p.get('abstract', '초록 내용 없음'))
