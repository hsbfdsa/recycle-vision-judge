"""판정 기록 · 피드백 · 관리자 API 검사 (AI 호출 없음). 실행: python tests/test_store.py

DB는 기본으로 임시 SQLite 파일을 쓴다. TEST_DATABASE_URL을 주면 그 DB로 돈다
(CI에서는 PostgreSQL 컨테이너로 한 번 더 돌린다).
"""
import io, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{TMP}/test.db"
os.environ["ADMIN_TOKEN"] = "test-admin-token"

from fastapi.testclient import TestClient
from PIL import Image

import app as server
import store

server.RATE_LIMIT_PER_MIN = 0
FAKE = {"item": "P01", "confidence": 0.9, "same_item": "unknown",
        "observations": {"is_clear": "true", "label": "present", "liquid": "absent"}, "notes": "fake"}
server.observe = lambda cur, prev=None, hint=None: FAKE
server.compare_same = lambda prev, cur: "unknown"
client = TestClient(server.app)
AUTH = {"Authorization": "Bearer test-admin-token"}

# PostgreSQL로 돌 때 이전 실행의 기록이 남아 있어도 숫자가 맞게 비우고 시작
with store._engine.begin() as con:
    con.execute(store.feedback.delete())
    con.execute(store.judgments.delete())


def jpg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="JPEG")
    return ("p.jpg", buf.getvalue(), "image/jpeg")


def judge_once(**data):
    return client.post("/judge", files={"image": jpg()}, data={"attempt": "1", **data})


results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("O " if cond else "X ") + name + (f"  ({detail})" if detail and not cond else ""))


# ---------- 판정 기록 ----------
r1 = judge_once()
jid = r1.json().get("judgment_id")
check("판정 응답에 judgment_id가 있음 (32자리)", r1.status_code == 200 and jid and len(jid) == 32, r1.text[:200])

with store._engine.connect() as con:
    row = con.execute(store.judgments.select().where(store.judgments.c.id == jid)).mappings().first()
check("DB에 품목 · 결과 · AI가 본 값이 저장됨",
      row and row["item"] == "P01" and row["status"] == r1.json()["judgement"]["status"]
      and row["seen"].get("label") == "present", dict(row) if row else None)
check("사진은 저장하지 않음 (테이블에 이미지 열이 없음)",
      not any("image" in c.name or "photo" in c.name for c in store.judgments.columns))

obs = r1.json()["observation"]
import json as _json
r2 = client.post("/judge", data={"attempt": "1", "observation": _json.dumps(obs), "answers": '{"checkbox": "true"}'})
with store._engine.connect() as con:
    row2 = con.execute(store.judgments.select().where(store.judgments.c.id == r2.json().get("judgment_id"))).mappings().first()
check("질문 답변 재판정은 reused=True, 답한 값도 기록", row2 and row2["reused"] is True and row2["answers"].get("checkbox") == "true",
      dict(row2) if row2 else r2.text[:200])

# ---------- 피드백 ----------
ok = client.post("/feedback", json={"judgment_id": jid, "correct": True})
check("맞았어요 → 200", ok.status_code == 200 and ok.json() == {"ok": True}, ok.text)
again = client.post("/feedback", json={"judgment_id": jid, "correct": False, "reason": "state", "comment": "라벨 없는데 있다고 함"})
with store._engine.connect() as con:
    fb = con.execute(store.feedback.select().where(store.feedback.c.judgment_id == jid)).mappings().all()
check("다시 누르면 마지막 값으로 바뀜 (한 판정에 피드백 1개)",
      again.status_code == 200 and len(fb) == 1 and fb[0]["correct"] is False and fb[0]["reason"] == "state", fb)

nf = client.post("/feedback", json={"judgment_id": "0" * 32, "correct": True})
check("없는 판정 → 404 NOT_FOUND", nf.status_code == 404 and nf.json()["error"]["code"] == "NOT_FOUND", nf.text)
bad = client.post("/feedback", json={"judgment_id": "../etc", "correct": True})
check("ID 형식이 아님 → 400", bad.status_code == 400, bad.text)
bad2 = client.post("/feedback", json={"judgment_id": jid, "correct": True, "comment": "x" * 301})
check("의견 300자 초과 → 400", bad2.status_code == 400, bad2.text)
bad3 = client.post("/feedback", json={"judgment_id": jid, "correct": True, "reason": "hack"})
check("정해진 이유가 아님 → 400", bad3.status_code == 400, bad3.text)

# ---------- 관리자 ----------
check("토큰 없이 요약 → 401", client.get("/admin/api/summary").status_code == 401)
check("틀린 토큰 → 401", client.get("/admin/api/summary", headers={"Authorization": "Bearer nope"}).status_code == 401)
page = client.get("/admin")
check("관리자 화면 HTML (캐시 안 함)", page.status_code == 200 and "text/html" in page.headers["content-type"]
      and page.headers.get("cache-control") == "no-store")

s = client.get("/admin/api/summary", headers=AUTH)
body = s.json()
check("요약: 판정 2건, 피드백 1건(틀림 1)", s.status_code == 200 and body["judgments"] == 2
      and body["feedback"] == {"total": 1, "correct": 0, "wrong": 1, "accuracy": 0.0}, body)
check("요약: 응답 시간은 AI를 부른 판정만 계산", body.get("latency_ms", {}).get("n") == 1, body.get("latency_ms"))
check("요약: 품목별 오답 수", body["by_item"] and body["by_item"][0] == {"item": "P01", "n": 2, "wrong": 1}, body["by_item"])

w = client.get("/admin/api/judgments?only=wrong", headers=AUTH).json()["items"]
check("틀렸어요 목록: 1건, 의견 포함", len(w) == 1 and w[0]["id"] == jid and w[0]["comment"] == "라벨 없는데 있다고 함", w)
a = client.get("/admin/api/judgments?limit=1", headers=AUTH).json()["items"]
check("전체 목록 limit 동작 (최신순)", len(a) == 1, a)

# 평가 세트 후보 목록 (tests/export_feedback.py)가 관리자 API 응답을 그대로 읽는지
sys.path.insert(0, HERE)
import export_feedback
md = export_feedback.build_report(w, today="2026-11-24")
check("틀렸어요 → 평가 후보 목록 (품목 · 이유 · AI가 본 값 · 의견)",
      "| P01 | 상태 | 1 |" in md and "label=present" in md and "라벨 없는데 있다고 함" in md, md)

# 토큰이 없으면 관리자 기능 전체가 없는 것처럼 (404)
server.ADMIN_TOKEN = ""
check("ADMIN_TOKEN 없음 → /admin 404", client.get("/admin").status_code == 404)
check("ADMIN_TOKEN 없음 → 관리자 API 404", client.get("/admin/api/summary", headers=AUTH).status_code == 404)
server.ADMIN_TOKEN = "test-admin-token"

# ---------- DB가 죽어도 판정은 계속 ----------
saved = store._engine
store._engine = None
r3 = judge_once()
check("DB 꺼짐 → 판정은 200, judgment_id만 없음", r3.status_code == 200 and "judgment_id" not in r3.json(), r3.text[:200])
off = client.post("/feedback", json={"judgment_id": jid, "correct": True})
check("DB 꺼짐 → 피드백은 503 STORE_OFF", off.status_code == 503 and off.json()["error"]["code"] == "STORE_OFF", off.text)
store._engine = saved

from sqlalchemy import create_engine
broken = create_engine("sqlite:////nonexistent-dir/x/y.db")
store._engine = broken
r4 = judge_once()
check("DB 쓰기 실패 → 판정은 200, judgment_id 없음", r4.status_code == 200 and "judgment_id" not in r4.json(), r4.text[:200])
store._engine = saved

print(f"\n{sum(results)}/{len(results)} 통과  (DB: {store._engine.dialect.name})")
sys.exit(0 if all(results) else 1)
