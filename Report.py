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
    # 데이터를 많이 주기 위해 검색량을 50개로 늘립니다.
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
                    "title": title, "abstract": summary, "url": link,
                    "publicationDate": published_date.strftime("%Y-%m-%d")
                })
        return filtered_papers
    except Exception as e:
        st.error(f"검색 오류: {e}")
        return []

# --- 3. 제미나이 리포트 작성 (🌟 심층 프롬프트 적용) ---
def generate_trend_report(papers, keywords, months):
    if not papers: return "논문이 없습니다."

    # 리포트의 질을 높이기 위해 상위 30개 논문의 '제목'과 '초록'을 모두 제공합니다.
    target_papers = papers[:30]
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] 제목: {p['title']}\n초록: {p['abstract']}\n\n"

    # [핵심] A4 2장 분량을 뽑아내기 위한 구체적이고 상세한 프롬프트
    prompt = f"""
    당신은 바이오 에너지(Biodiesel, HVO, SAF) 공정 설계 및 최적화를 전문으로 하는 수석 엔지니어입니다.
    아래는 최근 {months}개월간 arXiv에서 검색된 논문 {len(papers)}건의 제목과 초록입니다. (관심 키워드: {', '.join(keywords)})

    이 데이터를 바탕으로 경영진 및 현장 실무진에게 보고할 **A4 2페이지 분량(약 3000자 이상)의 매우 상세하고 깊이 있는 '심층 기술 동향 리포트'**를 작성해주세요. 단순 나열이 아닌, 전문적인 리뷰 논문 수준으로 유기적으로 작성해야 합니다.

    [필수 포함 목차 및 작성 지침]
    
    1. 📝 **Executive Summary (거시적 트렌드 총평)**
       - 수집된 논문들을 관통하는 핵심 기술 트렌드는 무엇인지 3~4문단으로 길고 상세하게 서술.
    
    2. 🔬 **주요 기술 및 공정 트렌드 심층 분석**
       - 기술 카테고리를 3~4개(예: 신규 촉매 및 반응 효율, 전처리 기술, 대체 원료 탐색 등)로 나누어 각 분야의 연구 동향을 깊이 있게 분석.
    
    3. 💡 **현업 공정 적용 및 최적화 인사이트**
       - 연중무휴(24/7)로 가동되는 연속식 공정(Continuous Process)의 안정성을 높이거나, 수율(Yield) 개선, 유틸리티 비용(전력, 스팀 등) 절감에 직접적으로 적용해 볼 수 있는 실무적 아이디어를 도출할 것.
       - 가능하다면 모노글리세라이드(MG) 저감 등 품질 향상과 연결 지을 것.
    
    4. 🏆 **핵심 논문 5선 심층 리뷰**
       - 산업적 활용 가치가 가장 높은 논문 5개를 선정하여, 각 논문의 1) 연구 목적, 2) 적용된 핵심 기술 및 수치적 성과, 3) 한계점 및 시사점을 각각 상세히 리뷰할 것.

    [논문 데이터]
    {combined_text}
    """
    
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except Exception as e:
        return f"⚠️ 모델 목록을 가져오지 못했습니다: {e}"

    if not available_models:
        return "⚠️ 사용 가능한 모델이 하나도 없습니다."

    error_logs = []
    # 텍스트를 길게 뽑아야 하므로, 더 똑똑한 모델인 1.5-pro를 먼저 시도하고 flash로 넘어갑니다.
    preferred_order = ['models/gemini-1.5-pro', 'models/gemini-1.5-flash', 'models/gemini-pro']
    sorted_models = [m for m in preferred_order if m in available_models] + [m for m in available_models if m not in preferred_order]

    for model_name in sorted_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return f"*(✅ `{model_name}` 모델로 생성된 심층 분석 리포트)*\n\n" + response.text
        except Exception as e:
            error_logs.append(f"- {model_name} 실패: {e}")
            continue

    error_summary = "\n".join(error_logs)
    return f"⚠️ 분석 실패.\n\n[원인]\n{error_summary}"

# --- 4. 메인 UI ---
st.set_page_config(page_title="Bio-Tech Deep Report", layout="wide")
st.title("🌿 바이오 기술 심층 트렌드 리포트")
st.caption("AI가 최신 논문의 초록을 모두 읽고 A4 2페이지 분량의 전문 리포트를 작성합니다. (생성에 30초~1분 정도 소요될 수 있습니다.)")

if not configure_gemini():
    st.error("❌ Secrets에 GOOGLE_API_KEY 설정이 필요합니다.")

with st.sidebar:
    st.header("설정")
    default_keywords = "Biodiesel\nSustainable Aviation Fuel\nTransesterification\nHVO\nBiomass"
    keywords_input = st.text_area("검색어 (영어)", value=default_keywords, height=200)
    months = st.slider("검색 기간 (개월)", 1, 24, 12)
    search_btn = st.button("심층 리포트 생성 🚀", type="primary")

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    with st.spinner("논문을 수집하고, AI가 심층 리포트를 작성 중입니다. 잠시만 기다려주세요..."):
        papers = get_arxiv_papers(keywords, months)
        
        if not papers:
            st.warning("검색 결과가 없습니다.")
        else:
            st.success(f"성공! {len(papers)}건의 논문을 기반으로 리포트를 생성했습니다.")
            
            # 리포트가 길어지므로 컬럼을 나누지 않고 탭으로 화면을 넓게 씁니다.
            tab1, tab2 = st.tabs(["📊 AI 심층 트렌드 리포트", "📝 논문 원문 리스트"])
            
            with tab1:
                report = generate_trend_report(papers, keywords, months)
                st.markdown(report)
            
            with tab2:
                for p in papers:
                    with st.expander(f"{p['title']} ({p['publicationDate']})"):
                        st.write(p['abstract'])
                        st.markdown(f"**[원문 PDF 링크]({p['url']})**")
