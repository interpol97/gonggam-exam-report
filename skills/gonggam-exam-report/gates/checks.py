#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원장 GATES-v02.md 가 부르는 검사들.

    python gates/checks.py topdf <폴더>   폴더의 HTML 을 전부 PDF 로 → "pdf ok"
    python gates/checks.py mdlink         MD 문장이 리포트에 실렸나 → "md link ok"
    python gates/checks.py summary        요약본이 A4 한 장인가 → "summary one page ok"
    python gates/checks.py regress        옛 결함 셋이 되살아났나 → "regress ok"
    python gates/checks.py fields         빌더가 채우는 칸이 규격대로인가 → "fields ok"

전부 **못 재면 통과하지 않는다.** 잴 대상이 없으면 그것 자체가 실패다 —
0개를 재고 통과하는 것이 가장 나쁜 검사다.
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


def fail(msg):
    print("  ✕ %s" % msg)
    return 1


# ──────────────────────────────────────────────────────── topdf
def topdf(folder):
    folder = os.path.join(SKILL, folder) if not os.path.isabs(folder) else folder
    if not os.path.isdir(folder):
        return fail("폴더가 없다: %s" % folder)
    htmls = [f for f in sorted(os.listdir(folder)) if f.endswith(".html")]
    if not htmls:
        return fail("HTML 이 하나도 없다 — 앞 게이트가 실패했나")
    for h in htmls:
        src = os.path.join(folder, h)
        code, out = run(["scripts/render_pdf.py", src, src[:-5] + ".pdf"])
        if code != 0 or not os.path.exists(src[:-5] + ".pdf"):
            return fail("PDF 변환 실패 %s\n       %s" % (h, out[-400:].replace("\n", " ")))
        print("  · %s → PDF" % h)
    print("pdf ok")
    return 0


# ──────────────────────────────────────────────────────── mdlink
def norm(s):
    """비교용으로 고른다 — 마크다운 표시·따옴표·공백 차이를 없앤다.

    처음에는 MD 쪽만 벗기고 HTML 과 견줬다. **0개가 나왔다.**
    MD 의 백틱·별표를 내가 벗겼는데 리포트에는 그대로 남아 있어 글자가 달랐던 것이다.
    한쪽만 고르면 «연동이 끊겼다» 는 거짓 경보가 난다 — **양쪽을 같은 자로 고른다.**"""
    s = re.sub(r"<[^>]+>", " ", s)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&amp;", "&"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    s = re.sub(r"[*`>«»\"'‘’“”]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def mdlink():
    """MD → report.json → 리포트 HTML 이 **한 줄로 이어져 있는가.**

    이 회차의 핵심이다. 두 곳을 본다 —
      ① 리포트에 실린 해설이 **MD 에서 왔는가** (지어낸 것이 아닌가)
      ② 그 해설이 **종이에 찍혔는가** (데이터로만 실려 있는 게 아닌가)
    둘 다여야 「MD 를 고치면 리포트가 바뀐다」가 사실이다."""
    if not os.path.isdir(EX):
        return fail("표본이 없다: %s" % EX)
    sol = [f for f in os.listdir(EX) if "정답해설" in f and f.endswith(".md")]
    if not sol:
        return fail("해설 MD 를 찾지 못했다")
    md = io.open(os.path.join(EX, sol[0]), encoding="utf-8").read()

    tmp = tempfile.mkdtemp(prefix="gate-mdlink-")
    try:
        p = os.path.join(tmp, "r.json")
        code, out = run(["scripts/report_build.py", os.path.join(EX, "exam.json"), EX, p, "--detail"])
        if code != 0:
            return fail("report_build 실패\n       %s" % out[-400:].replace("\n", " "))
        code, out = run(["scripts/render_report.py", p, tmp])
        if code != 0:
            return fail("렌더 실패\n       %s" % out[-400:].replace("\n", " "))
        htmls = [f for f in os.listdir(tmp) if f.endswith(".html")]
        if not htmls:
            return fail("HTML 이 나오지 않았다")
        html = io.open(os.path.join(tmp, htmls[0]), encoding="utf-8").read()
        body = norm(re.sub(r"<style.*?</style>|<script.*?</script>", " ", html, flags=re.S | re.I))
        mdn = norm(md)

        # 리포트에 실린 해설 글을 모은다 — 킬러의 근거가 이 연동의 알맹이다
        d = json.load(io.open(p, encoding="utf-8"))
        killer = d.get("killer") or []
        if not killer:
            return fail("report.json 에 킬러문항이 없다 — 잴 것이 없다")

        texts = []
        for k in killer:
            if k.get("why"):
                texts.append(("%s번 정답 근거" % k.get("no"), k["why"]))
            for i, w in enumerate(k.get("wrong_reasons") or []):
                texts.append(("%s번 오답 근거 %d" % (k.get("no"), i + 1), w))
        if len(texts) < 3:
            return fail("킬러 해설이 3조각도 안 된다 — MD 에서 글을 못 끌어왔다")

        from_md, on_paper = [], []
        for label, t in texts:
            piece = norm(t)[:40]
            if len(piece) < 12:
                continue
            if piece in mdn:
                from_md.append(label)
            if piece in body:
                on_paper.append(label)

        print("  해설 조각 %d개 — MD 에서 온 것 %d개 · 종이에 찍힌 것 %d개"
              % (len(texts), len(from_md), len(on_paper)))
        for label, t in texts[:3]:
            print("  · %s: %s…" % (label, norm(t)[:44]))

        if not from_md:
            return fail("리포트의 해설이 MD 어디에도 없다 — 지어낸 글이 실리고 있다")
        if not on_paper:
            return fail("해설이 데이터로만 있고 종이에 안 찍힌다 — 템플릿이 안 쓰고 있다")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("md link ok")
    return 0


# ──────────────────────────────────────────────────────── summary
def summary():
    src = os.path.join(SKILL, "examples", "summary.sample.json")
    if not os.path.exists(src):
        return fail("요약본 표본이 없다: %s" % src)
    tmp = tempfile.mkdtemp(prefix="gate-sum-")
    try:
        code, out = run(["scripts/render_report.py", src, tmp, "--summary"])
        if code != 0:
            return fail("요약본 렌더 실패\n       %s" % out[-400:].replace("\n", " "))
        htmls = [f for f in os.listdir(tmp) if f.endswith(".html")]
        if not htmls:
            return fail("HTML 이 나오지 않았다")
        h = os.path.join(tmp, htmls[0])
        if "요약본" not in htmls[0]:
            return fail("파일 이름에 «요약본» 이 없다 — 게이트가 요약본으로 못 알아본다: %s" % htmls[0])
        code, out = run(["scripts/render_pdf.py", h, h[:-5] + ".pdf"])
        if code != 0:
            return fail("PDF 변환 실패\n       %s" % out[-400:].replace("\n", " "))
        import fitz
        n = len(fitz.open(h[:-5] + ".pdf"))
        print("  요약본 %d쪽" % n)
        if n != 1:
            return fail("A4 한 장이 규격인데 %d쪽이다" % n)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("summary one page ok")
    return 0


# ──────────────────────────────────────────────────────── regress
def regress():
    """이 저장소에서 실제로 났던 사고 셋이 되살아나지 않았는가."""
    src = os.path.join(SKILL, "examples", "report.sample.json")
    d = json.load(io.open(src, encoding="utf-8"))
    # 국어 «<보기>» 가 태그로 먹히던 사고
    d["items"][0]["source"] = "<보기> 참조 & 지문"
    d["summary"]["quote"] = 'a < b 이고 "인용" & 기호'

    tmp = tempfile.mkdtemp(prefix="gate-regress-")
    bad = 0
    try:
        p = os.path.join(tmp, "r.json")
        io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
        code, out = run(["scripts/render_report.py", p, tmp])
        if code != 0:
            return fail("렌더 실패\n       %s" % out[-400:].replace("\n", " "))
        htmls = [f for f in os.listdir(tmp) if f.endswith(".html")]
        html = io.open(os.path.join(tmp, htmls[0]), encoding="utf-8").read()

        # ① HTML escape
        if "<td><보기>" in html or "<보기> 참조" in html:
            print("  ✕ escape — «<보기>» 가 날것으로 박혔다. 화면에서 사라진다")
            bad += 1
        elif "&lt;보기&gt;" in html:
            print("  · escape ok — «<보기>» 가 글자로 남았다")
        else:
            print("  ✕ escape — 넣은 값을 HTML 에서 찾지 못했다. 검사가 0개를 재고 있다")
            bad += 1

        # ② 같은 섹션이 두 번호를 쓰지 않는가
        heads = re.findall(r'class="section-title">(\d+)\.\s*([^<]*)', html)
        titles = {}
        for num, t in heads:
            titles.setdefault(re.sub(r"\s+", " ", t).strip(), set()).add(int(num))
        if not heads:
            print("  ✕ 섹션 번호 — 제목을 하나도 못 찾았다. 검사가 0개를 재고 있다")
            bad += 1
        else:
            dup = {t: sorted(v) for t, v in titles.items() if len(v) > 1}
            if dup:
                print("  ✕ 섹션 번호 — 같은 제목이 여러 번호를 쓴다: %s" % dup)
                bad += 1
            else:
                print("  · 섹션 번호 ok — 제목 %d개, 한 섹션 = 한 번호" % len(titles))

        # ③ 동봉 폰트
        if "@font-face" in html and "ReportKR" in html and "cdn." not in html:
            print("  · 폰트 ok — 동봉 woff2 가 박혔고 외부 의존이 없다")
        else:
            print("  ✕ 폰트 — 동봉 폰트가 없거나 CDN 에 기댄다")
            bad += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if bad:
        return fail("옛 결함 %d건이 되살아났다" % bad)
    print("regress ok")
    return 0


# ──────────────────────────────────────────────────────── fields
def fields():
    """빌더가 채우는 칸 여섯이 **규격대로 채워지는가** — em · num/unit/key ·
    강조 지목 · 레이다 · 푸는 순서 · 채움 자리.

    크롬을 쓰지 않는다. 여섯 다 report.json 과 판형 글자만 재기 때문이다 —
    크롬이 없는 자리에서도 이 게이트는 돈다.

    **잰 개수를 함께 찍는다.** 통과만 찍으면 «칸이 하나도 없어서 통과» 를
    구별할 수 없다 — 0개를 재고 통과하는 것이 가장 나쁜 검사다.
    표본은 examples/report.sample.json 이 아니라 examples/samsung_h1_en 에서
    갓 짓는다. 표본 json 두 개에는 새 칸이 없어 아직 렌더도 되지 않는다.
    """
    if not os.path.isdir(EX):
        return fail("표본이 없다: %s" % EX)
    exam = os.path.join(EX, "exam.json")
    tmp = tempfile.mkdtemp(prefix="gate-fields-")
    try:
        # 강조를 지목한 exam.json 을 따로 짓는다 — 삼성고 원본에는 emphasis 가 없어
        # 「지목이 report.json 까지 갔는가」를 잴 수 없다
        ex = json.load(io.open(exam, encoding="utf-8"))
        ex["emphasis"] = {"types": "어법", "chapters": "교과서 1과"}
        exam_em = os.path.join(tmp, "exam_em.json")
        io.open(exam_em, "w", encoding="utf-8").write(json.dumps(ex, ensure_ascii=False))

        seen = {"em": 0, "카드": 0, "레이다 축": 0, "푸는 순서": 0, "채움 자리": 0, "강조": 0}
        for label, flag, ex_path in (("상세본", "--detail", exam_em),
                                     ("요약본", "--summary", exam_em)):
            out = os.path.join(tmp, "%s.json" % flag.strip("-"))
            code, log = run(["scripts/report_build.py", ex_path, EX, out, flag])
            if code != 0:
                return fail("%s 빌드 실패\n       %s" % (label, log[-400:].replace("\n", " ")))
            code, log = run(["scripts/gate_check.py", "--data", out, "--exam", ex_path])
            blocked = [l.strip() for l in log.splitlines() if l.strip().startswith("[차단]")]
            if code != 0:
                return fail("%s 이 새 칸 검사에 막혔다\n       %s"
                            % (label, " / ".join(blocked)[:500]))

            d = json.load(io.open(out, encoding="utf-8"))
            rows = (d.get("types") or []) + (d.get("chapters") or [])
            seen["em"] += len([r for r in rows if "em" in r])
            seen["강조"] += len([r for r in rows if r.get("em") == "em"])
            seen["카드"] += len([c for c in (d.get("overview") or {}).get("cards") or []
                               if all(k in c for k in ("num", "unit", "key"))])
            seen["레이다 축"] += len((d.get("radar") or {}).get("axes") or [])
            seen["푸는 순서"] += len([k for k in d.get("killer") or [] if k.get("steps_flow")])
            seen["채움 자리"] += len([b for b in d.get("fill_blocks") or [] if b.get("section")])
            print("  · %s — 게이트 통과" % label)

        print("  잰 것: %s" % " · ".join("%s %d" % (k, v) for k, v in seen.items()))
        empty = [k for k, v in seen.items() if not v]
        if empty:
            return fail("%s 를 0개 재고 통과했다 — 표본이 그 칸을 안 쓰면 "
                        "회귀 잠금이 아니다" % " · ".join(empty))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("fields ok")
    return 0


# ──────────────────────────────────────────────────────── shots (G13 준비)
def shots(out_dir=".gatework/shots"):
    """수동 검수(G13)용 — 만들어진 PDF 를 장마다 PNG 로 떠 둔다.

    **이건 게이트가 아니다.** 사람이 볼 그림을 준비할 뿐이다.
    「예쁘게 나왔다」를 실행 게이트로 위장하지 않는다 — 통과·차단을 말하지 않고
    파일만 남긴다. 판정은 사람이 하고 원장의 EVIDENCE 에 사람이 적는다."""
    try:
        import fitz
    except ImportError:
        return fail("PyMuPDF 가 필요하다 — pip install pymupdf")

    out = os.path.join(SKILL, out_dir) if not os.path.isabs(out_dir) else out_dir
    os.makedirs(out, exist_ok=True)

    pdfs = []
    for root in (".gatework/detail", ".gatework/internal", ".gatework/summary", ".gatework/mdout"):
        d = os.path.join(SKILL, root)
        if os.path.isdir(d):
            pdfs += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".pdf")]
    if not pdfs:
        return fail("뜰 PDF 가 없다 — 앞 게이트를 먼저 돌려라")

    n = 0
    for p in pdfs:
        doc = fitz.open(p)
        stem = re.sub(r"[^가-힣A-Za-z0-9]+", "-", os.path.basename(p)[:-4])[:46]
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72.0, 150 / 72.0), alpha=False)
            pix.save(os.path.join(out, "%s_p%02d.png" % (stem, i + 1)))
            n += 1
        print("  · %s — %d장" % (os.path.basename(p), len(doc)))
        doc.close()

    print("\n  PNG %d장 → %s" % (n, out))
    print("  이제 **사람이 본다.** 볼 것:")
    print("    · 잘린 글자 · 어색한 줄바꿈")
    print("    · 표가 페이지 경계에서 반쪽 난 자리 · 머리글 없이 이어지는 표")
    print("    · 킬러 카드가 읽히는가 (오답 근거까지)")
    print("    · 요약본이 40초 안에 읽히는가")
    print("  본 것을 GATES-v02.md 의 G13 EVIDENCE 에 사람이 적는다.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        raise SystemExit(1)
    if a[0] == "shots":
        raise SystemExit(shots(a[1] if len(a) > 1 else ".gatework/shots"))
    if a[0] == "topdf":
        raise SystemExit(topdf(a[1] if len(a) > 1 else ".gatework/detail"))
    if a[0] == "mdlink":
        raise SystemExit(mdlink())
    if a[0] == "summary":
        raise SystemExit(summary())
    if a[0] == "regress":
        raise SystemExit(regress())
    if a[0] == "fields":
        raise SystemExit(fields())
    print(__doc__)
    raise SystemExit(1)
