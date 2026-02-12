import streamlit as st
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 ---
def configure_gemini():
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            genai.configure(api_key=api_key)
            
            available_models = []
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
            except:
                pass # 모델 리스트 조회 실패 시 기본값 사용

            # 우선순위: 1.5 Flash (빠름) -> 1.5 Pro (똑똑함) -> Pro (무난함)
            preferred_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']
            
            selected_model = 'models/gemini-pro' # 기본값
            for pref in preferred_models:
                if pref in available_models:
                    selected_model = pref
                    break
            return selected_model
        else:
            st.error("Secrets에 GOOGLE_API_KEY가 없습니다.")
            return None
    except Exception as e:
        st.error(f"API 설정 오류: {e}")
        return None

MODEL_NAME = configure_gemini()

# --- 2. arXiv 논문 검색 함수 (검색량 대폭 증가 수정) ---
def get_arxiv_papers(keywords, months):
    # [변경점] 따옴표("")를 제거하고 단순 키워드 매칭으로 변경하여 검색 범위를 넓힘
    # 제목(ti) 또는 초록(abs)에 키워드가 있으면 가져오도록 설정
    # 예: (ti:biodiesel OR abs:biodiesel)
    
    query_parts = []
    for k in keywords:
        # 공백이 있는 검색어(예: Bio fuel)는 괄호로 묶어줌
        clean_k = k.strip()
        query_parts.append(f'(ti:{clean_k} OR abs:{clean_k})')
    
    # 모든 키워드를 OR로 연결 (하나라도 걸리면 나옴)
    search_query = " OR ".join(query_parts)
    encoded_query = urllib.parse.quote(search_query)
    
    # 검색 개수도 30개 -> 50개로 늘림
    base_url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results=50&sortBy=submittedDate&sortOrder=descending"
    
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
        st.error(f"검색 오류: {e}")
        return []

# --- 3. 제미나이 리포트 작성 ---
def generate_trend_report(papers, keywords, months):
    if not papers: return "논문이 없습니다."
    if not MODEL_NAME: return "모델 오류."

    # 논문이 많아졌으니 상위 15개 분석
    target_papers = papers[:15]
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] {p['title']}\n"

    prompt = f"""
    당신은 바이오 에너지 공정 엔지니어입니다.
    키워드: {', '.join(keywords)}
    
    최근 {months}개월간 arXiv에서 검색된 {len(papers)}건의 논문 제목들을 보고 트렌드를 분석해주세요.
    (내용은 제목으로 유추하세요)
    
    1. 🔍 **검색 현황**: "총 {len(papers)}건 발견됨 (모델: {MODEL_NAME})"
    2. 📈 **주요 키워드**: 제목에서 자주 보이는 기술 용어 3가지 (예: Catalytic, Pyrolysis 등)
    3. 💡 **인사이트**: 연구 흐름이 어디로 가고 있는지 한 문단 요약.
    
    [논문 제목 리스트]
    {combined_text}
    """
    
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 분석 실패: {e}"

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech ArXiv Finder", layout="wide")
st.title("🔬 바이오 논문 탐색기 (확장 검색 Ver.)")
st.caption("제목과 초록을 넓게 검색하여 놓치는 논문을 최소화합니다.")

if MODEL_NAME:
    st.caption(f"✅ AI 연결됨: `{MODEL_NAME}`")
else:
    st.error("❌ AI 연결 실패")

with st.sidebar:
    st.header("설정")
    # [개선] 기본 검색어를 좀 더 잘 나오는 것들로 세팅
    default_keywords = "Biodiesel\nBiofuel\nSAF\nBiomass\nHydrotreatment\nTransesterification"
    keywords_input = st.text_area("검색어 (짧은 단어 추천)", value=default_keywords, height=200)
    months = st.slider("검색 기간 (개월)", 1, 24, 12)
    search_btn = st.button("검색 시작 🔍", type="primary")

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    if not keywords:
        st.warning("검색어를 입력해주세요.")
    else:
        with st.spinner("더 넓은 범위에서 논문을 찾고 있습니다..."):
            papers = get_arxiv_papers(keywords, months)
            
            if not papers:
                st.warning("검색 결과가 0건입니다. 'Biodiesel' 같은 아주 단순한 단어로 시도해보세요.")
            else:
                st.success(f"성공! {len(papers)}건의 논문을 찾았습니다.")
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📊 AI 트렌드 요약")
                    report = generate_trend_report(papers, keywords, months)
                    st.markdown(report)
                
                with col2:
                    st.subheader("📝 논문 리스트")
                    for p in papers:
                        with st.expander(f"{p['title']}"):
                            st.caption(p['publicationDate'])
                            st.write(p['abstract'])
                            st.markdown(f"[링크]({p['url']})")
