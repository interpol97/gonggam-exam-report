#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""양성 대조 — **일부러 어긋나게 만든 입력에 정말 ✕ 가 나오는가.**

통과만 보고 검사기를 믿지 않는다. 검사기가 죽어 있어도 통과는 나온다.

    python gates/negative.py md        MD 대조가 막는가 (다섯 갈래)
    python gates/negative.py summary   요약본이 2쪽이면 막는가
    python gates/negative.py stress    긴 내용에서 쪽수가 어긋나면 막는가
    python gates/negative.py fields    빌더가 채우는 칸이 어긋나면 막는가 (열아홉 갈래)

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


# ──────────────────────────────────────────── 빌더가 채우는 칸 (em·key·radar·…)
def _blocked_by(out, needle):
    """막혔는가, 그리고 **그 검사가** 막았는가.

    막히기만 하면 통과로 치면 안 된다 — 엉뚱한 검사가 막아도 «OK» 가 찍혀,
    정작 지으려던 검사는 죽어 있는 채로 남는다. 차단 줄의 이름까지 본다.
    """
    for line in out.splitlines():
        if line.strip().startswith("[차단]") and needle in line:
            return True
    return False


def _deep(d):
    return json.loads(json.dumps(d, ensure_ascii=False))


def _build(exam_path, out_path, summary=False):
    args = ["scripts/report_build.py", exam_path, EX, out_path,
            "--summary" if summary else "--detail"]
    code, out = run(args)
    return code, out


def case_fields():
    """report.json 의 새 칸들을 열아홉 가지로 어긋나게 만들어 게이트가 막는지 본다.

    **양성 대조만으로는 모자란다** — 멀쩡한 표본이 통과하는 것을 먼저 본다.
    「0개를 재고 통과하는 검사」와 「멀쩡한 것을 막는 검사」는 둘 다 못 쓴다.

    표본은 examples/report.sample.json 이 아니라 **examples/samsung_h1_en 에서
    갓 지은 것**을 쓴다. 표본 json 두 개는 새 칸이 없어 아직 렌더조차 되지 않는다
    (HANDOFF § 5-2). 크롬은 쓰지 않는다 — 여섯 검사 전부 글자만 잰다.
    """
    if not os.path.isdir(EX):
        print("  표본이 없다: %s" % EX)
        return 1
    exam = os.path.join(EX, "exam.json")
    tmp = tempfile.mkdtemp(prefix="neg-fields-")
    try:
        r, sm = os.path.join(tmp, "r.json"), os.path.join(tmp, "s.json")
        for path, is_sum in ((r, False), (sm, True)):
            code, out = _build(exam, path, is_sum)
            if code != 0:
                print("  빌드 실패: %s" % out[-300:].replace("\n", " "))
                return 1

        # 강조를 **지목한** 한 벌도 짓는다 — 지목이 report.json 까지 갔는지 보려면
        # 지목이 있는 표본이 있어야 한다. 삼성고 exam.json 에는 emphasis 가 없다.
        exam_em = os.path.join(tmp, "exam_em.json")
        ex = json.load(io.open(exam, encoding="utf-8"))
        ex["emphasis"] = {"types": "어법", "chapters": "교과서 1과"}
        io.open(exam_em, "w", encoding="utf-8").write(json.dumps(ex, ensure_ascii=False))
        rem = os.path.join(tmp, "rem.json")
        code, out = _build(exam_em, rem, False)
        if code != 0:
            print("  강조 표본 빌드 실패: %s" % out[-300:].replace("\n", " "))
            return 1

        base_r = json.load(io.open(r, encoding="utf-8"))
        base_s = json.load(io.open(sm, encoding="utf-8"))
        base_e = json.load(io.open(rem, encoding="utf-8"))

        ok = True

        # ── 0. 멀쩡한 것이 통과하는가 (오검출 대조)
        print("  — 멀쩡한 표본이 통과하는가")
        for label, path, ex_path in (("상세본", r, exam), ("요약본", sm, exam),
                                     ("강조 지목한 상세본", rem, exam_em)):
            code, out = run(["scripts/gate_check.py", "--data", path, "--exam", ex_path])
            good = code == 0
            print("  %s %-34s %s" % ("OK  " if good else "★실패", label,
                                     "통과" if good else "멀쩡한 표본을 막았다 — 오검출이다"))
            if not good:
                print("       %s" % " / ".join(l.strip() for l in out.splitlines()
                                               if l.strip().startswith("[차단]"))[:400])
            ok = good and ok

        # ── 1~6. 일부러 어긋나게 만든 것을 막는가
        def m(fn, base=None):
            d = _deep(base if base is not None else base_r)
            fn(d)
            return d

        def two_key(d):
            d["overview"]["cards"][0]["key"] = "key"
            d["overview"]["cards"][1]["key"] = "key"

        def two_star(d):
            for st in d["killer"][0]["steps_flow"][:2]:
                st["em"] = "em"

        cases = [
            # (이름, 어긋난 report.json, 곁들일 exam.json, 막아야 할 검사 이름)
            ("① em 이 한 줄 빠짐", m(lambda d: d["types"][2].pop("em")), exam,
             "em 이 모든 줄에"),
            ("① em 이 참/거짓", m(lambda d: d["chapters"][0].__setitem__("em", True)), exam,
             "em 이 모든 줄에"),
            ("① 레이다 축에 em 빠짐", m(lambda d: d["radar"]["axes"][0].pop("em")), exam,
             "em 이 모든 줄에"),
            ("② key 가 한 카드에 빠짐",
             m(lambda d: d["overview"]["cards"][1].pop("key")), exam,
             "num·unit·key 가 모든 카드에"),
            ("② num 이 빠짐", m(lambda d: d["overview"]["cards"][0].pop("num")), exam,
             "num·unit·key 가 모든 카드에"),
            ("② 말 카드가 둘", m(two_key), exam, "강조 카드 하나"),
            ("③ 지목한 줄이 안 칠해짐",
             m(lambda d: [x.__setitem__("em", "") for x in d["types"]], base_e), exam_em,
             "지목한 줄이 칠해졌다"),
            ("③ 없는 줄을 지목", _deep(base_r), None, "지목한 줄이 있다"),
            ("③ 지목 없는데 칠해짐 (1위 자동 강조)",
             m(lambda d: d["types"][0].__setitem__("em", "em")), exam,
             "지목 없으면 안 칠한다"),
            ("③ 칠한 줄이 둘",
             m(lambda d: [x.__setitem__("em", "em") for x in d["chapters"][:2]]), exam,
             "칠한 줄 하나"),
            ("④ ok=1 인데 축이 둘",
             m(lambda d: d["radar"].__setitem__("axes", d["radar"]["axes"][:2])), exam,
             "축 셋 이상"),
            ("④ ok 가 참/거짓", m(lambda d: d["radar"].__setitem__("ok", True)), exam,
             "레이다 ok 값"),
            ("④ ok=1 인데 꼭짓점 없음",
             m(lambda d: d["radar"].__setitem__("points", "")), exam, "레이다 꼭짓점"),
            ("⑤ 한 목록에 ★ 가 둘", m(two_star), exam, "갈린 칸 하나"),
            ("⑤ conclusion 칸이 빠짐",
             m(lambda d: d["killer"][0]["steps_flow"][0].pop("conclusion")), exam,
             "푸는 순서 네 칸"),
            ("⑥ section 에 key 이름을 적음",
             m(lambda d: d["fill_blocks"][0].__setitem__("section", "study-plan"), base_s),
             exam, "채움 자리 이름"),
            ("⑥ 판형에 없는 자리",
             m(lambda d: d["fill_blocks"][1].__setitem__("section", "fill-nowhere"), base_s),
             exam, "채움 자리 이름"),
            ("⑥ section 이 아예 없음",
             m(lambda d: d["fill_blocks"][0].pop("section"), base_s), exam,
             "채움 자리 이름"),
            ("⑥ 한 자리에 둘",
             m(lambda d: d["fill_blocks"][1].__setitem__(
                 "section", d["fill_blocks"][0]["section"]), base_s), exam,
             "한 자리에 한 블록"),
        ]

        # 「없는 줄을 지목」은 exam.json 쪽을 어긋나게 만든다
        bogus = os.path.join(tmp, "exam_bogus.json")
        ex2 = _deep(ex)
        ex2["emphasis"] = {"types": "없는유형"}
        io.open(bogus, "w", encoding="utf-8").write(json.dumps(ex2, ensure_ascii=False))

        print("  — 어긋난 것을 막는가")
        for i, (name, broken, ex_path, needle) in enumerate(cases, 1):
            path = os.path.join(tmp, "case%02d.json" % i)
            io.open(path, "w", encoding="utf-8").write(json.dumps(broken, ensure_ascii=False))
            code, out = run(["scripts/gate_check.py", "--data", path,
                             "--exam", ex_path or bogus])
            hit = code != 0 and _blocked_by(out, needle)
            if code != 0 and not hit:
                print("  ★실패 %-34s 막히긴 했는데 «%s» 가 아닌 다른 검사가 막았다"
                      % (name, needle))
                ok = False
                continue
            ok = report(name, hit, out) and ok
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = {"md": case_md, "summary": case_summary, "stress": case_stress,
         "fields": case_fields}

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
