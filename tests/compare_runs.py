"""평가 결과 두 개를 비교한다 (run_tests.py --save 로 만든 JSON). AI 호출 없음.

    python tests/compare_runs.py tests/results/before.json tests/results/after.json
    python tests/compare_runs.py 이전.json 새.json --strict     # 나빠졌으면 종료 코드 1 (배포 전 확인용)
    python tests/compare_runs.py 이전.json 새.json --md         # README·PR에 붙일 표

'나빠졌다'의 기준 (--strict):
  1) 잘못된 통과(처리가 필요한데 '통과' 안내)가 늘었다  ← 가장 나쁜 오류
  2) 최종 판정 정답률이 --tolerance(기본 0%p)보다 더 떨어졌다
  3) 이전에 맞던 사진이 이번에 틀렸다 (--allow-flip 개수까지는 허용)
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ok(row):
    want = row.get("expected_status")
    if want is None or "error" in row:
        return None
    return row["status"] in (want if isinstance(want, list) else [want])


def metrics(run):
    s = run["summary"]
    done = max(1, s["runs"] - s["errors"])
    secs = [r["seconds"] for r in run["rows"] if "seconds" in r]
    return {
        "품목 정확도": s["item_ok"] / done,
        "최종 판정 정답률": s["status_ok"] / max(1, s["status_total"]),
        "잘못된 통과": s["wrong_pass"],
        "틀린 단정": s["wrong"],
        "모름(unknown)": s["cautious"],
        "실패": s["errors"],
        "평균 응답(초)": statistics.mean(secs) if secs else None,
    }


def per_image(run):
    """사진별 정답 비율 (반복 실행이면 여러 번의 평균)"""
    acc = defaultdict(list)
    for r in run["rows"]:
        ok = _ok(r)
        if ok is not None:
            acc[r["image"]].append(ok)
        elif "error" in r:
            acc[r["image"]].append(False)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def compare(old, new, tolerance=0.0, allow_flip=0):
    mo, mn = metrics(old), metrics(new)
    po, pn = per_image(old), per_image(new)
    common = sorted(set(po) & set(pn))
    worse = [(k, po[k], pn[k]) for k in common if pn[k] < po[k]]
    better = [(k, po[k], pn[k]) for k in common if pn[k] > po[k]]
    flipped = [k for k, a, b in worse if a == 1.0 and b < 1.0]     # 항상 맞던 사진이 틀리기 시작
    problems = []
    if mn["잘못된 통과"] > mo["잘못된 통과"]:
        problems.append(f"잘못된 통과가 늘었어요 ({mo['잘못된 통과']} → {mn['잘못된 통과']})")
    drop = mo["최종 판정 정답률"] - mn["최종 판정 정답률"]
    if drop > tolerance + 1e-9:
        problems.append(f"최종 판정 정답률이 {drop * 100:.1f}%p 떨어졌어요")
    if len(flipped) > allow_flip:
        problems.append(f"맞던 사진 {len(flipped)}장이 틀렸어요")
    return {"old": mo, "new": mn, "worse": worse, "better": better, "flipped": flipped,
            "only_old": sorted(set(po) - set(pn)), "only_new": sorted(set(pn) - set(po)), "problems": problems}


def _fmt(k, v):
    if v is None:
        return "-"
    if k in ("품목 정확도", "최종 판정 정답률"):
        return f"{v * 100:.1f}%"
    if k == "평균 응답(초)":
        return f"{v:.2f}"
    return str(v)


def _delta(k, a, b):
    if a is None or b is None:
        return ""
    d = b - a
    if abs(d) < 1e-9:
        return "="
    if k in ("품목 정확도", "최종 판정 정답률"):
        return f"{d * 100:+.1f}%p"
    if k == "평균 응답(초)":
        return f"{d:+.2f}"
    return f"{d:+d}"


def report(res, md=False):
    lines = []
    if md:
        lines += ["| 지표 | 이전 | 이번 | 변화 |", "|---|---|---|---|"]
        for k in res["old"]:
            lines.append(f"| {k} | {_fmt(k, res['old'][k])} | {_fmt(k, res['new'][k])} | {_delta(k, res['old'][k], res['new'][k])} |")
    else:
        for k in res["old"]:
            lines.append(f"{k:<14} {_fmt(k, res['old'][k]):>8} → {_fmt(k, res['new'][k]):>8}  {_delta(k, res['old'][k], res['new'][k])}")
    if res["worse"]:
        lines.append("\n나빠진 사진:")
        lines += [f"  {k}  {a * 100:.0f}% → {b * 100:.0f}%" for k, a, b in res["worse"]]
    if res["better"]:
        lines.append("\n좋아진 사진:")
        lines += [f"  {k}  {a * 100:.0f}% → {b * 100:.0f}%" for k, a, b in res["better"]]
    if res["only_old"] or res["only_new"]:
        lines.append(f"\n한쪽에만 있는 사진: 이전 {len(res['only_old'])}장, 이번 {len(res['only_new'])}장 (비교에서 제외)")
    lines.append("\n판정: " + ("나빠짐 — " + " / ".join(res["problems"]) if res["problems"] else "나빠진 곳 없음"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="평가 결과 두 개 비교")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--strict", action="store_true", help="나빠졌으면 종료 코드 1")
    ap.add_argument("--tolerance", type=float, default=0.0, help="허용하는 정답률 하락 (%%p)")
    ap.add_argument("--allow-flip", type=int, default=0, help="맞던 사진이 틀려도 허용할 개수")
    ap.add_argument("--md", action="store_true", help="마크다운 표로 출력")
    a = ap.parse_args(argv)
    res = compare(load(a.old), load(a.new), a.tolerance / 100, a.allow_flip)
    print(report(res, a.md))
    return 1 if (a.strict and res["problems"]) else 0


if __name__ == "__main__":
    sys.exit(main())
