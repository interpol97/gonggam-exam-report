#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""양성 대조 — **일부러 어긋나게 만든 입력에 정말 ✕ 가 나오는가.**

통과만 보고 검사기를 믿지 않는다. 검사기가 죽어 있어도 통과는 나온다.

    python gates/negative.py md        MD 대조가 막는가 (다섯 갈래)
    python gates/negative.py summary   요약본이 2쪽이면 막는가
    python gates/negative.py stress    긴 내용에서 쪽수가 어긋나면 막는가

전부 「막혀야 하는데 막혔다」면 exit 0 과 `negative control ok` 를 찍는다.
하나라도 **통과해 버리면** exit 1 — 검사기가 죽어 있다는 뜻이다.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PY = sys.executable
EX = os.path.join(SKILL, "examples", "samsung_h1_en")


def run(args, cwd=SKILL):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY] + args, cwd=cwd, env=env, capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, out


def report(name, blocked, detail=""):
    mark = "OK  " if blocked else "★실패"
    print("  %s %-34s %s" % (mark, name, "막힘" if blocked else "통과해 버렸다 — 검사기가 죽어 있다"))
    if detail and not blocked:
        print("       %s" % detail[:300].replace("\n", " "))
    return blocked


# ──────────────────────────────────────────────────────────── MD 대조
def case_md():
    """해설 MD 를 다섯 가지로 망가뜨려 report_build 가 막는지 본다."""
    if not os.path.isdir(EX):
        print("  표본이 없다: %s" % EX)
        return 1

    sol = None
    for f in os.listdir(EX):
        if "정답해설" in f and f.endswith(".md"):
            sol = os.path.join(EX, f)
    if not sol:
        print("  해설 MD 를 찾지 못했다")
        return 1

    orig = io.open(sol, encoding="utf-8").read()
    cases = []

    # ① 제목 줄의 정답을 바꾼다
    m = re.search(r"(##\s*(\d+)번\s+정답\s*)([①-⑩])", orig)
    if m:
        swap = "①" if m.group(3) != "①" else "②"
        cases.append(("제목 줄 정답 불일치", orig[:m.start(3)] + swap + orig[m.end(3):]))

    # ② meta 주석의 정답을 바꾼다
    m = re.search(r'("answer"\s*:\s*")(\d+)(")', orig)
    if m:
        bad = str(int(m.group(2)) % 5 + 1)
        cases.append(("meta 정답 불일치", orig[:m.start(2)] + bad + orig[m.end(2):]))

    # ③ 문항 하나를 통째로 지운다
    heads = [mm.start() for mm in re.finditer(r"(?m)^##\s*\d+번", orig)]
    if len(heads) >= 2:
        cases.append(("문항 누락", orig[:heads[-1]]))

    # ④ 이슈 flag 에서 이유를 뗀다
    m = re.search(r"(<!--\s*flag:\s*issue/[^\s—\-:]+)\s*[—\-:][^>]*(-->)", orig)
    if m:
        cases.append(("이슈 이유 없음", orig[:m.start()] + m.group(1) + " " + m.group(2) + orig[m.end():]))

    # ⑤ 모르는 이슈 갈래
    m = re.search(r"(<!--\s*flag:\s*issue/)([^\s—\-:]+)", orig)
    if m:
        cases.append(("모르는 이슈 갈래",
                      orig[:m.start(2)] + "난이도이상" + orig[m.end(2):]))

    if not cases:
        print("  망가뜨릴 자리를 찾지 못했다 — MD 규격이 바뀌었나?")
        return 1

    ok = True
    tmp = tempfile.mkdtemp(prefix="neg-md-")
    try:
        for name, broken in cases:
            io.open(sol, "w", encoding="utf-8").write(broken)
            code, out = run(["scripts/report_build.py",
                             os.path.join(EX, "exam.json"), EX,
                             os.path.join(tmp, "r.json"), "--detail"])
            ok = report(name, code != 0, out) and ok
    finally:
        io.open(sol, "w", encoding="utf-8").write(orig)      # 반드시 되돌린다
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


# ──────────────────────────────────────────────────────────── 요약본 1쪽
def case_summary():
    """발췌를 길게 넣어 2쪽이 되게 만들고, 게이트가 막는지 본다."""
    src = os.path.join(SKILL, "examples", "summary.sample.json")
    if not os.path.exists(src):
        print("  요약본 표본이 없다: %s" % src)
        return 1

    d = json.load(io.open(src, encoding="utf-8"))
    k = (d.get("killer") or [{}])[0]
    k["excerpt"] = ("이 문장은 요약본 한 장을 일부러 넘기기 위한 긴 발췌다. " * 14)
    d["killer"] = [k]

    tmp = tempfile.mkdtemp(prefix="neg-sum-")
    try:
        p = os.path.join(tmp, "long.json")
        io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
        code, out = run(["scripts/render_report.py", p, tmp, "--summary"])
        if code != 0:
            return 0 if report("요약본 긴 발췌(렌더 단계에서 차단)", True) else 1

        html = [f for f in os.listdir(tmp) if f.endswith(".html")]
        if not html:
            print("  렌더가 HTML 을 내지 않았다")
            return 1
        h = os.path.join(tmp, html[0])
        run(["scripts/render_pdf.py", h, h[:-5] + ".pdf"])
        code, out = run(["scripts/gate_check.py", tmp])
        return 0 if report("요약본 2쪽", code != 0, out) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ──────────────────────────────────────────────────────────── 쪽수 어긋남
def case_stress():
    """내용을 길게 만들어 쪽수가 어긋나는지, 어긋나면 게이트가 막는지 본다.

    이게 옛 방식이 실제로 깨지던 자리다 — «한 장에 20행» 상수가 내용 길이를
    못 따라가 표기 12쪽 / 실제 13쪽이 나왔다."""
    src = os.path.join(SKILL, "examples", "report.sample.json")
    d = json.load(io.open(src, encoding="utf-8"))
    for i in d.get("items", []):
        i["basis"] = (i.get("basis", "") +
                      " — 판정 근거를 길게 적으면 이렇게 두 줄이 된다. 내부본에서 흔한 길이다.")
        i["source"] = i.get("source", "") + " (지문 첫 8어절 식별)"

    tmp = tempfile.mkdtemp(prefix="neg-stress-")
    try:
        p = os.path.join(tmp, "stress.json")
        io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
        code, out = run(["scripts/render_report.py", p, tmp, "--internal"])
        if code != 0:
            print("  렌더 실패:", out[-300:])
            return 1
        html = [f for f in os.listdir(tmp) if f.endswith(".html")]
        h = os.path.join(tmp, html[0])
        run(["scripts/render_pdf.py", h, h[:-5] + ".pdf"])

        # 표기 쪽수와 실제 쪽수를 직접 잰다
        import fitz
        dec = re.findall(r"/ (\d+) 페이지", io.open(h, encoding="utf-8").read())
        n = len(fitz.open(h[:-5] + ".pdf"))
        same = bool(dec) and int(dec[0]) == n
        print("  %s 긴 내용에서 쪽수 일치            표기 %s / 실제 %d"
              % ("OK  " if same else "★실패", dec[0] if dec else "?", n))
        if same:
            return 0
        # 어긋났다면 게이트가 반드시 막아야 한다
        code, out = run(["scripts/gate_check.py", tmp])
        return 0 if report("어긋남을 게이트가 막는다", code != 0, out) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = {"md": case_md, "summary": case_summary, "stress": case_stress}

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2 or sys.argv[1] not in CASES:
        print(__doc__)
        raise SystemExit(1)
    which = sys.argv[1]
    print("\n=== 양성 대조 : %s ===" % which)
    rc = CASES[which]()
    print("\nnegative control ok" if rc == 0 else "\n양성 대조 실패 — 검사기가 죽어 있다")
    raise SystemExit(rc)
