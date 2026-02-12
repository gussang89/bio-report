import streamlit as st
import urllib.request
import urllib.parse
import json
import re
import google.generativeai as genai
from datetime import datetime, timedelta
import io
from docx import Document

# --- 1. 구글 제미나이 설정 ---
def configure_gemini():
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        return True
    return False

# --- 2. 생명/화학공학 전문 DB (Europe PMC) 검색 함수 ---
def get_epmc_papers(keywords, months):
    query_parts = []
    for k in keywords:
        clean_k = k.strip()
        if not clean_k: continue
        # 각 줄의 검색어를 괄호로 묶어 정확도를 높임
        query_parts.append(f'({clean_k})')
    
    if not query_parts: return []

    keyword_query = " OR ".join(query_parts)
    
    # 날짜 필터링 (최근 N개월)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months*30)
    date_query = f'FIRST_PDATE:[{start_date.strftime("%Y-%m-%d")} TO {end_date.strftime("%Y-%m-%d")}]'
    
    # 최종 쿼리 조합
    full_query = f"({keyword_query}) AND ({date_query})"
    encoded_query = urllib.parse.quote(full_query)
    
    # 초록(Abstract)이 포함된 core 데이터를 50개까지 가져옵니다.
    base_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={encoded_query}&format=json&resultType=core&pageSize=50"
    
    try:
        # Europe PMC는 차단이 거의 없지만, User-Agent를 넣어 안전하게 요청합니다.
        req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        filtered_papers = []
        results = data.get('resultList', {}).get('result', [])
        
        for p in results:
            title = p.get('title', '')
            abstract = p.get('abstractText', '')
            pub_date = p.get('firstPublicationDate', '')
            doi = p.get('doi')
            pmid = p.get('pmid')
            
            # DOI가 있으면 최우선으로, 없으면 PMC 자체 링크 사용
            link = f"https://doi.org/{doi}" if doi else (f"https://europepmc.org/article/MED/{pmid}" if pmid else "")
            
            # 제목과 초록이 모두 존재하는 유효한 논문만 필터링
            if title and abstract and link:
                # 데이터에 섞여 있는 HTML 태그(<b>, <i> 등) 깔끔하게 제거
                clean_abstract = re.sub('<[^<]+>', '', abstract)
                filtered_papers.append({
                    "title": title, "abstract": clean_abstract, "url": link,
                    "publicationDate": pub_date
                })
        return filtered_papers
    except Exception as e:
        st.error(f"Europe PMC 검색 오류: {e}")
        return []

# --- 3. 제미나이 심층 리포트 작성 ---
def generate_trend_report(papers, keywords, months):
    if not papers: return "논문이 없습니다."

    target_papers = papers[:30]
    combined_text = ""
    for i, p in enumerate(target_papers):
        combined_text += f"[{i+1}] 제목: {p['title']}\n초록: {p['abstract']}\n\n"

    prompt = f"""
    당신은 바이오 에너지(Biodiesel, HVO, SAF) 공정 설계 및 최적화를 전문으로 하는 수석 엔지니어입니다.
    아래는 최근 {months}개월간 화학/바이오 전문 DB에서 검색된 논문 {len(papers)}건의 제목과 초록입니다. (관심 키워드: {', '.join(keywords)})

    이 데이터를 바탕으로 경영진 및 현장 실무진에게 보고할 **A4 2페이지 분량(약 3000자 이상)의 매우 상세하고 깊이 있는 '심층 기술 동향 리포트'**를 작성해주세요.

    [필수 포함 목차 및 작성 지침]
    1. 📝 **Executive Summary (거시적 트렌드 총평)**
    2. 🔬 **주요 기술 및 공정 트렌드 심층 분석** (카테고리별 세분화)
    3. 💡 **현업 공정 적용 및 최적화 인사이트** (수율 개선, 유틸리티 비용 절감, 품질 향상 등 실무적 아이디어)
    4. 🏆 **핵심 논문 5선 심층 리뷰** (목적, 성과, 시사점)

    [논문 데이터]
    {combined_text}
    """
    
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except Exception as e:
        return f"⚠️ 모델 목록을 가져오지 못했습니다: {e}"

    if not available_models: return "⚠️ 사용 가능한 모델이 없습니다."

    preferred_order = ['models/gemini-1.5-pro', 'models/gemini-1.5-flash', 'models/gemini-pro']
    sorted_models = [m for m in preferred_order if m in available_models] + [m for m in available_models if m not in preferred_order]

    for model_name in sorted_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            continue
    return "⚠️ 분석 실패."

# --- 4. Word 파일 생성 함수 ---
def create_word_doc(report_text, keywords):
    doc = Document()
    doc.add_heading('🌿 바이오 공정 기술 심층 트렌드 리포트', 0)
    doc.add_paragraph(f"생성일자: {datetime.now().strftime('%Y-%m-%d')}")
    doc.add_paragraph(f"검색 키워드: {', '.join(keywords)}")
    doc.add_paragraph("-" * 50)
    
    for line in report_text.split('\n'):
        if line.startswith('###'):
            doc.add_heading(line.replace('###', '').strip(), level=3)
        elif line.startswith('##'):
            doc.add_heading(line.replace('##', '').strip(), level=2)
        elif line.startswith('#'):
            doc.add_heading(line.replace('#', '').strip(), level=1)
        elif line.startswith('**') and line.endswith('**'):
            p = doc.add_paragraph()
            p.add_run(line.replace('**', '')).bold = True
        else:
            doc.add_paragraph(line)
            
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- 5. 메인 UI ---
st.set_page_config(page_title="Bio-Process Deep Report", layout="wide")
st.title("🌿 바이오 공정 기술 심층 트렌드 리포트")
st.caption("생명과학/화학공학 전문 DB(Europe PMC)를 사용하여 관련성 높은 논문만 엄선합니다.")

if not configure_gemini():
    st.error("❌ Secrets에 GOOGLE_API_KEY 설정이 필요합니다.")

with st.sidebar:
    st.header("설정")
    # 화학 공정에 맞게 기본 검색어 최적화
    default_keywords = "Biodiesel production\nSustainable Aviation Fuel\nHydrotreated Vegetable Oil\nTransesterification catalyst\nCavitation mixing"
    keywords_input = st.text_area("검색어 (영어)", value=default_keywords, height=200)
    months = st.slider("검색 기간 (개월)", 1, 24, 12)
    search_btn = st.button("심층 리포트 생성 🚀", type="primary")

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    with st.spinner("전문 DB에서 논문을 수집하고, AI가 분석 중입니다..."):
        papers = get_epmc_papers(keywords, months)
        
        if not papers:
            st.warning("검색 결과가 없습니다. 검색어를 약간 수정해보세요.")
        else:
            st.success(f"성공! 관련도 높은 논문 {len(papers)}건을 기반으로 리포트를 생성했습니다.")
            
            report = generate_trend_report(papers, keywords, months)
            docx_file = create_word_doc(report, keywords)
            
            st.download_button(
                label="📥 Word 파일(.docx)로 리포트 다운로드",
                data=docx_file,
                file_name=f"Bio_Process_Report_{datetime.now().strftime('%Y%m%d')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary"
            )
            
            st.divider()
            
            tab1, tab2 = st.tabs(["📊 AI 심층 트렌드 리포트", "📝 논문 원문 리스트"])
            
            with tab1:
                st.markdown(report)
            
            with tab2:
                for p in papers:
                    with st.expander(f"{p['title']} ({p['publicationDate']})"):
                        st.write(p['abstract'])
                        st.markdown(f"**[원문 링크 (DOI/PMC)]({p['url']})**")
