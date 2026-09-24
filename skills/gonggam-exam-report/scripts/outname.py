#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
산출 파일명 — **규격은 여기에 없다.**

정본은 `gonggam-material-studio/assets/filename_check.py` 하나다.
이 파일은 «시험 회차를 그 규격의 출처 칸으로 바꾸는 일»만 한다.

    공감에듀_기출분석리포트_H1_명지고등학교_26년1학기중간_영어_배포본.pdf
    공감에듀_기출분석_H1_명지고등학교_26년1학기중간_영어_난이도별.md

규격을 두 벌로 들고 있으면 반드시 갈라진다. 한때 이 파일이 자기 문법을 따로 갖고
있었고, 공용 검사기는 다른 것을 재고 있었다 — 그래서 위임으로 바꿨다.

    python outname.py <폴더>      규격 밖 이름을 세어서 보여 준다
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# scripts → skills/<skill> → skills → <plugin> → plugins
PLUGINS = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SHARED = os.path.join(PLUGINS, "gonggam-material-studio", "assets")


# 이 플러그인만 따로 받는 사람이 있다(공개 배포판). 그때는 옆에 자료제작소가 없다.
# 그래서 같은 파일을 assets/ 에 **동봉**해 두고, 옆에 정본이 있으면 정본이 이긴다.
# 규격을 두 벌 «만드는» 것이 아니라 한 벌을 복사해 두는 것이다 —
# 갈라지지 않게 배포할 때 다시 복사한다(HANDOFF 의 배포 절차).
VENDORED = os.path.join(os.path.dirname(HERE), "assets")


def _shared():
    """공용 검사기를 불러온다.

    ① 옆에 자료제작소가 있으면 **그 정본**을 쓴다
    ② 없으면 동봉본(assets/filename_check.vendored.py)을 쓴다
    ③ 둘 다 없으면 **막는다** — 자기 문법을 따로 만들지 않는다
    """
    if os.path.exists(os.path.join(SHARED, "filename_check.py")):
        if SHARED not in sys.path:
            sys.path.insert(0, SHARED)
        import filename_check
        return filename_check

    vend = os.path.join(VENDORED, "filename_check.vendored.py")
    if os.path.exists(vend):
        import importlib.util
        spec = importlib.util.spec_from_file_location("filename_check_vendored", vend)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    raise SystemExit(
        "파일명 규격을 찾지 못했습니다. 둘 중 하나가 있어야 합니다:\n"
        "  %s\\filename_check.py            (자료제작소가 함께 깔린 경우)\n"
        "  %s\\filename_check.vendored.py   (이 플러그인만 받은 경우)\n"
        "  이 스킬은 규격을 따로 만들지 않습니다." % (SHARED, VENDORED)
    )


TERM_RE = re.compile(r"(\d{2,4})\D*?([12])\s*학기\s*(중간|기말)")


def exam_source(school, term, subject):
    """학교 한 회차를 공용 규격의 출처 칸으로 만든다.

        ("명지고등학교", "2026-1학기 중간고사", "영어") → 명지고등학교_26년1학기중간_영어
    """
    m = TERM_RE.search(str(term))
    if not m:
        raise ValueError(
            "학기를 읽지 못했습니다: «%s» — «2026-1학기 중간고사» 꼴로 주세요" % term
        )
    year, sem, mid = m.group(1), m.group(2), m.group(3)
    year = year[-2:]                                    # 2026 → 26
    school = re.sub(r"[\s_]+", "", str(school or ""))
    subject = re.sub(r"[\s_]+", "", str(subject or ""))
    if not school or not subject:
        raise ValueError("학교명과 과목이 모두 있어야 합니다.")
    return "%s_%s년%s학기%s_%s" % (school, year, sem, mid, subject)


def outname(kind, grade, school, term, subject, tail=(), ext="pdf", brand=None):
    """공용 outname 에 그대로 넘긴다. 브랜드는 종류가 정한다 — 여기서 고르지 않는다."""
    fc = _shared()
    src = exam_source(school, term, subject)
    # 브랜드는 그 자료의 표지에 찍히는 이름 — 학원마다 다르다
    name = fc.outname(kind, grade, src, ext=ext, tail=list(tail), brand=brand)
    bad = fc.check(name)
    if bad:                                             # 지어 놓고 스스로 검사한다
        raise ValueError("규격을 벗어난 이름입니다: %s\n  %s" % (name, "\n  ".join(bad)))
    return name


def audit(folder):
    fc = _shared()
    names = [f for f in sorted(os.listdir(folder))
             if f.lower().endswith((".pdf", ".html", ".md"))]
    ok, bad = [], []
    for f in names:
        (ok if not fc.check(f) else bad).append(f)
    print("규격 %d개 / 규격 밖 %d개" % (len(ok), len(bad)))
    for f in bad:
        print("  [규격 밖] %s" % f)
        for x in fc.check(f):
            print("       %s" % x)
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        sys.exit(audit(sys.argv[1]))
    print(__doc__)
    print(outname("기출분석리포트", "H1", "명지고등학교", "2026-1학기 중간고사", "영어",
                  tail=["배포본"], ext="pdf"))
    print(outname("기출분석리포트", "H1", "명지고등학교", "2026-1학기 중간고사", "영어",
                  tail=["배포본"], ext="pdf", brand="더케이학원"))
    print(outname("기출분석", "H1", "명지고등학교", "2026-1학기 중간고사", "영어",
                  tail=["난이도별"], ext="md"))
