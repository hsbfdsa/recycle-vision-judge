"""compare_runs.py 검사 (AI 호출 없음). 실행: python tests/test_compare_runs.py"""
import copy, io, os, sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compare_runs as cr

before = cr.load(os.path.join(HERE, "results", "before.json"))
after = cr.load(os.path.join(HERE, "results", "after.json"))
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("O " if cond else "X ") + name + (f"  ({detail})" if detail and not cond else ""))


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cr.main(argv)
    return code, buf.getvalue()


b, a = os.path.join(HERE, "results", "before.json"), os.path.join(HERE, "results", "after.json")

res = cr.compare(before, after)
check("실제 개선 기록(before → after): 정답률 상승", res["new"]["최종 판정 정답률"] > res["old"]["최종 판정 정답률"], res["new"])
check("실제 개선 기록: 잘못된 통과가 늘지 않음", not any("잘못된 통과" in p for p in res["problems"]), res["problems"])
check("같은 결과끼리 비교 → 나빠진 곳 없음", cr.compare(after, after)["problems"] == [])

# 잘못된 통과를 하나 늘린 가짜 결과
worse = copy.deepcopy(after)
worse["summary"]["wrong_pass"] += 1
check("잘못된 통과 증가 → 문제로 잡음", any("잘못된 통과" in p for p in cr.compare(after, worse)["problems"]))

# 맞던 사진 하나를 틀리게 바꾼 가짜 결과
flip = copy.deepcopy(after)
target = next(r for r in flip["rows"] if cr._ok(r))
target["status"] = "pass" if target["expected_status"] != "pass" else "retake"
r2 = cr.compare(after, flip)
check("맞던 사진이 틀림 → 나빠진 사진 목록에 나옴", target["image"] in [k for k, _, _ in r2["worse"]], r2["worse"][:3])
check("--allow-flip 1 이면 사진 1장 뒤집힘은 허용",
      not any("맞던 사진" in p for p in cr.compare(after, flip, allow_flip=1)["problems"]))

code, out = run([a, a, "--strict"])
check("--strict, 같은 결과 → 종료 코드 0", code == 0, out[-200:])
import json, tempfile
tmp = os.path.join(tempfile.mkdtemp(), "worse.json")
json.dump(worse, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
code, out = run([a, tmp, "--strict"])
check("--strict, 나빠진 결과 → 종료 코드 1", code == 1 and "나빠짐" in out, out[-200:])
code, out = run([b, a, "--md"])
check("--md → 마크다운 표", out.startswith("| 지표 |") and "최종 판정 정답률" in out, out[:200])

print(f"\n{sum(results)}/{len(results)} 통과")
sys.exit(0 if all(results) else 1)
