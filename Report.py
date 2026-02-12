import streamlit as st
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
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

# --- 2. arXiv 논문 검색 함수 (차단 없는 API) ---
def get_arxiv_papers(keywords, months):
    # arXiv API는 'all:키워드' 형태로 검색합니다.
    # 예: (all:biodiesel OR all:SAF)
    query_parts = [f'all:"{k}"' for k in keywords]
    search_query = " OR ".join(query_parts)
    
    # URL 인코딩 (특수문자 처리)
    encoded_query = urllib.parse.quote(search_query)
    
    # 최신순 정렬 (submittedDate), 30개만 가져옴
    base_url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results=30&sortBy=submittedDate&sortOrder=descending"
    
    try:
        with urllib.request.urlopen(base_url) as url:
            data = url.read().decode('utf-8')
            
        # XML 파싱 (arXiv는 XML로 데이터를 줍니다)
        root = ET.fromstring(data)
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        
        cutoff_date = datetime.now() - timedelta(days=months*30)
        filtered_papers = []
        
        for entry in root.findall('atom:entry', namespace):
            published_str = entry.find('atom:published', namespace).text
            # 날짜 형식: 2024-02-12T14:00:00Z
            published_date = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ")
            
            if published_date >= cutoff_date:
                title = entry.find('atom:title', namespace).text.strip().replace('\n', ' ')
                summary = entry.find('atom:summary', namespace).text.strip().replace('\n', ' ')
                link = entry.find('atom:id', namespace).text
                
                filtered_papers.append({
                    "title": title,
                    "abstract": summary,
                    "url": link,
                    "publicationDate": published_date.strftime("%Y-%m-%d")
                })
        
        return filtered_papers

    except Exception as e:
        st.error(f"arXiv 검색 중 오류 발생: {e}")
        return []

# --- 3. 제미나이 리포트 작성 ---
def generate_trend_report(papers, keywords, months):
    if not papers:
        return "분석할 논문이 없습니다."

    # 상위 15개만 분석
    target_papers = papers[:15]
    
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] 날짜: {p['publicationDate']} / 제목: {p['title']} / 초록: {p['abstract'][:300]}...\n\n"

    prompt = f"""
    당신은 바이오 에너지 공정 전문가입니다.
    사용자 키워드: {', '.join(keywords)}
    
    아래는 'arXiv(아카이브)'에서 검색된 최근 {months}개월간의 논문 초록입니다.
    이 내용을 바탕으로 한국어 '기술 동향 브리핑'을 작성해주세요.
    
    [작성 포인트]
    1. 🔍 **검색 결과**: "arXiv에서 총 {len(papers)}건의 최신 연구가 검색되었습니다."
    2. 💡 **핵심 요약**: 검색된 연구들의 기술적 특징 요약.
    3. 🚀 **주요 논문 3가지**: 가장 관련성 높은 논문 3개를 뽑아 간단히 설명.
    
    [논문 데이터]
    {combined_text}
    """
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text

# --- 4. 메인 UI ---
st.set_page_config(page_title="ArXiv Bio-Tech Report", layout="wide")
st.title("🔬 최신 바이오 논문 탐색기 (arXiv 버전)")
st.caption("안정적인 arXiv API를 사용하여 끊김 없이 논문을 검색합니다.")

# 사이드바
with st.sidebar:
    st.header("설정")
    
    default_keywords = "Biodiesel\nBiofuel\nSustainable Aviation Fuel"
    
    keywords_input = st.text_area("검색어 (영어, 줄바꿈으로 구분)", value=default_keywords, height=150)
    months = st.slider("검색 기간 (개월)", 1, 24, 12) # 기본 12개월 (arXiv는 데이터가 아주 많진 않으므로 길게 잡음)
    
    search_btn = st.button("검색 시작 🔍", type="primary")

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("검색어를 입력해주세요.")
    else:
        with st.spinner(f"arXiv에서 최근 {months}개월간의 논문을 찾는 중..."):
            papers = get_arxiv_papers(keywords, months)
            
            if not papers:
                st.info("검색 결과가 없습니다. 기간을 늘리거나 검색어를 더 넓게 잡아보세요.")
            else:
                tab1, tab2 = st.tabs(["📊 AI 분석 리포트", "📝 논문 원문 리스트"])
                
                with tab1:
                    st.success(f"성공! {len(papers)}건의 논문을 가져왔습니다.")
                    report = generate_trend_report(papers, keywords, months)
                    st.markdown(report)
                    
                with tab2:
                    for p in papers:
                        with st.expander(f"[{p['publicationDate']}] {p['title']}"):
                            st.markdown(f"**[논문 바로가기 (PDF)]({p['url']})**")
                            st.write(p['abstract'])
