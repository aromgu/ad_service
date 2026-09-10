# 배포 / 운영

## 현재: 수동 배포 (개발 단계)

자동 배포(CD)는 **비활성화**돼 있다 (`Deploy` 워크플로우 `disabled_manually`).
앱이 아직 mock 이고 데모 환경이 없어서, 실행 상태를 보고 싶을 때만 VM 에서 직접 배포한다.

```bash
cd ~/ad_service
git pull
./scripts/deploy.sh                 # 또는 DEPLOY_SERVICES="api frontend" ./scripts/deploy.sh
```

- 배포 경로: `/home/argu/ad_service`
- 실행 유저: `argu` (docker 그룹, sudo 불필요)
- `deploy.sh`: `compose up -d --build` → `/health` 확인 → 미사용 이미지 정리

**자동 배포로 전환하는 시점**: 실제 모델 연결됨 + 스테이징/데모 환경이 생겨서
배포가 잦아질 때. 그때 아래 §1 로 runner 를 등록하고 `gh workflow enable deploy.yml`.

---

## 1. (나중에) self-hosted runner 로 자동 배포

```
main push → CI 통과 → Deploy 워크플로우 → VM 안 runner → scripts/deploy.sh
```

GitHub-hosted runner 에서 VM 으로 SSH 하려면 VM 22 포트를 외부에 열어야 한다.
runner 를 VM 안에 두면 GitHub 로 **아웃바운드**만 하므로 방화벽 변경이 필요 없다.

> ⚠️ 레포가 public 이면 self-hosted runner 는 위험하다 (fork PR 로 VM 에서 코드 실행).
> 현재 레포는 **private** 이라 안전. public 으로 돌린다면 runner 를 쓰지 말거나
> `deploy.yml` 에 `pull_request` 트리거를 절대 넣지 않는다.

### 1-1. runner 등록

GitHub → repo → Settings → Actions → Runners → "New self-hosted runner" (Linux x64)
에서 나오는 토큰으로 아래 실행. (또는 `gh api -X POST repos/aromgu/ad_service/actions/runners/registration-token --jq .token`)

```bash
cd ~
mkdir actions-runner && cd actions-runner
V=2.337.0   # https://github.com/actions/runner/releases 최신
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v${V}/actions-runner-linux-x64-${V}.tar.gz
tar xzf runner.tar.gz

./config.sh \
  --url https://github.com/aromgu/ad_service \
  --token <REGISTRATION_TOKEN> \
  --name gcp-vm \
  --labels gcp-vm \
  --work _work \
  --unattended
```

`deploy.yml` 이 `runs-on: [self-hosted, gcp-vm]` 이므로 라벨 `gcp-vm` 필수.
등록 후 `gh workflow enable deploy.yml` 로 Deploy 워크플로우를 켠다.

### 1-2. 서비스로 등록 (재부팅에도 살아있게)

`svc.sh` 는 sudo 가 필요하다. sudo 가 있으면:

```bash
sudo ./svc.sh install argu
sudo ./svc.sh start
sudo ./svc.sh status
```

sudo 가 없으면 systemd --user + linger:

```bash
sudo loginctl enable-linger argu        # 관리자에게 요청
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/gh-runner.service <<'EOF'
[Unit]
Description=GitHub Actions runner
After=network-online.target docker.service

[Service]
WorkingDirectory=%h/actions-runner
ExecStart=%h/actions-runner/run.sh
Restart=always

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now gh-runner
```

확인: repo Settings → Actions → Runners 에 `gcp-vm` 이 **Idle** 로 보이면 완료.

---

## 2. 배포

### 수동 (현재)
```bash
cd ~/ad_service && git pull && ./scripts/deploy.sh
```

### 자동 (runner 등록 + `gh workflow enable deploy.yml` 후)
`main` 머지 → CI 통과 → 1~2분 뒤 자동 배포. Actions 탭 "Deploy" 확인.
수동 재실행은 Actions → Deploy → "Run workflow".

### 롤백
```bash
cd ~/ad_service
git log --oneline -5                 # 되돌릴 커밋 확인
git checkout <good_commit>
DEPLOY_SERVICES="api" ./scripts/deploy.sh
# 복구되면 revert PR 를 올려 main 을 정리한다
```

---

## 3. 런북 (장애 대응)

→ **[docs/runbook.md](runbook.md)** 참고.

API 안뜸 / 포트 충돌 / job 실패·적체 / GPU OOM / 디스크 / 모니터링 / 전체 재기동,
그리고 배포가 원인일 때의 롤백(아래 §2).

---

## 4. 상태 확인

```bash
curl -s localhost:8000/health
curl -s localhost:8000/metrics | head
docker compose -f docker/docker-compose.yml ps
docker stats --no-stream
```

- API 문서: `http://34.133.130.208:8000/docs` (GCP 방화벽에서 8000 허용 시)
- 생성 결과물: named volume `api-var` (`docker compose exec api ls /app/var/outputs`)
- 메트릭·로그·알림: [monitoring.md](monitoring.md)

---

## 5. 다음 (TODO)

- [ ] self-hosted runner 등록 → 자동 배포 (개발 단계 지나면)
- [ ] 로그 중앙 수집 (현재는 `docker compose logs`)
- [ ] GCP 알림: VM CPU/메모리/디스크
- [ ] job 저장소 Redis 전환 (API 인스턴스 2개 이상일 때)
- [ ] 배포 알림 (Slack)
