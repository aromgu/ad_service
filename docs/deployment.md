# 배포 / 운영

## 구성

```
GitHub (main push)
  └─ CI 통과 → Deploy 워크플로우
        └─ GCP VM 의 self-hosted runner 가 받아서 실행
              └─ scripts/deploy.sh
                    docker compose up -d --build api → /health 확인 → 이미지 정리
```

**왜 self-hosted runner?**
GitHub-hosted runner 에서 VM 으로 SSH 하려면 VM 22 포트를 외부에 열어야 한다.
runner 를 VM 안에 두면 GitHub 로 **아웃바운드**만 하므로 방화벽 변경이 필요 없다.

- VM 외부 IP: `34.133.130.208` (SSH 인바운드는 열지 않는다)
- 배포 경로: `/home/argu/ad_service`
- 실행 유저: `argu` (docker 그룹 소속, sudo 불필요)

---

## 1. self-hosted runner 최초 설정 (1회)

GitHub → repo → Settings → Actions → Runners → "New self-hosted runner" (Linux x64)
에서 나오는 토큰으로 아래 실행. (또는 `gh api -X POST repos/aromgu/ad_service/actions/runners/registration-token --jq .token`)

```bash
cd ~
mkdir actions-runner && cd actions-runner
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
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

### 서비스로 등록 (재부팅에도 살아있게)

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

### 자동
`main` 에 머지 → CI 통과 → 약 1~2분 뒤 자동 배포. Actions 탭에서 "Deploy" 진행 확인.

### 수동 재배포
- GitHub Actions → Deploy → "Run workflow"
- 또는 VM 에서 직접:
  ```bash
  cd ~/ad_service && git pull && ./scripts/deploy.sh
  ```

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
docker compose -f docker/docker-compose.yml ps
docker stats --no-stream
```

- API 문서: `http://34.133.130.208:8000/docs` (GCP 방화벽에서 8000 허용 시)
- 생성 결과물: named volume `api-var` (`docker compose exec api ls /app/var/outputs`)

---

## 5. 다음 (TODO)

- [ ] `/metrics` 엔드포인트 + Prometheus (prometheus-fastapi-instrumentator)
- [ ] 로그 중앙 수집 (현재는 `docker compose logs`)
- [ ] GCP 알림: VM CPU/메모리/디스크
- [ ] job 저장소 Redis 전환 (API 인스턴스 2개 이상일 때)
- [ ] 배포 알림 (Slack)
