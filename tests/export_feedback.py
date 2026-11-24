"""운영 서버에서 '틀렸어요' 피드백을 모아 평가 세트 후보 목록을 만든다.

사진은 저장하지 않으므로 틀린 사진을 그대로 가져올 수는 없다. 대신 어떤 품목에서, 무엇이(품목/상태/장소)
틀렸고, AI가 무엇을 봤는지를 묶어서 '새로 찍어서 평가 세트(cases.json)에 넣을 사진' 목록을 만든다.

    ADMIN_TOKEN=... python tests/export_feedback.py                    # 운영 서버, 최근 200건
    ADMIN_TOKEN=... python tests/export_feedback.py --api http://127.0.0.1:5001 --out tests/results/feedback.md

흐름: 사용자 '틀렸어요' → 이 목록 → 같은 상황 사진 촬영 → cases.json 추가 → run_tests.py --save → compare_runs.py
"""
import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date

REASON = {"item": "품목", "state": "상태", "place": "배출 장소", "other": "기타", None: "이유 없음"}


def fetch(api, token, limit):
    req = urllib.request.Request(f"{api.rstrip('/')}/admin/api/judgments?only=wrong&limit={limit}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["items"]


def build_report(items, today=None):
    """'틀렸어요' 목록 → 품목·이유별로 묶은 마크다운"""
    today = today or date.today().isoformat()
    groups = defaultdict(list)
    for r in items:
        groups[(r["item"], r.get("reason"))].append(r)
    lines = [f"# 평가 세트 후보 ({today})", "",
             f"'틀렸어요' {len(items)}건을 품목과 이유로 묶었습니다. 많은 순서대로 같은 상황의 사진을 찍어 cases.json에 추가하세요.", ""]
    if not items:
        lines.append("틀렸어요 피드백이 없습니다.")
        return "\n".join(lines) + "\n"
    lines += ["| 품목 | 틀린 부분 | 건수 | 판정 결과 |", "|---|---|---|---|"]
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    for (item, reason), rows in ordered:
        statuses = ", ".join(sorted({r["status"] for r in rows}))
        lines.append(f"| {item} | {REASON.get(reason, reason)} | {len(rows)} | {statuses} |")
    for (item, reason), rows in ordered:
        lines += ["", f"## {item} · {REASON.get(reason, reason)} ({len(rows)}건)"]
        for r in rows[:10]:
            seen = ", ".join(f"{k}={v}" for k, v in (r.get("seen") or {}).items()) or "-"
            comment = f" · 의견: \"{r['comment']}\"" if r.get("comment") else ""
            lines.append(f"- [ ] {r['created_at'][:10]} {r['status']} · AI가 본 값: {seen}{comment}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.getenv("RESCAN_API_URL", "https://13-55-66-67.sslip.io"))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results", f"feedback_{date.today().isoformat()}.md"))
    a = ap.parse_args(argv)
    token = os.getenv("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN 환경 변수를 지정하세요.")
        return 2
    items = fetch(a.api, token, a.limit)
    text = build_report(items)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"{a.out}에 저장했어요")
    return 0


if __name__ == "__main__":
    sys.exit(main())
