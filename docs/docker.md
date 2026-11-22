# Docker로 백엔드 실행하기

백엔드를 컨테이너 하나로 묶어 어느 Linux 서버에서든 같은 방식으로 실행할 수 있게 했습니다.

## 왜 바꿨나

- Render의 Python 런타임에 맞춰 배포하다 보니 로컬과 서버의 파이썬 버전·패키지가 어긋날 수 있었습니다.
- 서버를 옮길 때마다 설치 과정을 다시 해야 했습니다.
- 이미지 하나로 묶으면 로컬, CI, 배포 서버가 같은 환경에서 돌아갑니다.

## 로컬에서 실행

```bash
# 1. 이미지 빌드 (저장소 루트에서)
docker build -t rescan-api backend

# 2. 실행 — API 키는 이미지에 넣지 않고 실행할 때 넘긴다
docker run --rm -p 5001:5001 --env-file backend/.env rescan-api

# 3. 확인
curl http://localhost:5001/health        # {"ok":true}
open http://localhost:5001/docs          # API 문서
```

`backend/.env` 예시 (저장소에 올리지 않는다):

```
OPENAI_API_KEY=sk-...
ALLOWED_ORIGINS=http://localhost:5173
RATE_LIMIT_PER_MIN=20
```

## Linux 서버(VM)에 배포

```bash
# 서버에서
sudo apt-get update && sudo apt-get install -y docker.io git
git clone https://github.com/<계정>/recycle-vision-judge.git
cd recycle-vision-judge
docker build -t rescan-api backend

# .env는 서버에서 직접 만든다 (scp나 에디터로)
docker run -d --name rescan-api --restart unless-stopped \
  -p 80:5001 --env-file backend/.env rescan-api

docker ps                    # STATUS에 (healthy)가 보이면 정상
docker logs -f rescan-api    # 요청 로그 확인
```

업데이트:

```bash
git pull && docker build -t rescan-api backend
docker rm -f rescan-api && docker run -d --name rescan-api --restart unless-stopped \
  -p 80:5001 --env-file backend/.env rescan-api
```

## 이미지 설계

| 결정 | 이유 |
|---|---|
| `python:3.11-slim` | CI와 같은 파이썬 버전, 작은 이미지 |
| requirements를 먼저 복사해 설치 | 코드만 바뀌면 의존성 층을 캐시에서 재사용해 빌드가 빨라짐 |
| `.dockerignore`로 `.env` 제외 | 비밀값이 이미지에 들어가지 않게 |
| root가 아닌 `app` 사용자로 실행 | 컨테이너가 뚫려도 권한을 줄이기 위해 |
| `HEALTHCHECK`로 `/health` 확인 | 서버가 멈추면 `unhealthy`로 표시, 재시작 정책과 함께 사용 |
| `--reload` 제외 | 개발용 옵션이라 운영에서는 불필요한 파일 감시를 하지 않게 |

## CI

GitHub Actions의 `docker` 작업이 푸시마다 이미지를 빌드하고 컨테이너를 띄워 `/health`, `/items` 응답과 non-root 실행을 확인합니다. AI는 호출하지 않으므로 API 키가 필요 없습니다.
