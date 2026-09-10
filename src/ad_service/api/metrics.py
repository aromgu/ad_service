"""커스텀 Prometheus 메트릭.

HTTP 레벨 메트릭(요청 수/지연/진행중)은 prometheus-fastapi-instrumentator 가
`/metrics` 에 자동으로 붙인다. 여기서는 생성 job 관련 지표만 정의한다.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

JOBS_TOTAL = Counter(
    "ad_jobs_total",
    "완료된 생성 job 수 (상태별)",
    labelnames=("status",),  # done | failed
)

JOBS_IN_PROGRESS = Gauge(
    "ad_jobs_in_progress",
    "현재 처리 중인 생성 job 수",
)

JOB_DURATION = Histogram(
    "ad_job_duration_seconds",
    "생성 job 접수부터 완료까지 걸린 시간",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
