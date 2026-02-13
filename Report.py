import streamlit as st
import urllib.request
import urllib.parse
import json
import re
import google.generativeai as genai
from datetime import datetime, timedelta
import io
from docx import Document
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# --- 1. 구글 제미나이 설정 ---
def configure_gemini():
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
        return True
    return False

# --- 2. 검색 함수들 ---

# [1] Europe PMC (해외 논문)
def get_epmc_papers(keywords, months):
    query_parts = [f'({k.strip()})' for k in keywords if k.strip()]
    if not query_parts: return []
    keyword_query = " OR ".join(query_parts)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months*30)
    date_query = f'FIRST_PDATE:[{start_date.strftime("%Y-%m-%d")} TO {end_date.strftime("%Y-%m-%d")}]'
    full_query = f"({keyword_query}) AND ({date_query})"
    encoded_query = urllib.parse.quote(full_query)
    base_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={encoded_query}&format=json&resultType=core&pageSize=30"
    
    try:
        req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
        filtered_papers = []
        for p in data.get('resultList', {}).get('result', []):
            title = p.get('title', '')
            abstract = re.sub('<[^<]+>', '', p.get('abstractText', ''))
            doi = p.get('doi')
            link = f"https://doi.org/{doi}" if doi else ""
            if title and abstract:
                filtered_papers.append({"title": title, "abstract": abstract, "url": link, "date": p.get('firstPublicationDate', '')})
        return filtered_papers
    except Exception as e:
        return []

# [2] Google News RSS (국내외 뉴스 - API 키 필요 없음!)
def get_google_news(keywords, months):
    query_parts = [f'"{k.strip()}"' for k in keywords if k.strip()]
    if not query_parts: return []
    search_query = " OR ".join(query_parts)
    encoded_query = urllib.parse.quote(search_query)
    
    # 한국(ko) 및 미국(en-US) 뉴스 동시 검색
    urls = [
        f"https://news.google.com/rss/search?q={encoded_query}+when:{months}m&hl=ko&gl=KR&ceid=KR:ko",
        f"https://news.google.com/rss/search?q={encoded_query}+when:{months}m&hl=en-US&gl=US&ceid=US:en"
    ]
    
    news_list = []
    for url in urls:
        source_label = "🇰🇷 국내" if "hl=ko" in url else "🌍 해외"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('./channel/item'):
                title = item.find('title').text
                link = item.find('link').text
                pubDate = item.find('pubDate').text
                
                # 날짜 변환
                try:
                    dt = parsedate_to_datetime(pubDate)
                    date_str = dt.strftime("%Y-%m-%d")
                except:
                    date_str = pubDate
                
                news_list.append({
                    "title": title, 
                    "abstract": "상세 내용은 원문 링크를 참고하세요.", # RSS는 요약이 매우 짧아 제목 위주로 활용
                    "url": link, 
                    "date": date_str,
                    "source": source_label
                })
        except Exception as e:
            continue
            
    # 중복 제거 (링크 기준) 및 최신순 정렬
    unique_news = {n['url']: n for n in news_list}.values()
    sorted_news = sorted(unique_news, key=lambda x: x['date'], reverse=True)
    return list(sorted_news)

# --- 3. AI 리포트 생성 (통합 함수) ---
def generate_ai_report(items, keywords, context_type):
    if not items: return "분석할 데이터가 없습니다."
    
    data_text = ""
    for i, item in enumerate(items[:30]): # 뉴스 제목이 짧으므로 30개까지 분석
        prefix = f"[{item.get('source', '')}] " if 'source' in item else ""
        data_text += f"[{i+1}] {prefix}제목: {item['title']} (일자: {item['date']})\n초록: {item['abstract'][:200]}\n\n"

    if context_type == "Global_Papers":
        role_description = "글로벌 바이오 에너지 공정 엔지니어"
        focus_point = """
        1. 🔬 **기술 트렌드 요약**: 핵심 공정 및 최신 기술 동향
        2. 🏭 **공정 최적화 인사이트**: 수율 개선 및 유틸리티 절감 시사점
        3. 🏆 **주요 논문 3선**: 눈여겨볼 핵심 논문 요약 (각 항목 끝에 주석 형태로 원문 링크 번호 표기)
        """
    else: # News
        role_description = "바이오 에너지 산업 및 시장 애널리스트"
        focus_point = """
        1. 📰 **시장 및 산업 동향**: 글로벌 및 국내 바이오 연료(SAF, HVO 등) 시장의 거시적 흐름
        2. 🏛️ **정책 및 투자 동향**: 각국 정부의 규제 변화나 주요 기업의 투자/상용화 발표
        3. 💡 **시사점**: 현업에서 주목해야 할 리스크 및 기회 요인 (각 항목 끝에 주석 형태로 뉴스 원문 번호 표기)
        """

    prompt = f"""
    당신은 {role_description}입니다. 키워드: {', '.join(keywords)}
    
    아래 수집된 데이터를 바탕으로 **'심층 리포트'**를 A4 1~2페이지 분량으로 작성하세요.
    *주의사항: AI의 추론이 들어간 부분은 '추정' 또는 '예상'임을 명확히 밝히고, 기재된 사실은 제공된 데이터(주석 번호)를 근거로 작성하세요.

    [작성 포인트]
    {focus_point}

    [수집된 데이터]
    {data_text}
    """
    
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        preferred_order = ['models/gemini-1.5-pro', 'models/gemini-1.5-flash', 'models/gemini-pro']
        sorted_models = [m for m in preferred_order if m in available_models] + [m for m in available_models if m not in preferred_order]

        for model_name in sorted_models:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return response.text
            except: continue
        return "AI 분석 실패."
    except: return "모델 설정 오류."

# --- 4. Word 생성 ---
def create_word_doc(report_text, keywords, title):
    doc = Document()
    doc.add_heading(title, 0)
    doc.add_paragraph(f"생성일자: {datetime.now().strftime('%Y-%m-%d')}")
    doc.add_paragraph("-" * 50)
    for line in report_text.split('\n'):
        if line.startswith('###'): doc.add_heading(line.replace('###', '').strip(), level=3)
        elif line.startswith('##'): doc.add_heading(line.replace('##', '').strip(), level=2)
        elif line.startswith('#'): doc.add_heading(line.replace('#', '').strip(), level=1)
        elif line.startswith('**') and line.endswith('**'): 
            p = doc.add_paragraph()
            p.add_run(line.replace('**', '')).bold = True
        else: doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- 5. 메인 UI ---
st.set_page_config(page_title="Bio-Energy Tracker", layout="wide")
st.title("🔬 바이오 에너지 트래커 (논문 & 뉴스)")

if not configure_gemini():
    st.error("❌ Google API Key 설정 필요")

with st.sidebar:
    st.header("🔍 검색 설정")
    default_keywords = "Biodiesel\nSustainable Aviation Fuel\nSAF\nHVO"
    keywords_input = st.text_area("검색어 (영어 권장)", value=default_keywords, height=150)
    months = st.slider("검색 기간 (개월)", 1, 24, 6) # 뉴스는 최신 동향이 중요하므로 기본 6개월
    search_btn = st.button("검색 시작 🚀", type="primary")

# 탭 구성
tab_global, tab_news = st.tabs(["🌍 해외 논문 (기술/공정)", "📰 국내외 뉴스 (시장/정책)"])

if search_btn:
    keywords = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    
    # --- [탭 1] 해외 논문 처리 ---
    with tab_global:
        with st.spinner("해외 전문 DB에서 공정/기술 논문을 분석 중입니다..."):
            epmc_papers = get_epmc_papers(keywords, months)
            if not epmc_papers:
                st.warning("검색된 해외 논문이 없습니다.")
            else:
                report_global = generate_ai_report(epmc_papers, keywords, "Global_Papers")
                docx_global = create_word_doc(report_global, keywords, "🌿 해외 바이오 공정 기술 리포트")
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.download_button("📥 논문 리포트 다운로드", docx_global, "Tech_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key="btn1")
                
                st.divider()
                sub_tab1, sub_tab2 = st.tabs(["📊 AI 기술 분석 리포트", "📝 원문 리스트"])
                with sub_tab1: st.markdown(report_global)
                with sub_tab2:
                    for i, p in enumerate(epmc_papers):
                        with st.expander(f"[{i+1}] {p['title']} ({p['date']})"):
                            st.write(p['abstract'])
                            st.markdown(f"[원문 링크]({p['url']})")

    # --- [탭 2] 국내외 뉴스 처리 ---
    with tab_news:
        with st.spinner("구글 뉴스에서 국내 및 해외 시장/정책 동향을 수집 중입니다..."):
            news_items = get_google_news(keywords, months)
            if not news_items:
                st.warning("관련 뉴스가 검색되지 않았습니다.")
            else:
                report_news = generate_ai_report(news_items, keywords, "News")
                docx_news = create_word_doc(report_news, keywords, "📰 국내외 바이오 시장 동향 리포트")
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.download_button("📥 뉴스 리포트 다운로드", docx_news, "News_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key="btn2")
                
                st.divider()
                sub_tab1, sub_tab2 = st.tabs(["📊 AI 시장 분석 리포트", "📰 뉴스 원문 리스트"])
                with sub_tab1: 
                    st.info("💡 **안내:** 이 리포트는 수집된 뉴스 기사의 제목을 근거로 작성되었으며, AI의 추론이 포함된 부분은 별도로 명시하였습니다.")
                    st.markdown(report_news)
                with sub_tab2:
                    for i, n in enumerate(news_items):
                        with st.expander(f"[{i+1}] {n['source']} | {n['title']} ({n['date']})"):
                            st.markdown(f"**[기사 바로가기]({n['url']})**")
