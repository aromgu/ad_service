# 모니터링 / 관측성

## 한눈에

| | |
|---|---|
| 메트릭 | `GET /metrics` (Prometheus 포맷). API 앱에 내장 |
| 로그 | stdout. `AD_LOG_JSON=true` 면 한 줄 JSON. 요청마다 `request_id` |
| 헬스 | `GET /health` |
| 대시보드 | `--profile monitoring` → Prometheus :9090, Grafana :3000 |

```bash
docker compose -f docker/docker-compose.yml --profile monitoring up -d
# Prometheus  http://<host>:9090
# Grafana     http://<host>:3000  (익명 열람 on, admin/admin)
```

Grafana 는 Prometheus 데이터소스가 자동 연결된다. 대시보드는 직접 만들거나
[FastAPI dashboard #16110](https://grafana.com/grafana/dashboards/16110) import.

---

## 메트릭

### HTTP (prometheus-fastapi-instrumentator 자동)

| 메트릭 | 용도 |
|---|---|
| `http_requests_total{handler,method,status}` | 요청량, 에러율 |
| `http_request_duration_seconds{handler,method}` | 지연 분포 (히스토그램) |
| `http_requests_in_progress` | 동시 처리 중 요청 수 |

`/health`, `/metrics` 는 집계에서 제외된다.

### 생성 job (커스텀 — `src/ad_service/api/metrics.py`)

| 메트릭 | 타입 | 용도 |
|---|---|---|
| `ad_jobs_total{status}` | counter | 완료 job 수. `status` = `done` / `failed` |
| `ad_jobs_in_progress` | gauge | 지금 생성 중인 job 수 |
| `ad_job_duration_seconds` | histogram | job 처리 시간 (버킷 0.5s ~ 300s) |

---

## 유용한 쿼리 (PromQL)

```promql
# 요청 에러율 (5xx 비율)
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# p95 응답시간 (엔드포인트별)
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))

# job 실패율
rate(ad_jobs_total{status="failed"}[10m]) / rate(ad_jobs_total[10m])

# job p90 처리시간
histogram_quantile(0.90, sum(rate(ad_job_duration_seconds_bucket[10m])) by (le))

# 쌓이는 job (처리가 안 따라감)
ad_jobs_in_progress
```

---

## 걸어둘 만한 알림 (임계값은 트래픽 보고 조정)

| 알림 | 조건 (예시) |
|---|---|
| API down | `up{job="ad-service-api"} == 0` for 1m |
| 에러율 급증 | 5xx 비율 > 5% for 5m |
| 응답 지연 | p95 > 2s for 10m |
| job 실패 급증 | 실패율 > 20% for 10m |
| job 적체 | `ad_jobs_in_progress > 20` for 5m |
| 디스크 | VM 디스크 사용률 > 85% (GCP Monitoring) |

Prometheus 자체 알림 규칙은 `deploy/monitoring/` 에 `alerts.yml` 추가 후
`prometheus.yml` 의 `rule_files` 에 등록. (지금은 미설정)

---

## 로그

```bash
docker compose -f docker/docker-compose.yml logs -f api
```

- 형식(dev): `시각 | LEVEL | request_id | 메시지`
- 운영: `AD_LOG_JSON=true` → 한 줄 JSON, 수집기(Loki/CloudWatch 등)로 보내기 쉬움
- 응답 헤더 `X-Request-ID` 로 클라이언트 ↔ 로그 상관관계 추적
- job 완료/실패는 `job <id> done (2.3s)` 형태로 남는다

중앙 수집(Loki 등)은 TODO. 현재는 `docker compose logs` + `journalctl`.

---

## TODO

- [ ] Grafana 대시보드 JSON 을 `deploy/monitoring/` 에 커밋 (프로비저닝)
- [ ] Prometheus alert rules + Alertmanager → Slack
- [ ] 로그 중앙 수집
- [ ] GPU 메트릭 (`nvidia-dcgm-exporter`) — api-gpu / triton 띄울 때
- [ ] job 저장소가 Redis 로 가면 Redis exporter
