# ===== 프론트엔드 (Streamlit) 이미지 =====
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 먼저 (레이어 캐시).
COPY frontend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 소스.
COPY frontend/ ./

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
