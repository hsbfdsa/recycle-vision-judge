"""설정값을 한 곳에 모은다. 실험하거나 배포할 때 바꿀 값은 .env(환경 변수)로 덮어쓸 수 있다.

예) .env 에 CONFIRM_BELOW=0.5 를 넣으면 코드를 고치지 않고 확신도 기준을 바꿔 볼 수 있다.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# ---------- AI ----------
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "30"))      # 초. 넘으면 AI_FAILED
PREV_IMAGE_DETAIL = os.getenv("PREV_IMAGE_DETAIL", "low")  # 처음 사진은 같은 물건인지만 보면 돼서 저해상도

# ---------- 판정 ----------
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))      # 재촬영 한도
CONFIRM_BELOW = float(os.getenv("CONFIRM_BELOW", "0.6"))  # 품목 확신도가 이보다 낮으면 "○○ 맞나요?"

# ---------- 업로드·이미지 ----------
MAX_BYTES = 15 * 1024 * 1024        # 업로드 최대 15MB
MAX_SIDE = 1024                     # AI에 보내기 전 긴 변 픽셀
MIN_SIDE = 24                       # 이보다 작은 사진은 AI에 보내지 않음 (판단 불가 + 비용 낭비)
MAX_PIXELS = 50_000_000             # 이보다 픽셀이 많으면 열기 전에 거부 (픽셀 폭탄 방지)

# ---------- 서버 ----------
# 프론트 주소. 여러 개면 쉼표로: "https://a.vercel.app,http://localhost:5173"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
# 한 사용자(IP)가 1분에 보낼 수 있는 판정 요청 수. 배포 주소가 공개돼도 AI 비용이 폭주하지 않게 (0이면 끄기)
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
HOST = os.getenv("HOST", "127.0.0.1")              # 배포 서버에서는 0.0.0.0
PORT = int(os.getenv("PORT", "5001"))              # Render 등은 PORT를 자동으로 넣어 줌

# ---------- 운영 ----------
# Sentry 에러 추적 주소. 비어 있으면 끔 (로컬·테스트에서는 보내지 않음)
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
APP_ENV = os.getenv("APP_ENV", "local")            # Sentry에서 local / production 구분

# ---------- 기록 (DB) ----------
# 운영: postgresql+psycopg://사용자:비밀번호@db:5432/rescan  (deploy/docker-compose.yml)
# 비우면 backend/data/rescan.db (SQLite). 사진·IP는 어디에도 저장하지 않는다
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///" + os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rescan.db")
# 관리자 화면(/admin) 토큰. 비어 있으면 관리자 기능 전체를 끈다 (404)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
