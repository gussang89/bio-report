import streamlit as st
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 및 자동 모델 찾기 ---
def configure_gemini():
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            genai.configure(api_key=api_key)
            
            # [핵심] 사용 가능한 모델 목록을 조회해서 'generateContent' 기능이 있는 첫 번째 모델을 선택
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            
            # 우선순위: 1.5 Flash -> 1.5 Pro -> 1.0 Pro -> 아무거나
            preferred_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-1.0-pro', 'models/gemini-pro']
            
            selected_model = None
            for pref in preferred_models:
                if pref in available_models:
                    selected_model = pref
                    break
            
            # 선호하는 게 없으면 목록의 첫 번째 것 사용
            if not selected_model and available_models:
                selected_model = available_models[0]
                
            return selected_model
            
        else:
            st.error("Secrets에 GOOGLE_API_KEY가 설정되지 않았습니다.")
            return None
    except Exception as e:
        st.error(f"API 설정 중 오류: {e}")
        return None

# 전역 변수로 모델 이름 저장
MODEL_NAME = configure_gemini()

# --- 2. arXiv 논문 검색 함수 ---
def get_arxiv_papers(keywords, months):
    query_parts = [f'all:"{k}"' for k in keywords]
    search_query = " OR ".join(query_parts)
    encoded_query = urllib.parse.quote(search_query)
    
    base_url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results=15&sortBy=submittedDate&sortOrder=descending"
    
    try:
        with urllib.request.urlopen(base_url) as url:
            data = url.read().decode('utf-8')
            
        root = ET.fromstring(data)
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        
        cutoff_date = datetime.now() - timedelta(days=months*30)
        filtered_papers = []
        
        for entry in root.findall('atom:entry', namespace):
            published_str = entry.find('atom:published', namespace).text
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
        st.error(f"arXiv 검색 오류: {e}")
        return []

# --- 3. 제미나이 리포트 작성 ---
def generate_trend_report(papers, keywords, months):
    if not papers:
        return "분석할 논문이 없습니다."
    
    if not MODEL_NAME:
        return "사용 가능한 AI 모델을 찾을 수 없습니다. API 키 권한을 확인해주세요."

    target_papers = papers[:10]
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] Title: {p['title']}\nAbstract: {p['abstract'][:200]}...\n\n"

    prompt = f"""
    당신은 바이오 에너지 전문가입니다.
    키워드: {', '.join(keywords)}
    
    아래 논문 초록을 바탕으로 한국어 '기술 동향 브리핑'을 작성해주세요.
    
    [형식]
    1. 🔍 **결과 요약**: "총 {len(papers)}건 검색됨." (사용 모델: {MODEL_NAME})
    2. 💡 **트렌드**: 주요 연구 주제 요약.
    3. 🚀 **주요 논문**: 핵심 논문 2개 소개.
    
    [데이터]
    {combined_text}
    """
    
    try:
        # 자동으로 찾아낸 모델 이름 사용
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 분석 중 오류 발생 ({MODEL_NAME}): {e}"

# --- 4. 메인 UI ---
st.set_page_config(page_title="ArXiv Bio-Tech Report", layout="wide")
st.title("🔬 최신 바이오 논문 탐색기 (Auto-Model)")

if MODEL_NAME:
    st.caption(f"✅ 연결된 AI 모델: `{MODEL_NAME}`")
else:
    st.error("❌ 사용 가능한 Gemini 모델을 찾지 못했습니다.")

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
        with st.spinner("논문 검색 및 분석 중..."):
            papers = get_arxiv_papers(keywords, months)
            
            if not papers:
                st.info("검색 결과가 없습니다.")
            else:
                st.success(f"완료! {len(papers)}건의 논문을 찾았습니다.")
                report = generate_trend_report(papers, keywords, months)
                st.markdown(report)
                
                with st.expander("논문 리스트 보기"):
                    for p in papers:
                        st.write(f"**[{p['publicationDate']}] {p['title']}**")
                        st.caption(f"[링크]({p['url']})")
