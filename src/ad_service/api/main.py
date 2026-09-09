from fastapi import FastAPI
from pydantic import BaseModel

# 1. Pydantic 스키마 정의
class AdRequest(BaseModel):
    store_name: str
    business_type: str
    target_audience: str
    keywords: str
    tone_manner: str

class AdResponse(BaseModel):
    ad_text: str
    image_url: str

# 2. FastAPI 앱 초기화
app = FastAPI(title="AI Ad Service API")

# 3. 광고 생성 엔드포인트 구현
@app.post("/api/v1/generate", response_model=AdResponse)
def generate_advertisement(request: AdRequest):
    generated_text = f"[{request.store_name}] 고객님들을 위한 특별한 제안! {request.keywords}와 함께하는 최고의 시간을 즐겨보세요."
    dummy_image_url = "https://via.placeholder.com/400x300.png?text=AI+Ad+Result"
    
    return AdResponse(
        ad_text=generated_text,
        image_url=dummy_image_url
    )

@app.get("/")
def root():
    return {"message": "AI Ad Service Backend is running!"}