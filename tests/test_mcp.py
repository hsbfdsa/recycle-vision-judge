"""MCP 서버(mcp_server/server.py) 검사. AI·네트워크 없이 실행: python tests/test_mcp.py
judge_photo는 실제 백엔드 앱(app.py)에 요청이 가도록 연결하고, AI 관찰만 가짜로 바꾼다."""
import asyncio, io, json, os, sys, tempfile, urllib.error
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, os.path.join(HERE, "..", "mcp_server"))

from fastapi.testclient import TestClient
from mcp.client.client import Client
from PIL import Image

import app as backend
import server as mcp_server

backend.RATE_LIMIT_PER_MIN = 0
backend.observe = lambda cur, prev=None, hint=None: {
    "item": "P01", "confidence": 0.95, "same_item": "unknown",
    "observations": {"is_clear": "true", "label": "present", "liquid": "absent"}, "notes": "fake"}
api = TestClient(backend.app)
sent = {}


class FakeResponse:
    def __init__(self, body): self.body = body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(req, timeout=None):
    """MCP 서버가 만든 multipart 요청을 그대로 백엔드 앱에 넘긴다 (본문을 다시 만들지 않음)"""
    sent["url"] = req.full_url
    res = api.post("/judge", content=req.data, headers={"content-type": req.get_header("Content-type")})
    if res.status_code >= 400:
        raise urllib.error.HTTPError(req.full_url, res.status_code, "error", {}, io.BytesIO(res.content))
    return FakeResponse(res.content)


mcp_server.urllib.request.urlopen = fake_urlopen
tmp = tempfile.mkdtemp()
photo = os.path.join(tmp, "bottle.jpg")
Image.new("RGB", (40, 30), "white").save(photo, format="JPEG")
text_file = os.path.join(tmp, "note.txt")
open(text_file, "w").write("x")
broken = os.path.join(tmp, "broken.jpg")
open(broken, "wb").write(b"not an image")


def data(r):
    if r.structured_content and "result" in r.structured_content:
        return r.structured_content["result"]
    return json.loads(r.content[0].text) if len(r.content) == 1 else [json.loads(c.text) for c in r.content]


async def run():
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print("O" if ok else "X", name, "→", detail)

    async with Client(mcp_server.server) as c:
        names = sorted(t.name for t in (await c.list_tools()).tools)
        check("도구 3개 노출", names == ["get_disposal_rule", "judge_photo", "search_items"], names)

        r = await c.call_tool("search_items", {"query": "생수병"})
        hits = data(r)
        check("별칭 '생수병' → 투명 페트병(P01) 첫 번째", not r.is_error and hits[0]["id"] == "P01", hits[:1])

        r = await c.call_tool("search_items", {"query": "  "})
        check("빈 검색어 → 오류", r.is_error, r.content[0].text[-40:])

        r = await c.call_tool("get_disposal_rule", {"item_id": "p01"})
        rule = data(r)
        check("소문자 품목ID도 조회, 필수 조건에 라벨", not r.is_error and rule["name"] == "투명 페트병"
              and any("라벨" in a for a in rule["required"]), rule["required"])

        r = await c.call_tool("get_disposal_rule", {"item_id": "ZZ9"})
        check("없는 품목ID → 오류와 다음 행동 안내", r.is_error and "search_items" in r.content[0].text)

        r = await c.call_tool("judge_photo", {"image_path": os.path.join(tmp, "none.jpg")})
        check("없는 파일 → 오류", r.is_error, r.content[0].text[-30:])

        r = await c.call_tool("judge_photo", {"image_path": text_file})
        check("사진이 아닌 확장자 → 보내기 전에 거름", r.is_error and "판정 서버" not in r.content[0].text)

        r = await c.call_tool("judge_photo", {"image_path": photo})
        res = data(r)
        check("사진 판정 → 백엔드 규칙표 결과 그대로 (라벨 있음 → need_action)",
              not r.is_error and res["status"] == "need_action" and res["item"] == "P01"
              and any("라벨" in t for t in res["checklist"]) and sent["url"].endswith("/judge"),
              (res.get("status"), res.get("checklist")))

        r = await c.call_tool("judge_photo", {"image_path": photo, "answers": {"item_hint": "P05"}})
        res = data(r)
        check("answers 전달 (item_hint=P05 → 캔으로 확정)", not r.is_error and res["item"] == "P05", res.get("item"))

        r = await c.call_tool("judge_photo", {"image_path": broken})
        check("서버 오류(BAD_IMAGE) → 서버 문구를 그대로 전달", r.is_error and "사진을 읽을 수 없어요" in r.content[0].text)

    print(f"\n{sum(results)}/{len(results)} 통과")
    return all(results)


sys.exit(0 if asyncio.run(run()) else 1)
