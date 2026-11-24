"""RE:SCAN MCP 서버 — 분리배출 판정과 배출 기준 조회를 AI 에이전트의 도구로 연다.

도구
  search_items       품목 이름·별칭으로 검색 (규칙표만 읽음, AI·네트워크 없음)
  get_disposal_rule  품목ID로 배출 기준 조회 (규칙표만 읽음)
  judge_photo        사진 파일을 운영 중인 RE:SCAN API에 보내 판정 (AI 호출, 요청 제한 적용)

설계 원칙은 서비스와 같다. 배출 기준은 rules.json만 말하고, 에이전트(LLM)는 그 결과를 전달만 한다.
API 키는 이 서버에 두지 않는다. 판정은 배포된 API가 하고, 여기서는 사진을 전달만 한다.

실행:  python mcp_server/server.py          (stdio, Claude Desktop 등에서 실행)
설정:  RESCAN_API_URL  판정 API 주소 (기본값: 운영 서버)
"""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError   # 에이전트에게 그대로 보여 줄 오류

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "backend" / "rules.json"
API_URL = os.getenv("RESCAN_API_URL", "https://13-55-66-67.sslip.io").rstrip("/")
MAX_BYTES = 15 * 1024 * 1024                 # 서버와 같은 제한. 보내기 전에 미리 거른다
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
TIMEOUT = 60

with RULES_PATH.open(encoding="utf-8") as f:
    _RULESET = json.load(f)
ITEMS: dict[str, dict] = _RULESET["items"]
PLACES: dict[str, dict] = _RULESET["places"]

server = MCPServer(
    "rescan",
    instructions=(
        "분리배출 방법을 안내하는 도구입니다. 배출 기준은 도구 결과(공공기관 기준을 옮긴 규칙표)만 "
        "근거로 답하고, 결과에 없는 기준을 추측해 덧붙이지 마세요. judge_photo가 질문이나 재촬영을 "
        "돌려주면 사용자에게 그대로 묻고, 답은 answers로 다시 보내세요."
    ),
)


def _places(keys: list[str]) -> list[dict]:
    return [{"title": PLACES[k]["title"], "where": PLACES[k]["where"]} for k in keys if k in PLACES]


@server.tool()
def search_items(query: str, limit: int = 8) -> list[dict]:
    """품목 이름이나 흔히 부르는 말(예: '생수병', '택배 상자')로 지원 품목을 찾는다. 결과의 id를 get_disposal_rule에 쓴다."""
    q = query.strip().lower()
    if not q:
        raise ToolError("검색어가 비어 있어요. 물건 이름을 넣어 주세요.")
    hits = []
    for item_id, rule in ITEMS.items():
        words = [rule["name"], *rule.get("keywords", [])]
        if any(q in w.lower() or w.lower() in q for w in words):
            exact = any(q == w.lower() for w in words)
            hits.append((0 if exact else 1, item_id, rule))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [{"id": i, "name": r["name"], "type": "상태 판정형" if r["type"] == "state" else "정보 안내형"}
            for _, i, r in hits[:max(1, min(limit, 20))]]


@server.tool()
def get_disposal_rule(item_id: str) -> dict:
    """품목ID(예: P01, I05)의 배출 기준: 버리는 곳, 순서, 꼭 지킬 조건, 권고, 주의, 출처."""
    rule = ITEMS.get(item_id.strip().upper())
    if rule is None:
        raise ToolError(f"'{item_id}' 품목이 없어요. search_items로 품목ID를 먼저 찾아 주세요.")
    conditions = rule.get("conditions", [])
    return {
        "id": item_id.strip().upper(),
        "name": rule["name"],
        "disposal": rule.get("disposal"),
        "how": rule.get("how", []),
        "places": _places(rule.get("places", [])),
        "required": [c["action"] for c in conditions if c.get("kind") == "required" and c.get("action")],
        "tips": [c["action"] for c in conditions if c.get("kind") == "tip" and c.get("action")],
        "warnings": rule.get("warnings", []),
        "source": rule.get("source"),
    }


def _multipart(fields: dict[str, str], file_field: str, path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                 f'filename="{path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _post_judge(path: Path, answers: dict[str, str]) -> dict:
    body, ctype = _multipart({"attempt": "1", "answers": json.dumps(answers, ensure_ascii=False)}, "image", path)
    req = urllib.request.Request(f"{API_URL}/judge", data=body, method="POST",
                                 headers={"Content-Type": ctype, "User-Agent": "rescan-mcp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", {})
        except (ValueError, AttributeError):
            err = {}
        raise ToolError(err.get("message") or f"판정 서버 오류 (HTTP {e.code})")
    except (urllib.error.URLError, TimeoutError):
        raise ToolError("판정 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.")


@server.tool()
def judge_photo(image_path: str, answers: dict[str, str] | None = None) -> dict:
    """사진 파일 경로를 받아 지금 버려도 되는지, 버리기 전에 할 일이 있는지 판정한다.
    status가 question이면 questions의 key와 고른 value를 answers에 담아 같은 사진으로 다시 부른다."""
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise ToolError(f"사진 파일을 찾을 수 없어요: {image_path}")
    if path.suffix.lower() not in IMAGE_TYPES:
        raise ToolError("JPG, PNG, HEIC, WEBP 사진만 판정할 수 있어요.")
    if path.stat().st_size > MAX_BYTES:
        raise ToolError("사진이 15MB를 넘어요. 크기를 줄여서 다시 보내 주세요.")

    data = _post_judge(path, answers or {})
    j = data.get("judgement", {})
    obs = data.get("observation", {})
    return {
        "status": j.get("status"),
        "message": j.get("message"),
        "item": j.get("item"),
        "name": j.get("name"),
        "disposal": j.get("disposal"),
        "checklist": [c.get("text") for c in j.get("checklist", [])],
        "questions": [{"key": q.get("key"), "text": q.get("text"),
                       "options": [o.get("value") for o in q.get("options", [])][:10]}
                      for q in j.get("questions", [])],
        "places": j.get("places", []),
        "tips": j.get("tips", []),
        "warnings": j.get("warnings", []),
        "seen": obs.get("observations", {}),       # 판정 근거: AI가 사진에서 본 것
        "source": j.get("source"),
    }


if __name__ == "__main__":
    server.run()
