import streamlit as st
import requests

# 페이지 기본 설정
st.set_page_config(page_title="AI 소상공인 광고 생성기", layout="wide")

st.title("📢 소상공인 맞춤형 AI 광고 생성 서비스")
st.write("원하는 광고 조건을 입력하고 AI가 추천하는 홍보 문구와 이미지를 생성해 보세요.")

# 1. 사이드바 설정 및 입력 폼
with st.sidebar:
    st.header("⚙️ 광고 설정")
    store_name = st.text_input("상호명", "OO 카페")
    business_type = st.selectbox("업종 선택", ["카페/디저트", "음식점", "뷰티/헤어", "기타 소상공인"])
    target_audience = st.text_input("타겟 고객", "20~30대 직장인 및 대학생")
    keywords = st.text_area("핵심 키워드", "수제 디저트, 분위기 좋은, 역세권")
    tone_manner = st.selectbox("톤앤매너", ["친근하고 재치 있는", "전문적이고 신뢰감 있는", "감성적이고 따뜻한"])
    
    generate_btn = st.button("✨ 광고 생성하기", type="primary")

# 2. 메인 화면 레이아웃 (st.columns 활용)
col1, col2 = st.columns(2)

with col1:
    st.subheader("📋 입력된 조건 요약")
    st.info(f"""
    - **상호명:** {store_name}
    - **업종:** {business_type}
    - **타겟:** {target_audience}
    - **키워드:** {keywords}
    - **분위기:** {tone_manner}
    """)

with col2:
    st.subheader("🎨 생성된 광고 결과")
    # 3. 상태 관리 및 액션 버튼 (st.button 및 st.spinner)
    if generate_btn:
        with st.spinner("AI가 매장 맞춤형 광고를 제작 중입니다..."):
            try:
                payload = {
                    "store_name": store_name,
                    "business_type": business_type,
                    "target_audience": target_audience,
                    "keywords": keywords,
                    "tone_manner": tone_manner
                }
                
                # 백엔드 API 호출 (Docker 내부 네트워크 주소 사용)
                response = requests.post("http://api:8000/api/v1/generate", json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    st.success("광고 생성이 완료되었습니다!")
                    st.text_area("AI 홍보 문구 (Copy)", result.get("ad_text", ""), height=100)
                    st.image(result.get("image_url", ""), caption="생성된 광고 이미지 미리보기")
                else:
                    st.error(f"서버 오류가 발생했습니다. (상태 코드: {response.status_code})")
                    
            except requests.exceptions.ConnectionError:
                st.error("백엔드 서버와 통신할 수 없습니다. API 컨테이너가 실행 중인지 확인해주세요.")
            except requests.exceptions.Timeout:
                st.error("요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")
    else:
        st.warning("좌측 사이드바에서 조건을 입력하고 '광고 생성하기' 버튼을 눌러주세요.")