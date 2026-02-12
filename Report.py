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

# --- 2. arXiv 논문 검색 함수 (안정적인 API) ---
def get_arxiv_papers(keywords, months):
    # arXiv API 쿼리 생성
    query_parts = [f'all:"{k}"' for k in keywords]
    search_query = " OR ".join(query_parts)
    encoded_query = urllib.parse.quote(search_query)
    
    # 최신순 정렬, 20개 가져오기
    base_url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending"
    
    try:
        with urllib.request.urlopen(base_url) as url:
            data = url.read().decode('utf-8')
            
        root = ET.fromstring(data)
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        
        cutoff_date = datetime.now() - timedelta(days=months*30)
        filtered_papers = []
        
        for entry in root.findall('atom:entry', namespace):
            published_str = entry.find('atom:published', namespace).text
            # 날짜 파싱 (2024-02-12T14:00:00Z)
            published_date = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ")
            
            if published_date >= cutoff_date:
                title = entry.find('atom:title', namespace).text.strip().replace('\n', ' ')
                summary = entry.find('atom:summary', namespace).text.strip().replace('\n', ' ')
                link_id = entry.find('atom:id', namespace).text
                
                filtered_papers.append({
                    "title": title,
                    "abstract": summary,
                    "url": link_id,
                    "publicationDate": published_date.strftime("%Y-%m-%d")
                })
        
        return filtered_papers

    except Exception as e:
        st.error(f"arXiv 검색 중 오류 발생: {e}")
        return []

# --- 3. 제미나이 리포트 작성 (모델 변경됨) ---
def generate_trend_report(papers, keywords, months):
    if not papers:
        return "분석할 논문이 없습니다."

    # Gemini Pro는 입력 제한이 있을 수 있으므로 상위 10개만 분석
    target_papers = papers[:10]
    
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] Title: {p['title']}\nAbstract: {p['abstract'][:200]}...\n\n"

    prompt = f"""
    당신은 숙련된 바이오 에너지 연구원입니다.
    사용자 키워드: {', '.join(keywords)}
    
    아래는 arXiv에서 검색된 최근 {months}개월간의 논문 요약본입니다.
    이 내용을 바탕으로 한국어로 '최신 기술 동향 브리핑'을 작성해주세요.
    
    [작성 형식]
    1. 🔍 **검색 결과**: "총 {len(papers)}건의 논문이 검색되었습니다."
    2. 💡 **기술 트렌드 요약**: 검색된 연구들의 주요 주제와 흐름을 3줄로 요약.
    3. 🚀 **주목할 논문**: 가장 흥미로운 논문 2~3개를 골라 제목과 내용을 간단히 소개.
    
    [논문 데이터]
    {combined_text}
    """
    
    try:
        # [수정] 가장 호환성이 좋은 'gemini-pro' 모델 사용
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 분석 중 오류가 발생했습니다: {e}"

# --- 4. 메인 UI ---
st.set_page_config(page_title="ArXiv Bio-Tech Report", layout="wide")
st.title("🔬 최신 바이오 논문 탐색기 (Stable Ver.)")
st.caption("arXiv 데이터베이스와 Google Gemini Pro를 사용합니다.")

with st.sidebar:
    st.header("설정")
    default_keywords = "Biodiesel\nBiofuel\nSustainable Aviation Fuel"
    keywords_input = st.text_area("검색어 (영어)", value=default_keywords, height=150)
    months = st.slider("검색 기간 (개월)", 1, 24, 12)
    search_btn = st.button("검색 시작 🔍", type="primary")

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("검색어를 입력해주세요.")
    else:
        with st.spinner("논문을 검색하고 분석 중입니다..."):
            papers = get_arxiv_papers(keywords, months)
            
            if not papers:
                st.info("검색 결과가 없습니다. 기간을 늘리거나 검색어를 변경해보세요.")
            else:
                tab1, tab2 = st.tabs(["📊 AI 분석 리포트", "📝 논문 원문 리스트"])
                
                with tab1:
                    st.success("분석 완료!")
                    report = generate_trend_report(papers, keywords, months)
                    st.markdown(report)
                    
                with tab2:
                    for p in papers:
                        with st.expander(f"[{p['publicationDate']}] {p['title']}"):
                            st.markdown(f"**[논문 바로가기]({p['url']})**")
                            st.write(p['abstract'])
