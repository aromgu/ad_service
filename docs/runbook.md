# 런북 (장애 대응)

서버/인프라 담당용. 증상 → 원인 → 조치 순.
배포 절차와 runner 설정은 `docs/deployment.md`, 메트릭은 `docs/monitoring.md`.

포트 배정: **8000** api · **8501** frontend · **8001–8003** triton · **9090** prometheus · **3000** grafana

```bash
COMPOSE="docker compose -f docker/docker-compose.yml"
```

---

## 1. API 가 안 뜸 / 계속 재시작

```bash
$COMPOSE ps
$COMPOSE logs --tail=100 api
```

| 로그에 보이는 것 | 원인 | 조치 |
|---|---|---|
| `error parsing value for field ...` | `.env` 값이 스키마와 안 맞음 (예: 리스트 필드에 JSON 아닌 값) | `.env` 수정. 리스트는 콤마 문자열로 (`AD_CORS_ALLOW_ORIGINS=a,b`) |
| `ModuleNotFoundError` / `ImportError` | 의존성 누락, 이미지 오래됨 | `$COMPOSE build --no-cache api && $COMPOSE up -d api` |
| `Permission denied: '/app/var/...'` | 쓰기 경로 권한 | named volume `api-var` 사용 확인. `docker volume rm docker_api-var` 후 재기동 |
| `Address already in use` | 아래 2번 | |
| 아무 로그 없이 unhealthy | healthcheck 실패 | `$COMPOSE exec api curl -sf localhost:8000/health` 로 직접 확인 |

임시 복구: `$COMPOSE restart api`. 안 되면 `$COMPOSE up -d --force-recreate api`.

---

## 2. `port is already allocated` / `address already in use`

무엇이 잡고 있는지 확인:

```bash
docker ps --filter publish=8000 --filter publish=8501     # 컨테이너
ss -tlnp | grep -E ':8000|:8501'                          # 호스트 프로세스 (uvicorn 직접 실행 등)
```

- **떠돌이 컨테이너** (compose 밖에서 `docker run` 한 것): 팀 확인 후 `docker rm -f <name>`
- **호스트 프로세스** (`127.0.0.1:8000` 에 uvicorn 등): 그 프로세스 소유자에게 확인 후 종료
- compose 재기동 시 `--remove-orphans` 붙이기

예방: API/프론트는 항상 compose 로만. `docker run` 수동 실행 금지. 로컬 `make run` 은 컨테이너와 포트 겹침.

---

## 3. 생성이 계속 실패 (job status = failed)

```bash
curl -s localhost:8000/api/v1/jobs/<request_id> | python3 -m json.tool
$COMPOSE logs --tail=100 api | grep -E 'job .* 실패|ERROR'
```

| `error.code` | 의미 | 조치 |
|---|---|---|
| `MODEL_UNAVAILABLE` | 추론 백엔드 응답 없음 | api-gpu / triton 상태 확인. mock 모드면 코드 버그 |
| `BUDGET_EXCEEDED` | 요청 비용이 `AD_BUDGET_CAP_USD` 초과 | 캡 조정 또는 요청 축소 |
| `INTERNAL_ERROR` | 파이프라인 예외 | 로그의 스택트레이스 확인 |

메트릭으로 추세 확인: `rate(ad_jobs_total{status="failed"}[10m])` (`docs/monitoring.md`).

---

## 4. job 이 적체됨 (응답은 오는데 결과가 안 나옴)

```bash
curl -s localhost:8000/metrics | grep ad_jobs_in_progress
```

- MVP job 저장소는 **단일 프로세스 메모리**. API 컨테이너 재시작하면 진행 중 job 은 사라진다 (클라이언트는 재요청).
- `ad_jobs_in_progress` 가 계속 높으면 파이프라인이 느리거나 멈춘 것 → api 로그 확인, 필요 시 `$COMPOSE restart api`.
- 근본 대응: 워커 분리 + Redis 저장소 (`docs/api_spec.md` 섹션 5).

---

## 5. GPU OOM / GPU 안 잡힘 (api-gpu, triton)

```bash
nvidia-smi                                  # 점유 프로세스 / VRAM
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi -L
```

- **OOM**: L4 23GB 한 장 공유. 학습(`ad-service:gpu` 컨테이너)과 추론 서버를 동시에 띄우지 않는다. 큰 배치 축소.
- **`no known GPU vendor found`**: `nvidia-container-toolkit` 미설치/미설정 → `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`
- 유휴 GPU 컨테이너 정리: `$COMPOSE --profile gpu down`

---

## 6. 디스크 부족

```bash
docker system df
du -sh ~/ad_service/data /var/lib/docker 2>/dev/null
```

```bash
docker image prune -f                        # 안 쓰는 이미지
docker builder prune -f                      # 빌드 캐시
docker system prune -af --volumes            # 전체 (주의: 미사용 볼륨 삭제 — api-var 는 사용 중이면 유지)
```

생성 결과물이 쌓이는 곳: named volume `api-var` (`$COMPOSE exec api du -sh /app/var`).

---

## 7. 모니터링 스택 문제

```bash
$COMPOSE --profile monitoring ps
```

- Prometheus 타깃이 down: `http://<host>:9090/targets` 확인. api 컨테이너가 같은 compose 네트워크에 있어야 함.
- Grafana 데이터 없음: 데이터소스 URL 이 `http://prometheus:9090` 인지 확인 (`deploy/monitoring/grafana-datasource.yml`).

---

## 8. 배포가 안 나감 (Deploy 워크플로우가 큐에 멈춤)

self-hosted runner 가 죽었거나 등록이 안 된 상태. CI 는 정상인데 "Deploy" 만 queued.

```bash
# runner 상태 (등록/설정 방식에 따라)
systemctl --user status gh-runner        # user 서비스로 등록한 경우
sudo ./svc.sh status                     # 시스템 서비스로 등록한 경우 (~/actions-runner 에서)
cd ~/actions-runner && ./run.sh          # 서비스 아니고 수동 실행

# 재시작
systemctl --user restart gh-runner
```

GitHub → repo Settings → Actions → Runners 에서 `gcp-vm` 이 **Idle** 이어야 정상.
runner 가 없으면 임시로 VM 에서 직접 배포: `cd ~/ad_service && git pull && ./scripts/deploy.sh`
등록/상주 설정은 `docs/deployment.md` §1.

---

## 9. 전체 재기동 (최후의 수단)

```bash
$COMPOSE down
$COMPOSE up -d --build api
# 필요 시
$COMPOSE --profile monitoring up -d
```

Docker 데몬 자체 재시작(`sudo systemctl restart docker`)은 **공유 VM 의 모든 컨테이너를 죽인다**. 다른 팀원 작업 확인 후에만.

---

## 에스컬레이션

1. 로그 + `docker compose ps` + `nvidia-smi` 캡처
2. 팀 채널에 공유 (어느 커밋에서 터졌는지 `git -C ~/ad_service log --oneline -3`)
3. 배포가 원인이면 `docs/deployment.md` 롤백 절차
