import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    else:
        st.error("Secrets에 GOOGLE_API_KEY가 설정되지 않았습니다.")
except Exception as e:
    st.error(f"API 키 설정 중 에러 발생: {e}")

# --- 2. 논문 검색 함수 (핵심 수정됨) ---
def get_recent_papers(keywords, months):
    # 1. 날짜 기준 설정
    today = datetime.now()
    cutoff_date = today - timedelta(days=months*30)
    
    # 2. 검색어 결합 (OR 조건)
    # 검색어가 너무 복잡하면 API가 헷갈려하므로, 가장 확실한 방법으로 포맷팅
    combined_query = " | ".join(keywords)
    
    # 3. API 요청 설정
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    # 최근 2년치 데이터에서 검색 (그래야 이번 달 논문이 포함됨)
    current_year = today.year
    year_range = f"{current_year-1}-{current_year}"

    params = {
        "query": combined_query,
        "year": year_range,
        "limit": 100,  # 넉넉하게 100개 가져옴
        "fields": "title,abstract,url,publicationDate,venue,citationCount"
        # 주의: 무료 API에서는 'sort' 파라미터가 불안정할 수 있어, 
        # 최신 연도(year_range)를 타이트하게 잡고 파이썬에서 거르는 방식이 가장 확실합니다.
    }
    
    try:
        response = requests.get(base_url, params=params)
        
        if response.status_code != 200:
            st.error(f"논문 검색 API 오류: {response.status_code}")
            return []

        data = response.json().get('data', [])
        
        # 4. 파이썬에서 날짜 필터링 및 정렬 (여기가 중요!)
        filtered_papers = []
        for paper in data:
            pub_date_str = paper.get('publicationDate')
            if pub_date_str:
                try:
                    pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
                    # 사용자가 설정한 기간(months) 이내인지 확인
                    if pub_date >= cutoff_date:
                        filtered_papers.append(paper)
                except ValueError:
                    continue
        
        # 5. 진짜 최신순으로 다시 정렬 (내림차순)
        filtered_papers.sort(key=lambda x: x['publicationDate'], reverse=True)
        
        return filtered_papers

    except Exception as e:
        st.error(f"검색 중 예기치 않은 오류 발생: {e}")
        return []

# --- 3. 제미나이 리포트 작성 ---
def generate_trend_report(papers, keywords, months):
    if not papers:
        return "분석할 논문이 없습니다."

    # 상위 20개 논문만 분석 (너무 많으면 요약 품질 저하)
    target_papers = papers[:20]
    
    combined_text = ""
    for i, p in enumerate(target_papers):
        # 초록이 없는 경우 제목만이라도 사용
        abstract = p.get('abstract')
        if not abstract:
            abstract = "초록 없음 (제목으로 유추 필요)"
        combined_text += f"[{i+1}] 날짜: {p['publicationDate']} / 제목: {p['title']} / 초록: {abstract[:300]}...\n\n"

    prompt = f"""
    당신은 바이오 에너지 공정 전문가입니다.
    사용자 관심 키워드: {', '.join(keywords)}
    
    아래는 최근 {months}개월간 발표된 관련 논문 리스트입니다.
    이들을 분석하여 한국어로 '기술 트렌드 브리핑'을 작성해주세요.
    
    [작성 포인트]
    1. 🔍 **검색 현황**: "총 {len(papers)}건의 최신 논문이 검색되었습니다." 로 시작할 것.
    2. 📈 **핵심 동향**: 최근 연구들이 집중하고 있는 주제 (예: 특정 공정 효율화, 신규 촉매 등)
    3. ⭐ **주목할 논문 3선**: 가장 실용적이거나 흥미로운 연구 3개를 뽑아 제목과 이유를 간단히 설명.
    
    [논문 데이터]
    {combined_text}
    """
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech Trends", layout="wide")
st.title("🔬 최신 바이오 논문 탐색기")

# 사이드바
with st.sidebar:
    st.header("설정")
    
    # 기본값
    default_keywords = "Biodiesel\nSustainable Aviation Fuel\nTransesterification"
    
    keywords_input = st.text_area("검색어 (줄바꿈으로 구분)", value=default_keywords, height=150)
    months = st.slider("검색 기간 (개월)", 1, 24, 6) # 기본 6개월로 늘림
    
    search_btn = st.button("검색 시작 🔍", type="primary")

# 메인 화면 로직
if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("검색어를 입력해주세요.")
    else:
        with st.spinner(f"최근 {months}개월간의 논문을 찾고 있습니다..."):
            papers = get_recent_papers(keywords, months)
            
            if not papers:
                st.error("조건에 맞는 논문을 찾지 못했습니다. 기간을 늘리거나 검색어를 영어로 변경해보세요.")
                st.info("팁: 한글 검색어는 잘 검색되지 않습니다. (예: 바이오디젤 -> Biodiesel)")
            else:
                # 탭으로 화면 분리
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
