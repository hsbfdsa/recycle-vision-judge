"""판정 기록과 사용자 피드백 저장 (SQLAlchemy Core)

- 운영: PostgreSQL (DATABASE_URL=postgresql+psycopg://...)
- 로컬·테스트: SQLite 파일 (DATABASE_URL을 안 주면 backend/data/rescan.db)

저장하는 것: 품목, 판정 결과, AI가 본 값, 확신도, 응답 시간, 사용자의 '맞았어요/틀렸어요'
저장하지 않는 것: 사진, IP, 기기 정보 (사진은 메모리에서만 처리하고 버린다)

DB가 죽어도 판정은 계속돼야 한다. 그래서 저장 실패는 로그와 Sentry에만 남기고
판정 응답은 judgment_id 없이 그대로 돌려준다. (피드백만 잠시 못 받음)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String,
                        Table, case, create_engine, func, select)
from sqlalchemy.engine import Engine

log = logging.getLogger("uvicorn.error")

metadata = MetaData()

judgments = Table(
    "judgments", metadata,
    Column("id", String(32), primary_key=True),                 # uuid4 hex. 순번을 쓰지 않아 남의 기록을 추측할 수 없게
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("item", String(8), nullable=False, index=True),      # 품목ID (P01 등)
    Column("status", String(24), nullable=False),               # pass / need_action / question / retake ...
    Column("attempt", Integer, nullable=False),
    Column("confidence", Float),
    Column("reused", Boolean, nullable=False, default=False),   # 질문 답변으로 직전 관찰을 다시 쓴 판정 (AI 호출 없음)
    Column("seen", JSON),                                       # AI가 본 값 {"label": "present", ...}
    Column("answers", JSON),                                    # 사용자가 답한 질문·체크박스
    Column("notes", String(300)),                               # AI 메모 (평가 세트 후보를 고를 때 참고)
    Column("ms", Integer),                                      # 서버 처리 시간
    Column("model", String(40)),
)

feedback = Table(
    "feedback", metadata,
    Column("judgment_id", String(32), ForeignKey("judgments.id", ondelete="CASCADE"), primary_key=True),
    Column("correct", Boolean, nullable=False),
    Column("reason", String(20)),                               # item / state / place / other
    Column("comment", String(300)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_engine: Optional[Engine] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(ts: Optional[datetime]) -> Optional[datetime]:
    """SQLite는 시간대 없이 돌려준다. 저장은 항상 UTC로 하므로 UTC로 붙여 읽는다."""
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def init(url: str) -> bool:
    """DB 연결과 테이블 생성. 실패하면 기록 없이 서비스한다 (판정은 막지 않음)."""
    global _engine
    try:
        if url.startswith("sqlite:///"):
            import os
            path = url[len("sqlite:///"):]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        engine = create_engine(url, pool_pre_ping=True, future=True)
        metadata.create_all(engine)
        _engine = engine
        log.info("store: connected (%s)", engine.dialect.name)
        return True
    except Exception:
        log.exception("store: DB 연결 실패. 판정 기록 없이 계속합니다")
        _engine = None
        return False


def enabled() -> bool:
    return _engine is not None


def save_judgment(*, item: str, status: str, attempt: int, confidence: Optional[float], reused: bool,
                  seen: dict, answers: dict, notes: str, ms: int, model: str) -> Optional[str]:
    """판정 한 건 저장. 성공하면 id, 실패하면 None (판정 응답은 그대로 나감)."""
    if _engine is None:
        return None
    jid = uuid.uuid4().hex
    try:
        with _engine.begin() as con:
            con.execute(judgments.insert().values(
                id=jid, created_at=_now(), item=item, status=status, attempt=attempt, confidence=confidence,
                reused=reused, seen=seen or {}, answers=answers or {}, notes=(notes or "")[:300], ms=ms,
                model=model[:40]))
        return jid
    except Exception:
        log.exception("store: 판정 저장 실패")
        return None


def save_feedback(judgment_id: str, correct: bool, reason: Optional[str], comment: Optional[str]) -> bool:
    """피드백 저장. 같은 판정에 다시 누르면 마지막 값으로 바꾼다. 판정이 없으면 False."""
    if _engine is None:
        raise RuntimeError("store disabled")
    with _engine.begin() as con:
        if con.execute(select(judgments.c.id).where(judgments.c.id == judgment_id)).first() is None:
            return False
        row = dict(correct=correct, reason=reason, comment=(comment or "").strip()[:300] or None, created_at=_now())
        updated = con.execute(feedback.update().where(feedback.c.judgment_id == judgment_id).values(**row))
        if updated.rowcount == 0:
            con.execute(feedback.insert().values(judgment_id=judgment_id, **row))
    return True


# ---------- 관리자 화면용 조회 ----------

def summary(days: int = 7) -> dict[str, Any]:
    """최근 N일 요약: 판정 수, 결과별 수, 피드백 정답률, 응답 시간, 품목별 오답."""
    since = _now() - timedelta(days=days)
    j, f = judgments, feedback
    with _engine.connect() as con:
        total = con.execute(select(func.count()).select_from(j).where(j.c.created_at >= since)).scalar_one()
        by_status = dict(con.execute(
            select(j.c.status, func.count()).where(j.c.created_at >= since).group_by(j.c.status)).all())
        fb = con.execute(
            select(func.count(), func.sum(case((f.c.correct.is_(True), 1), else_=0)))
            .select_from(f.join(j, f.c.judgment_id == j.c.id)).where(j.c.created_at >= since)).one()
        ms = [r[0] for r in con.execute(
            select(j.c.ms).where(j.c.created_at >= since, j.c.reused.is_(False), j.c.ms.is_not(None))).all()]
        by_item = con.execute(
            select(j.c.item, func.count().label("n"),
                   func.sum(case((f.c.correct.is_(False), 1), else_=0)).label("wrong"))
            .select_from(j.outerjoin(f, f.c.judgment_id == j.c.id))
            .where(j.c.created_at >= since).group_by(j.c.item).order_by(func.count().desc()).limit(15)).all()
        daily_rows = con.execute(select(j.c.created_at).where(j.c.created_at >= since)).all()

    daily: dict[str, int] = {}
    for (ts,) in daily_rows:                    # 날짜 함수는 DB마다 달라서 파이썬에서 센다 (최근 N일이라 양이 적음)
        key = _utc(ts).astimezone(timezone(timedelta(hours=9))).strftime("%m-%d")   # 한국 시간 기준
        daily[key] = daily.get(key, 0) + 1

    fb_total, fb_correct = fb[0] or 0, int(fb[1] or 0)
    ms.sort()
    return {
        "days": days,
        "judgments": total,
        "by_status": by_status,
        "feedback": {"total": fb_total, "correct": fb_correct, "wrong": fb_total - fb_correct,
                     "accuracy": round(fb_correct / fb_total, 3) if fb_total else None},
        "latency_ms": {"avg": round(sum(ms) / len(ms)) if ms else None,
                       "p95": ms[min(len(ms) - 1, int(len(ms) * 0.95))] if ms else None,
                       "n": len(ms)},
        "by_item": [{"item": r.item, "n": r.n, "wrong": int(r.wrong or 0)} for r in by_item],
        "daily": dict(sorted(daily.items())),
    }


def recent(limit: int = 50, only: Optional[str] = None) -> list[dict[str, Any]]:
    """최근 판정 목록. only='wrong'이면 '틀렸어요'만, 'feedback'이면 피드백 있는 것만."""
    j, f = judgments, feedback
    q = (select(j, f.c.correct, f.c.reason, f.c.comment)
         .select_from(j.outerjoin(f, f.c.judgment_id == j.c.id))
         .order_by(j.c.created_at.desc()).limit(max(1, min(limit, 500))))
    if only == "wrong":
        q = q.where(f.c.correct.is_(False))
    elif only == "feedback":
        q = q.where(f.c.correct.is_not(None))
    with _engine.connect() as con:
        rows = con.execute(q).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["created_at"] = _utc(d["created_at"]).isoformat() if d["created_at"] else None
        out.append(d)
    return out
