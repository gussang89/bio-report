import streamlit as st
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import google.generativeai as genai
from datetime import datetime, timedelta

# --- 1. 구글 제미나이 설정 ---
def configure_gemini():
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        return True
    return False

# --- 2. arXiv 논문 검색 함수 ---
def get_arxiv_papers(keywords, months):
    query_parts = []
    for k in keywords:
        clean_k = k.strip()
        if not clean_k: continue
        query_parts.append(f'(ti:{clean_k} OR abs:{clean_k})')
    
    if not query_parts: return []

    search_query = " OR ".join(query_parts)
    encoded_query = urllib.parse.quote(search_query)
    base_url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results=30&sortBy=submittedDate&sortOrder=descending"
    
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
                    "title": title, "abstract": summary, "url": link,
                    "publicationDate": published_date.strftime("%Y-%m-%d")
                })
        return filtered_papers
    except Exception as e:
        st.error(f"검색 오류: {e}")
        return []

# --- 3. 제미나이 리포트 작성 (🌟핵심: 릴레이 테스트) ---
def generate_trend_report(papers, keywords):
    if not papers: return "논문이 없습니다."

    target_papers = papers[:15]
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] {p['title']}\n"

    prompt = f"""
    당신은 바이오 에너지 공정 전문가입니다. 키워드: {', '.join(keywords)}
    아래 {len(papers)}건의 최신 논문 제목들을 보고 기술 트렌드를 분석해주세요.
    
    1. 🔍 **요약**: "총 {len(papers)}건의 최신 연구 분석"
    2. 📈 **주요 토픽**: 가장 많이 연구되고 있는 분야 3가지 키워드.
    3. 💡 **인사이트**: 제목들로 보아 현재 연구의 흐름이 어디로 가고 있는지 한 문단 설명.
    
    [논문 리스트]
    {combined_text}
    """
    
    # 1. 내 API 키로 쓸 수 있는 모든 모델 목록 가져오기
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except Exception as e:
        return f"⚠️ 모델 목록을 가져오지 못했습니다. API 키를 확인해주세요: {e}"

    if not available_models:
        return "⚠️ 사용 가능한 모델이 하나도 없습니다."

    # 2. 목록에 있는 모델을 하나씩 순서대로 전부 시도해보기
    error_logs = []
    for model_name in available_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            # 성공하면 결과와 함께 어떤 모델이 성공했는지 알려주고 바로 종료!
            return f"*(✅ `{model_name}` 모델로 분석 성공!)*\n\n" + response.text
        except Exception as e:
            # 실패하면 로그만 남기고 다음 모델로 넘어감
            error_logs.append(f"- {model_name} 실패: {e}")
            continue

    # 3. 모든 모델이 다 실패했을 때만 에러 원인 총출력
    error_summary = "\n".join(error_logs)
    return f"⚠️ 보유하신 API 키의 모든 모델이 분석에 실패했습니다.\n\n[실패 원인들]\n{error_summary}"

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech ArXiv Finder", layout="wide")
st.title("🔬 바이오 논문 탐색기 (Auto-Healing Ver.)")

if not configure_gemini():
    st.error("❌ Secrets에 GOOGLE_API_KEY 설정이 필요합니다.")

with st.sidebar:
    st.header("설정")
    default_keywords = "Biodiesel\nBiofuel\nSAF\nBiomass\nHydrotreatment"
    keywords_input = st.text_area("검색어 (영어)", value=default_keywords, height=200)
    months = st.slider("검색 기간 (개월)", 1, 24, 12)
    search_btn = st.button("검색 시작 🔍", type="primary")

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    with st.spinner("논문을 찾고 모든 모델을 테스트 중입니다..."):
        papers = get_arxiv_papers(keywords, months)
        
        if not papers:
            st.warning("검색 결과가 없습니다.")
        else:
            st.success(f"성공! {len(papers)}건의 논문을 찾았습니다.")
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📊 AI 트렌드 요약")
                report = generate_trend_report(papers, keywords)
                st.markdown(report)
            
            with col2:
                st.subheader("📝 논문 리스트")
                for p in papers:
                    with st.expander(f"{p['title']}"):
                        st.caption(p['publicationDate'])
                        st.markdown(f"[링크]({p['url']})")
