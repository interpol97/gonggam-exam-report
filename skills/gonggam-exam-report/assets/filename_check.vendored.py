# -*- coding: utf-8 -*-
"""내보내는 파일 이름이 규격인가 (§28).

이름은 자료가 학원 폴더에 쌓인 **뒤에** 값을 한다. 만들 때는 아무래도 좋지만,
석 달 뒤 «고2 24년 9모 워크북» 을 찾을 때 이름이 제각각이면 다 열어 봐야 한다.

    {브랜드}_{종류}_{학년}_{출처}[_{범위}].pdf

    공감에듀_분석지_H2_24년9월_고2.pdf
    공감에듀북스_워크북_H2_24년9월_고2_21-24_29-40.pdf
    공감에듀북스_멘토용_어법해설_H2_YBM_L5_Reading1.pdf

    python assets/filename_check.py <폴더>
"""
import re
import sys
from pathlib import Path

# 브랜드는 **그 자료의 표지·머리글에 실제로 찍히는 이름**을 쓴다.
# 파일 이름과 표지가 다르면 어느 쪽이 맞는지 매번 열어 봐야 한다.
BRAND = {
    # 머리글 «공감에듀 영어제작소»
    # 분석지부록 = 구문 전환 권말 부록(§23). 전환을 본문에 끼우면 단원마다 면이
    # 늘고 그 면이 거의 빈다 — 뒤로 빼서 여러 단원을 한 곳에 모은다.
    "공감에듀": ["분석지", "분석지부록", "지문변형대조", "동형모의고사",
                 "동형모의고사정답",
                 # 기출 분석 리포트 4종 (gonggam-exam-report). 출처는 EXAM 꼴을 쓴다 —
                 # 이 넷은 모의고사·교재가 아니라 «학교 한 회차» 가 출처다.
                 "기출분석리포트", "기출문제", "기출정답해설", "기출분석"],
    # 표지 «공감에듀북스»
    # 워크북은 학생용과 정답 두 벌로 나간다 — 동형모의고사·동형모의고사정답과 같은 꼴이다.
    "공감에듀북스": ["워크북", "워크북정답", "멘토용_어법해설"],
}
KIND = {k: b for b, ks in BRAND.items() for k in ks}
GRADE = ("H1", "H2", "H3")

# 출처 — 두 꼴뿐이다
MOCK = re.compile(r"^\d{2}년\d{1,2}월_고[123]$")          # 24년9월_고2
BOOK = re.compile(r"^[A-Za-z가-힣][\w가-힣]*(_[\w가-힣]+){1,3}$")  # 능률_공통영어2_1과
# 21-24 · 29-40 · 21번(지문 하나짜리 — 한 편만 담은 자료도 이름을 지을 수 있어야 한다)
RANGE = re.compile(r"^(\d{1,3}-\d{1,3}|\d{1,3}번)$")
# 학교 한 회차 — 명지고등학교_26년1학기중간_영어
EXAM = re.compile(r"^[가-힣A-Za-z][가-힣A-Za-z0-9]*_\d{2}년[12]학기(중간|기말)_[가-힣]{2,8}$")
# 꼬리칸 — 범위와 같은 자리에 붙는다. 2종(배포본/내부본), 분량 2종, 분석 축 셋.
# «요약본» 은 A4 한 장짜리다. 게이트가 **이 낱말로** 요약본을 알아보고
# 「1쪽을 넘기면 차단」을 건다 — 그래서 «요약» 이 아니라 반드시 «요약본» 이어야 한다.
TAIL = ("배포본", "내부본", "요약본", "상세본", "유형별", "출제별", "난이도별")
# 기출분석리포트는 이 넷 중 하나를 반드시 단다 (분량 둘 · 종 둘)
REPORT_TAILS = ("요약본", "상세본", "배포본", "내부본")
EXAM_KINDS = ("기출분석리포트", "기출문제", "기출정답해설", "기출분석")


def outname(kind, grade, source, rng=(), ext="pdf", tail=(), brand=None):
    """규격에 맞는 이름을 **만들어 준다.**

    검사만 두면 사람이 손으로 짓고 검사에서 걸린다. 짓는 쪽을 주면 애초에 안 어긋난다.
    브랜드는 종류가 정한다 — 그 자료의 표지에 찍히는 이름이다.

        outname("워크북", "H2", "24년9월_고2", ["21-24", "29-40"])
        → 공감에듀북스_워크북_H2_24년9월_고2_21-24_29-40.pdf
    """
    if kind not in KIND:
        raise ValueError(f"모르는 종류 «{kind}» — {' · '.join(KIND)}")
    if grade not in GRADE:
        raise ValueError(f"학년은 {' · '.join(GRADE)} 중 하나다 — «{grade}»")
    for t in tail:
        if t not in TAIL:
            raise ValueError(f"모르는 꼬리칸 «{t}» — {' · '.join(TAIL)}")
    # 기출 4종은 **그 학원 이름**으로 나간다 — 표지에 찍히는 이름이 곧 브랜드다.
    # 나머지는 종류가 브랜드를 정한다(공감에듀 / 공감에듀북스).
    if brand and kind not in EXAM_KINDS:
        raise ValueError(f"«{kind}» 의 브랜드는 종류가 정한다 — brand 를 주지 않는다")
    if kind in EXAM_KINDS and not brand:
        brand = "공감에듀"
    parts = [brand or KIND[kind], kind, grade, source] + list(rng) + list(tail)
    return "_".join(parts) + ("." + ext if ext else "")


def check(name):
    """한 이름을 본다. 걸린 자리를 모두 돌려준다 — 첫 하나에서 멈추지 않는다."""
    stem = re.sub(r"\.(pdf|png|html|zip|md)$", "", name)
    p = stem.split("_")
    bad = []
    if len(p) < 4:
        return [f"칸이 {len(p)}개다 — 브랜드_종류_학년_출처 로 넷은 있어야 한다"]

    brand, rest = p[0], p[1:]
    # 브랜드 판정은 종류를 안 뒤에 한다 — 기출 4종은 학원마다 다르다
    

    # 종류는 «멘토용_어법해설» 처럼 두 칸일 수 있다 — 긴 것부터 맞춰 본다
    kind = None
    for n in (3, 2, 1):
        cand = "_".join(rest[:n])
        if cand in KIND:
            kind, rest = cand, rest[n:]
            break
    if kind is None:
        return bad + [f"모르는 종류 «{rest[0]}» — {' · '.join(KIND)}"]
    if kind in EXAM_KINDS:
        if not re.match(r"^[가-힣A-Za-z][가-힣A-Za-z0-9]*$", brand):
            bad.append(f"브랜드 자리가 학원 이름이 아니다 «{brand}»")
    elif brand not in BRAND:
        bad.append(f"모르는 브랜드 «{brand}» — {' · '.join(BRAND)}")
    elif kind not in BRAND.get(brand, []):
        bad.append(f"«{kind}» 는 브랜드가 «{KIND[kind]}» 다 — 표지에 찍히는 이름을 쓴다")

    if not rest:
        return bad + ["학년과 출처가 없다"]
    if rest[0] not in GRADE:
        bad.append(f"학년이 없다 — «{rest[0]}» 자리에 {' · '.join(GRADE)} 가 와야 한다(§26)")
    else:
        rest = rest[1:]

    if not rest:
        return bad + ["출처가 없다"]

    # 뒤쪽이 «배포본»·«난이도별» 꼴이면 꼬리칸이다 — 범위보다 먼저 떼어 낸다
    tail = []
    while rest and rest[-1] in TAIL:
        tail.insert(0, rest.pop())

    # 뒤쪽이 «21-24» 꼴이면 범위다
    rng = []
    while rest and RANGE.match(rest[-1]):
        rng.insert(0, rest.pop())
    src = "_".join(rest)
    if not src:
        bad.append("출처가 없다 — 범위만 있다")
    elif kind in EXAM_KINDS:
        if not EXAM.match(src):
            bad.append(f"출처 꼴이 아니다 «{src}» — «명지고등학교_26년1학기중간_영어»")
    elif not (MOCK.match(src) or BOOK.match(src)):
        bad.append(f"출처 꼴이 아니다 «{src}» — «24년9월_고2» 또는 «능률_공통영어2_1과»")
    if kind in ("워크북", "워크북정답") and not rng:
        bad.append(f"{kind}인데 문항 범위가 없다 — «21-24_29-40» 처럼 붙인다")
    # 리포트의 꼬리칸은 **두 축**이 섞여 있다.
    #   분량 — 요약본(A4 한 장) · 상세본
    #   종   — 배포본(학부모) · 내부본(강사, 판정 근거가 더 붙는다)
    # 요약본을 강사용으로 만들 일은 없다(한 장에 판정 근거를 넣을 자리가 없다).
    # 그래서 넷 중 **하나만** 있으면 된다. 둘을 겹쳐 적게 만들면 이름만 길어진다.
    if kind == "기출분석리포트" and not [t for t in tail if t in REPORT_TAILS]:
        bad.append("리포트인데 분량·종이 없다 — %s 중 하나를 붙인다"
                   % " · ".join("«%s»" % t for t in REPORT_TAILS))
    if kind == "기출분석" and not [t for t in tail if t in ("유형별", "출제별", "난이도별")]:
        bad.append("분석인데 축이 없다 — «유형별»·«출제별»·«난이도별» 중 하나를 붙인다")
    return bad


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("  ✕ 폴더를 달라 — python assets/filename_check.py <폴더>")
        return 1
    root = Path(sys.argv[1])
    # 종류 목록에서 **자동으로** 만든다. 손으로 적어 두면 새 종류가 생겼을 때
    # 검사 대상에서 조용히 빠진다 — 동형모의고사가 실제로 그렇게 빠져 있었다.
    kinds = "|".join(re.escape(k.split("_")[0]) for k in KIND)
    names = sorted(x.name for x in root.iterdir()
                   if re.match(rf"^[가-힣A-Za-z][가-힣A-Za-z0-9]*_({kinds})", x.name))
    # 규격 이름이 아닌 산출물도 **세어서 보여 준다.** 앞머리로만 걸러 내면
    # 규격을 어긴 이름이 검사 대상에서 조용히 빠지고 «볼 파일이 없다» 가 찍힌다.
    # 0개를 읽고 통과하는 것이 가장 나쁜 검사다(audit-protocol).
    others = sorted(x.name for x in root.iterdir()
                    if x.is_file() and x.suffix.lower() in (".pdf", ".xlsx")
                    and x.name not in names and not x.name.startswith("_"))
    if others:
        print(f"  ✕ 규격 이름이 아닌 산출물 {len(others)}개 — 이름부터 고친다")
        for o in others[:12]:
            print(f"     {o}")
        if len(others) > 12:
            print(f"     … 그리고 {len(others) - 12}개 더")
    if not names:
        print("  ✕ 규격에 맞는 파일이 0개다 — 통과가 아니라 실패다"
              if others else "  · 볼 파일이 없다")
        return 1 if others else 0
    ok = 0
    for n in names:
        b = check(n)
        if b:
            print(f"  ✕ {n}")
            for x in b:
                print(f"       {x}")
        else:
            ok += 1
    print()
    print(f"  규격 {ok} / {len(names)}")
    return 0 if ok == len(names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
