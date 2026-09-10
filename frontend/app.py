"""소상공인 광고 생성 - Streamlit 프론트엔드.

API 계약: docs/api_spec.md (v0.3, 비동기).
  1) POST {API_BASE_URL}/generate            -> 202 { request_id, poll_url }
  2) GET  {API_BASE_URL}/jobs/{request_id}   -> 2초 폴링, status done/failed 까지
  3) 결과의 assets[].url 이미지는 서버측에서 바이트로 받아 표시
"""

from __future__ import annotations

import os
import time

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000/api/v1")
POLL_INTERVAL_S = 2
POLL_TIMEOUT_S = 180

# D9 (한글 라벨 -> enum) 매핑 초안. 최종 확정은 API 담당과 함께.
BUSINESS_LABELS = {
    "포장 식품": "packaged_food",
    "간식·음료": "snack_beverage",
    "반찬·밀키트": "side_dish_meal",
}
TONE_LABELS = {
    "친근하고 재치 있는": ("친근한", "friendly"),
    "전문적이고 신뢰감 있는": ("전문적이고 믿음직한", "informative"),
    "감성적이고 따뜻한": ("감성적이고 따뜻한", "emotional"),
}
CHANNEL_LABELS = {
    "스마트스토어": "smart_store",
    "SNS": "social_media",
    "배달앱": "delivery_app",
    "오프라인 매장": "offline_store",
}
GOAL_LABELS = {
    "신제품 출시": "product_launch",
    "프로모션": "promotion",
    "브랜드 인지도": "brand_awareness",
    "구매 전환": "purchase_conversion",
}


st.set_page_config(page_title="AI 소상공인 광고 생성기", layout="wide")
st.title("📢 소상공인 맞춤형 AI 광고 생성 서비스")
st.write("제품 설명과 광고 조건을 입력하면 AI가 홍보 문구와 배너 이미지를 생성합니다.")

with st.sidebar:
    st.header("⚙️ 광고 설정")
    store_name = st.text_input("상호명", "OO 카페")
    product_label = st.selectbox("상품 종류", list(BUSINESS_LABELS))
    sales_label = st.selectbox("판매 채널", list(CHANNEL_LABELS))
    goal_label = st.selectbox("광고 목적", list(GOAL_LABELS), index=3)
    target_audience = st.text_input("타겟 고객", "20~30대 직장인 및 대학생")
    keywords = st.text_area("핵심 키워드 (쉼표로 구분)", "수제 디저트, 분위기 좋은, 역세권")
    tone_label = st.selectbox("톤앤매너", list(TONE_LABELS))
    outputs = st.multiselect("생성할 결과", ["copy", "banner"], default=["copy", "banner"])
    generate_btn = st.button("✨ 광고 생성하기", type="primary")

product_text = st.text_area(
    "제품 설명 (문구 생성에 필요)",
    "국산 딸기로 만든 300g 수제 딸기잼. 유리병 포장.",
    height=90,
)


def build_payload() -> dict:
    tone, copy_style = TONE_LABELS[tone_label]
    must_include = [k.strip() for k in keywords.split(",") if k.strip()]
    return {
        "text": product_text.strip() or None,
        "outputs": outputs,
        "options": {
            "store_name": store_name or None,
            "business_type": "food_retail",
            "product_category": BUSINESS_LABELS[product_label],
            "sales_channel": CHANNEL_LABELS[sales_label],
            "campaign_goal": GOAL_LABELS[goal_label],
            "target_audience": target_audience or None,
            "tone": tone,
            "copy_style": copy_style,
            "must_include": must_include,
        },
        "source": {"channel": "web"},
    }


def submit_and_wait(payload: dict) -> dict:
    """접수 후 완료까지 폴링. 실패 시 RuntimeError."""

    res = requests.post(f"{API_BASE_URL}/generate", json=payload, timeout=10)
    if res.status_code != 202:
        raise RuntimeError(_error_message(res))
    request_id = res.json()["request_id"]

    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        job = requests.get(f"{API_BASE_URL}/jobs/{request_id}", timeout=10).json()
        if job["status"] == "done":
            return job["result"]
        if job["status"] == "failed":
            raise RuntimeError(job.get("error", {}).get("message", "생성 실패"))
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError("시간 초과: 생성이 완료되지 않았습니다")


def _error_message(res: requests.Response) -> str:
    try:
        return res.json()["error"]["message"]
    except (ValueError, KeyError):
        return f"서버 오류 (상태 코드 {res.status_code})"


def _fetch_image(asset_url: str) -> bytes:
    # asset_url 은 "/api/v1/assets/..." 형태. 브라우저가 아니라 서버측에서 받는다.
    origin = API_BASE_URL.rsplit("/api/v1", 1)[0]
    return requests.get(f"{origin}{asset_url}", timeout=10).content


col1, col2 = st.columns(2)
with col1:
    st.subheader("📋 입력 요약")
    st.info(
        f"- **상호명:** {store_name}\n"
        f"- **상품:** {product_label}\n"
        f"- **채널/목적:** {sales_label} / {goal_label}\n"
        f"- **타겟:** {target_audience}\n"
        f"- **키워드:** {keywords}\n"
        f"- **톤:** {tone_label}"
    )

with col2:
    st.subheader("🎨 생성 결과")
    if not generate_btn:
        st.warning("좌측에서 조건을 입력하고 '광고 생성하기' 를 누르세요.")
    elif not outputs:
        st.error("생성할 결과를 하나 이상 선택하세요.")
    elif "copy" in outputs and not product_text.strip():
        st.error("문구(copy) 생성에는 제품 설명이 필요합니다.")
    else:
        with st.spinner("AI가 매장 맞춤형 광고를 제작 중입니다... (최대 3분)"):
            try:
                result = submit_and_wait(build_payload())
            except requests.exceptions.ConnectionError:
                st.error("API 서버와 통신할 수 없습니다. api 컨테이너 상태를 확인하세요.")
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success("생성 완료!")
                copy_result = result.get("copy")
                if copy_result:
                    st.markdown("**헤드라인 후보**")
                    for line in copy_result["headline_candidates"]:
                        st.write(f"- {line}")
                    st.markdown("**본문 후보**")
                    for line in copy_result["body_candidates"]:
                        st.write(f"- {line}")
                    st.markdown("**CTA 후보**: " + " / ".join(copy_result["cta_candidates"]))

                for asset in result.get("assets", []):
                    st.image(
                        _fetch_image(asset["url"]),
                        caption=f"{asset['type']} ({asset['width']}x{asset['height']})",
                    )

                if result.get("warnings"):
                    st.caption(" · ".join(result["warnings"]))
