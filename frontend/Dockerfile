FROM python:3.9-slim

WORKDIR /app

# 필수 시스템 패키지 업데이트 및 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 패키지 설치 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 현재 폴더의 모든 소스코드를 컨테이너 내부로 복사
COPY . .

# Streamlit 기본 포트 개방
EXPOSE 8501

# 컨테이너 실행 시 Streamlit 앱 구동 명령어
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]