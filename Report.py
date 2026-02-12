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

# --- 2. 논문 검색 함수 (기간 확장 대응) ---
def get_recent_papers(keywords, days):
    """
    지정된 기간(일수) 내의 논문을 검색합니다.
    """
    # 기간이 길어지면 연도 범위도 넓어야 하므로 2년치(올해, 작년)를 기본으로 잡습니다.
    current_year = datetime.now().year
    year_range = f"{current_year-1}-{current_year}"
    
    combined_query = " | ".join(keywords)
    
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": combined_query,
        "year": year_range,
        "limit": 100,  # 기간이 늘어난 만큼 검색 한도를 50 -> 100개로 늘림
        "fields": "title,abstract,url,publicationDate,venue"
    }
    
    response = requests.get(base_url, params=params)
    filtered_papers = []
    
    if response.status_code == 200:
        data = response.json().get('data', [])
        # 오늘 날짜에서 'days'만큼 뺀 날짜를 기준점으로 설정
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
def generate_monthly_report(papers, keywords, months):
    if not papers:
        return "분석할 논문이 없습니다."

    # 논문이 많을 수 있으니 상위 40개까지 분석 (Gemini Flash는 컨텍스트가 큼)
    target_papers = papers[:40]
    
    combined_abstracts = ""
    for i, p in enumerate(target_papers):
        combined_abstracts += f"[{i+1}] {p['title']} ({p.get('publicationDate')}): {p.get('abstract', 'No abstract')} \n\n"

    keyword_str = ", ".join(keywords)

    prompt = f"""
    당신은 바이오 에너지 공정 수석 엔지니어입니다.
    사용자가 관심 있어 하는 키워드는 [{keyword_str}] 입니다.
    아래는 지난 {months}개월간 발표된 논문들의 초록입니다.
    
    이 내용들을 종합하여 한국어로 '월간 기술 트렌드 리포트'를 작성해주세요.
    단순 나열하지 말고, 긴 기간의 기술 흐름 변화를 읽어내세요.
    
    [보고서 형식]
    1. 📅 **기간 분석 ({months}개월간의 흐름)**: 이 기간 동안 연구 트렌드가 어떻게 변화했는지, 어떤 주제가 가장 핫했는지 요약.
    2. 🏭 **주요 카테고리별 동향**: (예: 공정 최적화, 신규 촉매, 대체 원료 등으로 나누어 설명)
    3. 🏆 **기간 내 Best 연구**: 현업 적용 가능성이 가장 높은 핵심 논문 3개를 선정하고 이유를 설명.
    
    [논문 데이터]
    {combined_abstracts}
    """

    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech Monthly Report", layout="wide")
st.title("🌿 바이오 기술 트렌드 리포트 (월간/주간)")

# 사이드바 설정
st.sidebar.header("🔍 검색 설정")

default_keywords = """Biodiesel production
Sustainable Aviation Fuel (SAF)
HVO process
Transesterification catalyst
Used Cooking Oil (UCO) pretreatment"""

raw_keywords = st.sidebar.text_area(
    "검색어 입력 (줄바꿈으로 구분, 최대 10개)", 
    value=default_keywords,
    height=200
)

# [변경] 슬라이더를 '월' 단위로 변경 (1개월 ~ 12개월)
months_filter = st.sidebar.slider("검색 기간 설정 (월)", 1, 12, 1)

if st.sidebar.button("리포트 생성하기 🚀"):
    keyword_list = [k.strip() for k in raw_keywords.split('\n') if k.strip()]
    
    # 월을 일(days)로 환산
    days_converted = months_filter * 30
    
    if not keyword_list:
        st.error("검색어를 입력해주세요.")
    else:
        st.info(f"최근 {months_filter}개월 ({days_converted}일) 동안의 논문을 분석합니다...")
        
        with st.spinner('방대한 기간의 데이터를 수집하고 분석 중입니다...'):
            recent_papers = get_recent_papers(keyword_list, days=days_converted)
            
            if not recent_papers:
                st.warning(f"최근 {months_filter}개월 동안 발견된 논문이 없습니다. 검색어를 좀 더 넓은 범위로 바꿔보세요.")
            else:
                st.success(f"총 {len(recent_papers)}건의 논문을 발견했습니다!")
                
                # 종합 리포트
                st.subheader(f"📊 지난 {months_filter}개월간의 기술 분석")
                report_content = generate_monthly_report(recent_papers, keyword_list, months_filter)
                st.markdown(report_content)
                
                st.divider()
                
                # 개별 리스트
                st.subheader("📝 수집된 논문 목록")
                # 최신순 정렬
                recent_papers.sort(key=lambda x: x.get('publicationDate', ''), reverse=True)
                
                for paper in recent_papers:
                    with st.expander(f"[{paper['publicationDate']}] {paper['title']}"):
                        st.write(f"**저널:** {paper.get('venue', 'N/A')}")
                        st.write(f"**링크:** {paper['url']}")
                        st.caption(paper.get('abstract', '초록 없음'))

st.sidebar.markdown("---")
st.sidebar.caption("Powered by Gemini 1.5 Flash & Semantic Scholar")
