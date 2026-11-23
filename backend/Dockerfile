# RE:SCAN 백엔드 컨테이너
#   빌드:  docker build -t rescan-api backend
#   실행:  docker run --rm -p 5001:5001 --env-file .env rescan-api
#   확인:  curl http://localhost:5001/health
#
# 이미지 안에는 비밀값(.env)을 넣지 않는다. API 키는 실행할 때 환경 변수로만 넘긴다.

FROM python:3.11-slim

# 파이썬 출력이 버퍼에 쌓이지 않고 바로 로그로 나가게, .pyc 파일은 만들지 않게
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=5001

WORKDIR /app

# 의존성 먼저 설치: 코드만 바뀌면 이 층은 캐시를 재사용해 빌드가 빨라진다
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# root가 아닌 사용자로 실행 (컨테이너가 뚫려도 권한을 줄이기 위해)
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 5001

# 컨테이너 상태 점검: /health가 응답하지 않으면 unhealthy로 표시
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"5001\")}/health', timeout=4)" || exit 1

# Render 등은 PORT를 자동으로 넣어 준다. 개발용 --reload는 쓰지 않는다
CMD ["sh", "-c", "uvicorn app:app --host ${HOST} --port ${PORT}"]
