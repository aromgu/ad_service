# ===== CPU / API 이미지 =====
# 멀티모달 추론 없이 API 서버만 띄우거나, 외부 추론 엔드포인트를 호출하는 경우 사용.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ----- deps 레이어 (캐시 최적화) -----
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ----- 소스 -----
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
RUN pip install -e .

EXPOSE 8000

# 생성 결과/업로드가 쌓이는 위치. compose 에서 named volume 으로 마운트한다.
# 빈 named volume 은 이 디렉터리의 소유권(appuser)을 물려받으므로 쓰기가 된다.
RUN mkdir -p /app/var/outputs /app/var/uploads

# 비루트 유저
RUN useradd -m appuser && chown -R appuser:appuser ${APP_HOME}
USER appuser

HEALTHCHECK --interval=10s --timeout=3s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "ad_service.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
