#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam.json (수치) + MD 2종 (글)  →  report.json

**같은 내용을 두 번 쓰지 않는다.** 예전에는 Claude 가 report.json 에 해설을 쓰고,
MD 에 또 썼다. 둘이 어긋나도 아무도 몰랐다. 이제 글은 MD 한 곳에만 있고
리포트는 그 글을 **가져다 쓴다** — 강사가 MD 의 해설 문장을 다듬으면
다시 빌드하는 것만으로 리포트에 반영된다.

    exam.json          수치 — 번호·유형·배점·난이도·출처·정답·confidence·flags
    …기출문제.md        원문 — 발문·지문·선지
    …기출정답해설.md     긴 글 — 정답 근거·오답 근거·푸는 순서·필요 개념
            └──→ report_build.py ──→ report.json ──→ render_report.py

사용:
    python report_build.py <exam.json> <md폴더> <out/report.json> [--detail|--summary]
    python report_build.py … --excerpt-lines 10     발췌 줄 수를 직접 정할 때

계약 정본: references/md-contract.md
스키마 정본: references/report-schema.md

막는 것 (조용히 넘어가지 않는다):
    1. MD 의 문항 번호 집합 ≠ exam.json 의 번호 집합
    2. 제목 줄 · meta 주석 · exam.json 이 어긋남 (정답·배점·난이도·유형)
    3. 킬러문항인데 오답 근거·정답 근거·푸는 순서·필요 개념이 없음
    4. 이슈 표시인데 이유가 없음
    5. 닫힌 목록에 없는 이슈 갈래
"""

import io
import json
import math
import os
import re
import sys

DIFFICULTIES = ("상", "중상", "중", "중하", "하")

# 이슈 갈래는 닫힌 목록이다. 새 갈래가 필요하면 md-contract.md 를 먼저 고친다.
ISSUE_KINDS = ("복수정답", "조건누락", "범위밖", "배점과다", "유형급변")

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

# ⓐ~ⓩ — 고난도 내신의 «<보기> ⓐ~ⓔ + 조합 선지» 꼴. 선지 ①~⑤ 가 ⓐ~ⓔ 의 조합을 고르므로
# 보기를 못 읽으면 문항이 통째로 뜻을 잃는다 (명지고2 2026-1학기 기말 34번에서 드러났다).
# 국어는 ⓐ 가 아니라 **ㄱ·ㄴ·ㄷ·ㄹ** 로 보기를 단다. 그게 그 과목의 관례다.
# 여기에 없어서 국어 목업의 <보기> 가 보기로 안 잡히고 발문과 한 덩어리로
# 발췌 상자에 흘러들었다 — 글자는 살아남지만 <보기> 상자가 서지 않았다.
# 「영어에서 됐으니 됐다」가 통하지 않는 자리다.
HANGUL_MARKS = "ㄱㄴㄷㄹㅁㅂㅅㅇ"
CIRCLED_LETTERS = "".join(chr(c) for c in range(0x24D0, 0x24EA)) + HANGUL_MARKS

# 서술형을 가리키는 유형 이름. 학교마다 «서답형» 으로도 쓴다.
ESSAY_WORDS = ("서술형", "서답형", "논술형")

# 킬러문항 선정 — 기본은 기계가 고른다. 사람이 고르려면 exam.json 의
# `killer_override` 로만 — 그래야 «누가 왜 골랐나» 가 파일에 남는다.
KILLER_MAX = 5              # 상세본 최대
KILLER_MIN = 3              # 상세본 권장 하한 (상 문항이 그보다 적으면 있는 만큼)
KILLER_SUMMARY = 1          # 요약본
ISSUES_SUMMARY = 1
TYPES_SUMMARY = 3           # 요약본은 배점 상위 3개만 (summary-spec.md § 2-1)

# 발췌 한도 — **줄 수와 글자 수를 둘 다** 본다.
# 원고 한 줄이 긴 문단이면 종이에서 대여섯 줄로 접힌다. 줄만 세면 여섯 줄을 지켰는데
# 2쪽이 난다. 요약본 여유분은 실측 약 22mm ≈ 네 줄뿐이다 (summary-spec.md § 5).
EXCERPT_DETAIL = 8
EXCERPT_CHARS_DETAIL = 900
EXCERPT_SUMMARY = 6
EXCERPT_CHARS_SUMMARY = 420         # 6줄 × 70자 (본문 폭 182mm)
CHARS_PER_LINE = 70
ISSUE_EXCERPT_SUMMARY = (1, 60)     # 요약본 이슈 발췌는 한 줄 60자
ELLIPSIS = " …"                     # 잘랐으면 잘랐다고 남긴다. 조용히 버리지 않는다

# 요약본 한 장을 지키는 것은 CSS 가 아니라 글자 수다 (summary-spec.md § 5).
# 자를 수 없는 칸(사람이 쓴 문장)은 막지 않고 주의로 알린다 — 잘라내면 말이 끊긴다.
SUMMARY_LIMITS = [
    ("next_action", 45), ("summary.quote", 30), ("summary.desc", 90),
    ("overview.highlight", 45), ("difficulty.summary", 45),
    ("difficulty.discriminator", 90), ("meta.scope", 60),
]

# ── 요약본 «채움 블록» ────────────────────────────────────────────────────
# 이슈가 없으면 요약본 아래가 34.3mm 빈다(있으면 7.2mm). 34mm 가 비면 «덜 만든 종이» 로
# 보인다 — 원장님 지시로 남는 자리에 들어갈 것을 **우선순위 순서로** 넘긴다.
# 무엇을 어떤 차례로 줄지는 여기서 정하고, 남은 높이를 재서 켜는 것은 렌더러가 한다.
FILL_STUDY_ROWS = 2         # «앞의 2주만» — 학부모가 읽는 것은 «다음에 뭘 하나» 다
FILL_PARENT_ROWS = 2
FILL_ROW_CHARS = CHARS_PER_LINE     # 한 줄 70자 — 채움 블록의 한 줄도 같은 폭을 쓴다
# (key, 제목, 판형 자리 이름)
#   key    = 상세본 섹션 이름. 「이미 섹션으로 실렸나」를 이 이름으로 본다
#   자리   = 요약본 판형의 SECTION:… 이름. 둘은 **다르다**
# 처음엔 key 하나뿐이었고, 렌더러가 그 key 로 자리를 찾다 셋 다 「켤 자리 없음」으로
# 빠졌다. 그래서 요약본 아래가 53mm 비어도 아무 것도 안 켜졌다 — 수학 목업에서
# 드러난 결함이다. 영어는 이슈 문항이 그 자리를 채워 안 보였다.
FILL_PLAN = [
    ("study-plan", "다음 학습 전략", "fill-plan"),
    ("parent-note", "가정에서 도와주실 것", "fill-home"),
    ("difficulty-detail", "난이도 5단 상세", "fill-difficulty"),
]

# 「본문참조」는 정답이 아니라 **정답을 적지 않았다는 말**이다. 학부모가 받는 한 장에
# 이 글자가 찍히면 그 종이는 못 쓴다 — 주의가 아니라 차단이다.
EMPTY_ANSWERS = ("본문참조", "본문 참조", "해설참조", "해설 참조", "정답참조", "정답 참조",
                 "채점기준참조", "채점 기준 참조", "별도", "별도해설", "생략", "서술형", "-")

# 근거가 없을 때 채우는 «학원이 할 일 한 줄». 빈 문자열로 두면 렌더가 막힌다.
NEXT_ACTION_DEFAULT = "학원은 %s을 다음 수업부터 따로 잡아 다룹니다."
NEXT_ACTION_FALLBACK = "학원은 이번에 갈린 문항을 다음 수업부터 따로 잡아 다룹니다."

DETAIL_SECTIONS = ["overview", "items", "type-chart", "chapter-ratio",
                   "difficulty", "killer", "study-plan", "parent-note", "summary"]
SUMMARY_SECTIONS = ["overview", "type-chart", "radar", "difficulty", "killer", "summary"]

# 섹션마다 report.json 에 있어야 하는 것. 템플릿이 실제로 읽는 키와 같다.
SECTION_NEEDS = {
    "overview": ["overview.desc", "overview.highlight", "overview.cards", "meta.scope"],
    "items": ["items"],
    "type-chart": ["types"],
    # 레이다 — 유형 막대와 같은 데이터를 다른 꼴로 본다. 좌표는 빌더가 낸다.
    # 이 줄이 없어서, 판형에 자리가 있는데도 sections_summary 에 적으면
    # 「템플릿에 없는 섹션」으로 막혔다 — 켤 길이 없는 자리였다.
    "radar": ["radar.points"],
    "chapter-ratio": ["chapters", "chapter_desc"],
    "difficulty": ["difficulty.summary", "difficulty.discriminator"],
    "killer": ["killer"],
    "grade-cut": ["grade_cut.basis", "grade_cut.disclaimer", "grade_cut.cuts"],
    "study-plan": ["study_plan", "study_plan_desc"],
    "parent-note": ["parent_note"],
    "summary": ["summary.quote", "summary.desc", "disclaimer"],
    # 이슈 상자는 데이터가 켜고 끈다 — 빈 목록이면 저절로 사라진다 (summary-spec.md § 2-1).
    # 그래서 요구하는 데이터가 없다. sections 에 적어도 되고 안 적어도 된다.
    "issues": [],
}

# exam.json 에서 그대로 옮기는 «긴 글» 칸. 여기 없는 것은 계산해서 만든다.
PASSTHROUGH = ["brand", "cover", "overview", "chapter_desc", "study_plan_desc",
               "study_plan", "parent_note", "summary", "disclaimer", "grade_cut",
               "next_action"]

ITEM_FIELDS = ("no", "type", "points", "difficulty", "source", "answer", "basis", "confidence")
ITEM_OPTIONAL = ("answer_source", "note")


class BuildError(Exception):
    pass


def fail(lines):
    """모아서 한 번에 낸다. 한 건씩 고치고 다시 돌리는 일이 없도록."""
    if isinstance(lines, str):
        lines = [lines]
    seen, uniq = set(), []
    for line in lines:                  # 같은 말을 두 번 하지 않는다
        if line not in seen:
            seen.add(line)
            uniq.append(line)
    raise BuildError("%d건\n  - %s" % (len(uniq), "\n  - ".join(uniq)))


# ---------------------------------------------------------------- 자잘한 것
def read_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read().replace("﻿", "")


def num(v):
    """배점은 정수가 아니다. 실제 학교 시험은 3.1·3.4·2.8 처럼 쪼갠다
    (명지고2 2026-1학기 기말은 38문항 중 34개가 소수 배점이었다).
    int() 로 받으면 3.1 이 3 이 되어 배점 합이 100 에서 95 로 주저앉는다."""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def fmt_num(v):
    """3.0 은 «3», 3.1 은 «3.1». 표에 «3.0점» 이 찍히지 않게."""
    f = num(v)
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else ("%g" % round(f, 2))


def is_essay(type_):
    t = str(type_ or "")
    return any(w in t for w in ESSAY_WORDS)


def norm_answer(v):
    """«②» 와 «2» 는 같은 정답이다. 서술형의 «본문참조» 는 그대로 둔다."""
    s = " ".join(("" if v is None else str(v)).split())      # 겹친 공백은 같은 값으로 본다
    if len(s) == 1 and s in CIRCLED:
        return str(CIRCLED.index(s) + 1)
    return s


def circled(n):
    try:
        i = int(n)
    except (TypeError, ValueError):
        return str(n)
    return CIRCLED[i - 1] if 1 <= i <= len(CIRCLED) else str(n)


def lookup(data, path):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def find_md(md_dir, keyword):
    """이름이 길어도(공감에듀_기출정답해설_H1_…) 낱말로 찾는다."""
    if not os.path.isdir(md_dir):
        fail("MD 폴더가 없습니다: %s" % md_dir)
    hits = sorted(n for n in os.listdir(md_dir)
                  if n.endswith(".md") and keyword in n)
    # «기출문제» 로 찾을 때 «기출정답해설» 이 걸리지 않게 한다
    if keyword == "기출문제":
        hits = [n for n in hits if "정답해설" not in n]
    if not hits:
        fail("%s MD 가 없습니다: %s 안에 «%s» 가 이름에 든 .md 파일이 있어야 합니다."
             % (keyword, md_dir, keyword))
    if len(hits) > 1:
        fail("%s MD 가 여러 개입니다: %s" % (keyword, " · ".join(hits)))
    return os.path.join(md_dir, hits[0])


# ---------------------------------------------------------------- MD 파싱
FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEAD_RE = re.compile(r"^##\s*(\d+)\s*(?:번|\.)?\s*(.*)$")
META_RE = re.compile(r"<!--\s*meta:\s*(\{.*?\})\s*-->", re.S)
FLAG_RE = re.compile(r"<!--\s*flag:\s*(.+?)\s*-->", re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
LABEL_RE = re.compile(r"^\*\*(.+?)\*\*\s*(?:[—–-]\s*)?(.*)$")
SEP_RE = re.compile(r"\s(?:—|–|-|:)\s")

TITLE_POINTS = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*점\s*\]")     # 3.4점 처럼 쪼갠 배점
TITLE_DIFF = re.compile(r"난이도\s*(중상|중하|상|중|하)")
TITLE_ANSWER = re.compile(r"정답\s*([^\s·\[\]]+)")


def parse_front_matter(text):
    m = FM_RE.search(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.split("#")[0].strip()
    return fm, text[m.end():]


def split_blocks(text, path):
    """`## 11번 …` 단위로 쪼갠다. 같은 번호가 두 번 나오면 막는다."""
    body = parse_front_matter(text)[1]
    blocks, cur = [], None
    for line in body.splitlines():
        m = HEAD_RE.match(line)
        if m:
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(), "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    seen = {}
    dup = []
    for b in blocks:
        if b["no"] in seen:
            dup.append("%s: %d번 제목 줄이 두 번 나옵니다." % (os.path.basename(path), b["no"]))
        seen[b["no"]] = b
    if dup:
        fail(dup)
    return seen


def parse_meta_comment(block, path, errors):
    m = META_RE.search("\n".join(block["lines"]))
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        errors.append("%s %d번: meta 주석이 JSON 이 아닙니다 (%s)"
                      % (os.path.basename(path), block["no"], e))
        return None


def parse_flag_comments(block, path, errors):
    """`<!-- flag: issue/복수정답 — 이유 -->` 를 읽는다. 이유가 없으면 막는다."""
    out = []
    for m in FLAG_RE.finditer("\n".join(block["lines"])):
        raw = " ".join(m.group(1).split())
        if raw.lower().startswith("meta:"):
            continue
        parts = SEP_RE.split(raw, 1)
        kind = parts[0].strip()
        reason = plain(parts[1]) if len(parts) > 1 else ""
        where = "%d번" % block["no"]
        if kind == "killer":
            out.append({"kind": "killer", "reason": reason})
            continue
        if not kind.startswith("issue/"):
            errors.append("%s: 알 수 없는 flag 갈래입니다 «%s» — killer 또는 issue/<갈래>"
                          % (where, kind))
            continue
        sub = kind[len("issue/"):]
        if sub not in ISSUE_KINDS:
            errors.append("%s: 알 수 없는 이슈 갈래입니다 «%s» (쓸 수 있는 것: %s)"
                          % (where, sub, " · ".join(ISSUE_KINDS)))
            continue
        if not reason:
            errors.append("%s: 이슈 «%s» 에 이유가 없습니다 — "
                          "`<!-- flag: issue/%s — 왜 이슈인지 -->` 꼴로 적습니다."
                          % (where, sub, sub))
            continue
        out.append({"kind": sub, "reason": reason})
    return out


def parse_title(rest):
    """`정답 ②  [5점] · 난이도 상 · 빈칸추론` 을 읽는다. 없는 칸은 None.

    **정답·유형은 «정답» 으로 시작하는 해설 제목 줄에서만 읽는다.** 원문 MD 의 제목은
    발문이라 그 안의 `·` 를 유형으로 오해한다 — 실제로 「어법상 틀린 부분·이유·수정이…」
    에서 «이유» 를 유형으로 읽었다 (명지고2 31번).

    정답은 한 낱말이 아니다. 서술형은 문장이 통째로 온다
    (「정답 ask if your wish was to add an interactive element [5점] · …」)."""
    out = {"answer": None, "points": None, "difficulty": None, "type": None}
    body = rest.strip()
    is_solution = body.startswith("정답")
    if is_solution:
        head = body[len("정답"):]
        cut = len(head)
        for mark in ("[", "·"):                  # 배점·난이도 앞까지가 정답이다
            i = head.find(mark)
            if i >= 0:
                cut = min(cut, i)
        out["answer"] = norm_answer(head[:cut])
    m = TITLE_POINTS.search(rest)
    if m:
        out["points"] = num(m.group(1))
    m = TITLE_DIFF.search(rest)
    if m:
        out["difficulty"] = m.group(1)
    if is_solution:
        segs = [s.strip() for s in body.split("·")]
        for s in segs[1:]:
            s = re.sub(r"\(.*?\)\s*$", "", s).strip()
            if not s or s.startswith("난이도") or "정답" in s or "[" in s:
                continue
            out["type"] = s
            break
    return out


def parse_labeled(lines):
    """`**정답 근거** — …` 같은 덩어리로 나눈다."""
    out, cur = {}, None
    for line in lines:
        if COMMENT_RE.match(line.strip()):
            continue
        m = LABEL_RE.match(line.strip())
        if m:
            cur = m.group(1).strip()
            out.setdefault(cur, [])
            if m.group(2).strip():
                out[cur].append(m.group(2).strip())
            continue
        if cur is not None:
            out[cur].append(line.rstrip())
    return {k: [x for x in v] for k, v in out.items()}


IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
UNDER_RE = re.compile(r"__(.+?)__", re.S)
STRIKE_RE = re.compile(r"~~(.+?)~~", re.S)
ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.S)
LEAD_RE = re.compile(r"^\s*(?:>+\s*|[-*+]\s+|\d+[.)]\s+)")


def plain(s):
    """MD 표시를 벗긴 **종이에 찍을 글자**. 산문은 전부 이 문을 지난다.

    자리마다 따로 처리하면 어느 자리를 빠뜨렸는지 아무도 모른다 — 실제로 발췌에서는
    인용 표시를 뗐는데 오답 근거에서는 백틱이 그대로 종이에 찍혔다. 이 저장소에는 더 큰
    같은 사고의 기록도 있다: 원고의 `<i>`·`**강조**` 가 글자로 찍혀 이미 나간 PDF 466개
    중 138개가 그랬다(해설 한 권에만 2,631자리).

    렌더러는 값에 든 `<`·`&` 를 **언제나 글자로** 본다 (render_report.esc).
    그러니 «꼴» 은 데이터가 아니라 템플릿이 준다 — 여기서는 표시를 벗기기만 한다."""
    s = str(s or "")
    s = IMG_RE.sub("", s)
    s = LINK_RE.sub(r"\1", s)               # 링크는 글자만 남긴다
    s = s.replace("`", "")                   # 원문 인용 백틱
    for rx in (BOLD_RE, UNDER_RE, STRIKE_RE, ITALIC_RE):
        s = rx.sub(r"\1", s)
    s = LEAD_RE.sub("", s)                   # 줄머리 인용·글머리표
    return " ".join(s.split()).strip()


def bullets_of(lines):
    out = []
    for line in lines:
        m = BULLET_RE.match(line)
        if m and m.group(1).strip():
            out.append(plain(m.group(1)))
    return [x for x in out if x]


STEP_EM = "★"
STEP_ARROW = re.compile(r"\s*(?:→|->)\s*")


def split_steps(rows):
    """푸는 순서 한 줄을 «하는 일 → 결론» 으로 가른다.
    규격: references/layout-grammar.md §5 · md-contract.md

        1. It is 와 that 을 지워본다 → 문장이 깨진다
        2. ★ It is 뒤 요소의 품사를 본다 → conceivable = 형용사 ∴ 가주어
        3. that 뒤 절의 완전성을 본다 → what ✗ / that ✓

    ★ 는 «실제로 갈린 칸» 이다. 본본은 셋 중 하나만 칠했다 — 강조는 하나뿐이다.
    화살표가 없으면 결론 칸은 빈다. 지어내지 않는다.
    렌더러에 「만약」이 없으므로 세 칸 모두 **모든 줄에** 온다.
    """
    out = []
    for row in rows:
        t = row.strip()
        em = ""
        if t.startswith(STEP_EM):
            em, t = "em", t.lstrip(STEP_EM).strip()
        parts = STEP_ARROW.split(t, 1)
        out.append({"text": parts[0].strip(),
                    "conclusion": parts[1].strip() if len(parts) > 1 else "",
                    "em": em,
                    "value": t})          # 옛 판형이 쓰던 {{value}} 를 살려 둔다
    marked = [s for s in out if s["em"]]
    if len(marked) > 1:
        return out, ["푸는 순서에 ★ 가 %d개입니다 (%s) — 갈린 칸은 하나입니다. "
                     "하나만 남기십시오 (layout-grammar.md §0-2)"
                     % (len(marked), " · ".join(s["text"][:14] for s in marked))]
    return out, []


def text_of(lines):
    return plain(" ".join(x.strip() for x in lines
                          if x.strip() and not BULLET_RE.match(x)))


def strip_markup(s):
    """모범답안은 종이에 그대로 찍힌다. 앞뒤 구분 기호까지 떼고 한 줄로 만든다."""
    return plain(s).strip(" —–-:")


def is_empty_answer(s):
    """«본문참조» 는 정답이 아니라 정답을 적지 않았다는 말이다."""
    t = " ".join(str(s or "").split()).strip(" .·")
    return (not t) or t in EMPTY_ANSWERS


LEFTOVER_RE = re.compile(r"`|\*\*|~~")


def sweep_markup(node, path="report"):
    """나가는 글자에 마크다운 표시가 남았는가. 남았으면 **막는다.**

    「고쳤다」를 믿지 않고 산출물에서 잰다. 이 저장소에서 원고의 강조 표시가 글자로
    찍힌 PDF 가 466개 중 138개였다 — 그때도 코드는 «고쳤다» 고 되어 있었다."""
    bad = []
    if isinstance(node, dict):
        for k, v in node.items():
            bad += sweep_markup(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad += sweep_markup(v, "%s[%d]" % (path, i))
    elif isinstance(node, str):
        m = LEFTOVER_RE.search(node)
        if m:
            near = node[max(0, m.start() - 24):m.start() + 30].strip()
            bad.append("%s: 마크다운 표시가 그대로 남았습니다 — «…%s…» "
                       "(학부모 종이에 그 기호가 찍힙니다)" % (path, near))
    return bad


def table_answer(v, type_=""):
    """문항표의 정답 칸. 서술형이면 «서술형» 한 낱말, 객관식이면 정답 그대로.

    「본문참조」는 우리끼리 쓰는 말이다 — 학부모가 표에서 그 글자를 보면 «무슨 본문?» 이
    된다. 표의 정답 칸은 좁아서 모범답안이 들어가지 않고, 넣을 필요도 없다.
    모범답안은 킬러 카드와 해설이 맡는다. 칸에는 «어떤 꼴인가» 만 있으면 된다.

    **숫자인지로 가르지 않는다.** 복수정답 문항의 정답은 «3,4» 다 — 숫자가 아니라고
    «서술형» 이라 찍으면 거짓이 된다 (명지고2 25번)."""
    if is_essay(type_):
        return "서술형"
    s = norm_answer(v)
    return "서술형" if is_empty_answer(s) else s


def split_choices(lines):
    """선지를 ①~⑤ 단위로 자른다. 한 줄에 몰려 있어도 나눈다."""
    picked = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        marks = [c for c in s if c in CIRCLED]
        if s[0] in CIRCLED or len(marks) >= 2:
            picked.append(s)
    if not picked:
        return []
    joined = " ".join(picked)
    parts = re.split(r"(?=[%s])" % CIRCLED, joined)
    out = []
    for p in parts:
        if not p.strip():
            continue
        # 번호(①②…)는 떼어 담는다 — 요약본 템플릿이 1부터 다시 매긴다
        # (summary-spec.md § 2-3). 번호를 두 번 찍으면 «1 ① …» 이 된다.
        out.append(plain(p.lstrip(CIRCLED)))
    return [c for c in out if c]


def split_givens(lines):
    """«<보기> ⓐ~ⓔ» 를 읽는다. 선지 ①~⑤ 가 이것들의 조합을 고르는 꼴이다.

    **번호(ⓐⓑ…)는 떼지 않는다** — 선지와 오답 근거가 그 기호로 보기를 가리키기 때문이다
    (「⑤ = ⓑ,ⓒ,ⓓ」 · 「ⓐ 는 … 가장 그럴듯한 함정이다」). 선지는 템플릿이 번호를 매기지만
    보기는 기호 자체가 뜻을 갖는다."""
    picked = []
    for line in lines:
        s = line.strip()
        while s.startswith(">"):
            s = s[1:].lstrip()
        if not s or s.startswith("<!--"):
            continue
        # 선지 줄이 보기를 가리킨다(「① ⓐ, ⓑ  ② ⓐ, ⓒ, ⓔ …」). 그 줄은 **선지**다 —
        # 보기로 읽으면 한 줄이 열여덟 토막으로 부서진다. 선지가 먼저다.
        if s[0] in CIRCLED or len([c for c in s if c in CIRCLED]) >= 2:
            continue
        marks = [c for c in s if c in CIRCLED_LETTERS]
        if s[0] in CIRCLED_LETTERS or len(marks) >= 2:
            picked.append(s)
    if not picked:
        return []
    parts = re.split(r"(?=[%s])" % CIRCLED_LETTERS, " ".join(picked))
    out = [plain(p) for p in parts if p.strip()]
    return [g for g in out if g]


COND_RE = re.compile(r"^조건\s*\d*\s*[.)]?\s*(.+)$")


def conditions_of(lines):
    """서술형의 «조건» 상자. 선지가 없는 문항은 이것이 선지 자리를 쓴다.

    번호(조건 1.)는 떼어 담는다 — 선지와 같은 규칙으로, 번호는 템플릿이 매긴다."""
    out = []
    for line in lines:
        s = line.strip()
        while s.startswith(">"):
            s = s[1:].lstrip()
        m = COND_RE.match(s)
        if m and m.group(1).strip():
            out.append(plain(m.group(1)))
    return [c for c in out if c]


def passage_of(lines):
    """지문 줄 전부. 선지·조건·주석·표시는 뺀다. 자르는 것은 clip_lines 가 한다."""
    out = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("<!--") or s.startswith("**"):
            continue
        probe = s
        while probe.startswith(">"):
            probe = probe[1:].lstrip()
        if COND_RE.match(probe):
            continue            # 조건은 conditions 로 따로 나간다 — 두 번 싣지 않는다
        if s[0] in CIRCLED or len([c for c in s if c in CIRCLED]) >= 2:
            continue
        if probe and (probe[0] in CIRCLED_LETTERS
                      or len([c for c in probe if c in CIRCLED_LETTERS]) >= 2):
            continue            # <보기> ⓐ~ⓔ 는 givens 로 따로 나간다
        # 인용 표시·백틱·강조는 마크다운 문법이다. 발췌는 종이에 그대로 찍힌다
        s = plain(s)
        if s:
            out.append(s)
    return out


def clip_lines(lines, max_lines, max_chars):
    """줄 수와 글자 수를 **둘 다** 본다.

    원고 한 줄이 긴 문단이면 종이에서 대여섯 줄로 접힌다 — 줄만 세면 여섯 줄을
    지켰는데 2쪽이 난다 (summary-spec.md § 5). 잘랐으면 `…` 를 남긴다:
    조용히 버리면 「왜 뒷문장이 없지」를 아무도 모른다."""
    out, used, cut = [], 0, False
    for line in lines[:max_lines]:
        room = max_chars - used
        if len(line) > room:
            if room >= 20:                      # 쓸 만한 길이가 남았을 때만 잘라 담는다
                head = line[:room]
                if " " in head:
                    head = head.rsplit(" ", 1)[0]
                head = head.rstrip(" ,.;:·")
                if head:
                    out.append(head + ELLIPSIS)
            elif out:
                out[-1] = out[-1].rstrip() + ELLIPSIS
            cut = True
            break
        out.append(line)
        used += len(line) + 1
    if not cut and len(lines) > max_lines and out:
        out[-1] = out[-1] + ELLIPSIS
    return out


# ---------------------------------------------------------------- 검사
def check_item_fields(items):
    errors, seen = [], set()
    for i, it in enumerate(items):
        no = it.get("no")
        where = "%s번" % no if no is not None else "items[%d]" % i
        if no is None:
            errors.append("exam.json %s: no 가 없습니다." % where)
            continue
        if no in seen:
            errors.append("exam.json: %d번이 두 번 있습니다." % no)
        seen.add(no)
        for f in ITEM_FIELDS:
            if it.get(f) in (None, ""):
                errors.append("exam.json %s: %s 가 없습니다. (report-schema.md § items)" % (where, f))
        if it.get("difficulty") not in (None, "") and it["difficulty"] not in DIFFICULTIES:
            errors.append("exam.json %s: difficulty «%s» — %s 다섯 중 하나여야 합니다."
                          % (where, it["difficulty"], " · ".join(DIFFICULTIES)))
        if it.get("confidence") not in (None, "", "high", "low"):
            errors.append("exam.json %s: confidence «%s» — high · low 둘 중 하나입니다."
                          % (where, it["confidence"]))
    return errors


def check_numbers(exam_nos, q_nos, a_nos):
    """번호 집합이 셋 다 같아야 한다. 하나라도 어긋나면 그 뒤 분석이 전부 어긋난다."""
    errors = []
    for name, nos in (("기출문제.md", q_nos), ("기출정답해설.md", a_nos)):
        missing = sorted(exam_nos - nos)
        extra = sorted(nos - exam_nos)
        if missing:
            errors.append("%s 에 없는 문항: %s (exam.json 에는 있습니다)"
                          % (name, " · ".join("%d번" % n for n in missing)))
        if extra:
            errors.append("%s 에만 있는 문항: %s (exam.json 에 없습니다)"
                          % (name, " · ".join("%d번" % n for n in extra)))
    return errors


def check_cross(item, title, meta, where):
    """제목 줄 ↔ meta 주석 ↔ exam.json. 어느 문항 어느 필드가 다른지 말한다."""
    errors = []
    fields = (("answer", "정답"), ("points", "배점"),
              ("difficulty", "난이도"), ("type", "유형"))
    for key, label in fields:
        exam_v = norm_answer(item.get(key)) if key == "answer" else item.get(key)
        title_v = title.get(key)
        meta_v = meta.get(key) if meta else None
        if key == "answer" and meta_v is not None:
            meta_v = norm_answer(meta_v)
        if key == "points":
            # 배점은 3.1 처럼 쪼개진다. int() 로 받으면 3.1 과 3.4 가 같아진다
            title_v = None if title_v is None else num(title_v)
            meta_v = None if meta_v is None else num(meta_v)
            exam_v = None if exam_v in (None, "") else num(exam_v)
        if title_v is not None and meta_v is not None and title_v != meta_v:
            errors.append("%s %s: 제목 줄 «%s» ≠ meta 주석 «%s»"
                          % (where, label, title_v, meta_v))
        if meta_v is not None and exam_v not in (None, "") and meta_v != exam_v:
            errors.append("%s %s: meta 주석 «%s» ≠ exam.json «%s»"
                          % (where, label, meta_v, exam_v))
        if meta_v is None and title_v is not None and exam_v not in (None, "") and title_v != exam_v:
            errors.append("%s %s: 제목 줄 «%s» ≠ exam.json «%s»"
                          % (where, label, title_v, exam_v))
    return errors


# ---------------------------------------------------------------- 고르기
def pick_killers(items, limit):
    """난이도 «상» 중 배점이 높은 순. 동점이면 번호가 빠른 쪽. 최대 limit 개.

    사람이 고르지 않는다 — 회차마다 «느낌» 이 달라지면 리포트끼리 비교가 안 된다."""
    top = [it for it in items if it.get("difficulty") == "상"]
    top.sort(key=lambda it: (-float(it.get("points") or 0), int(it["no"])))
    return top[:limit]


def build_fill_blocks(report, items, sections, notes):
    """요약본에서 남는 자리에 들어갈 것 — **우선순위 순서**로 담는다.

    지키는 것 셋.
    1. **데이터가 없으면 블록을 넘기지 않는다.** 빈 상자가 켜지면 안 된다
    2. **줄이는 것은 자르는 것과 다르다.** 4주 계획을 `…` 로 끊지 않고 **앞의 2주만** 담는다
    3. 이미 섹션으로 실리는 것은 채움으로 또 내지 않는다 (같은 장에 두 번 나온다)

    높이를 재서 켜는 것은 렌더러다. 여기서는 «무엇을 어떤 차례로» 만 정한다."""
    blocks = []

    def add(spec, rows):
        key, title, section = spec
        if not rows or key in sections:
            return
        blocks.append({"key": key, "title": title, "section": section, "rows": rows})

    plan = [p for p in (report.get("study_plan") or []) if isinstance(p, dict)]
    add(FILL_PLAN[0],
        [{"week": plain(p.get("week")), "focus": plain(p.get("focus")),
          "todo": plain(p.get("todo"))}
         for p in plan[:FILL_STUDY_ROWS] if p.get("todo") or p.get("focus")])

    add(FILL_PLAN[1],
        [plain(x) for x in (report.get("parent_note") or [])[:FILL_PARENT_ROWS] if plain(x)])

    rows = []
    for label, count, points in difficulty_counts(items):
        if not count:
            continue                     # 없는 칸은 싣지 않는다
        nos = [int(i["no"]) for i in items if i.get("difficulty") == label]
        text = "·".join(str(n) for n in sorted(nos))
        if len(text) > FILL_ROW_CHARS:   # 번호 목록은 줄 수 있다 — 전체는 문항표에 있다
            keep = []
            for n in sorted(nos):
                if len("·".join(keep + [str(n)])) > FILL_ROW_CHARS - len(ELLIPSIS):
                    break
                keep.append(str(n))
            text = "·".join(keep) + ELLIPSIS
        rows.append({"label": label, "count": count,
                     "points": points, "nos": text + "번"})
    add(FILL_PLAN[2], rows)

    # 채우려다 2쪽이 되면 «채우려다 망친» 것이다. 자르지 않고 알린다.
    for b in blocks:
        for r in b["rows"]:
            text = r if isinstance(r, str) else " ".join(str(v) for v in r.values())
            if len(text) > FILL_ROW_CHARS:
                notes.append("채움 블록 «%s» 의 한 줄이 %d자입니다(한 줄 %d자) — "
                             "줄이지 않으면 요약본이 2쪽이 될 수 있습니다."
                             % (b["title"], len(text), FILL_ROW_CHARS))
    return blocks


def read_override(exam, items):
    """exam.json 의 `killer_override` — **사람이 고르는 유일한 길**.

    기계 규칙(난이도 상 중 배점순)은 회차마다 같지만 사람 판단은 다르다. 그래서
    손으로 고르려면 **파일에 남겨야 한다** — 반년 뒤에 «왜 이 문항이 킬러였지» 를
    알 수 있어야 하기 때문이다. 리포트에도 «수동 선정» 이 남는다.

    (실제로 필요했다: 명지고2 기말은 배점순으로 고르면 서답형 셋이 1~3위라
     리포트가 서술형 얘기만 하게 됐다. 원장님이 객관식을 섞어 다시 고르셨다.)"""
    raw = exam.get("killer_override")
    if raw in (None, "", [], {}):
        return None, []                 # 없으면(빈 목록이어도) 기계가 고른다
    errors = []
    if not isinstance(raw, list):
        return None, ["killer_override 는 번호 목록이어야 합니다 (예: [36, 34, 16, 31, 25])."]
    nos, seen = [], set()
    known = set(int(it["no"]) for it in items)
    for v in raw:
        try:
            n = int(v)
        except (TypeError, ValueError):
            errors.append("killer_override 에 번호가 아닌 값이 있습니다: %r" % (v,))
            continue
        if n not in known:
            errors.append("killer_override 의 %d번은 exam.json 에 없는 문항입니다." % n)
        elif n in seen:
            errors.append("killer_override 에 %d번이 두 번 있습니다." % n)
        else:
            seen.add(n)
            nos.append(n)
    if len(nos) > KILLER_MAX:
        errors.append("killer_override 가 %d개입니다 — 최대 %d개입니다 (한 장에 들어가지 "
                      "않습니다). 앞에서부터 고르세요." % (len(nos), KILLER_MAX))
    return (nos if not errors else None), errors


def aggregate(items, key):
    rows = {}
    for it in items:
        name = it.get(key)
        r = rows.setdefault(name, {"name": name, "count": 0, "points": 0})
        r["count"] += 1
        r["points"] += num(it.get("points"))
    out = list(rows.values())
    out.sort(key=lambda r: (-r["points"], -r["count"], str(r["name"])))
    for r in out:
        r["points"] = round(r["points"], 1)      # 3.0999999 를 종이에 찍지 않는다
    return out


CARD_NUM = re.compile(r"^\s*([0-9][0-9,.]*)\s*(.*)$")


def split_cards(cards, errors):
    """«38문항» 을 값과 단위로 가른다 — 숫자는 크게, 단위는 작게 붙인다.
    규격: references/layout-grammar.md §3

    숫자로 시작하지 않는 카드는 «말» 카드다(본본의 「It ~ that 강조 vs 가주어」).
    그 자리가 강조 카드다. 다만 **넷 중 하나만** 강조한다(§0-2) —
    둘을 칠하면 둘 다 안 보인다. 둘 이상이면 막고 사람에게 고르게 한다.
    """
    # 값은 «모든 카드»에 온다. 렌더러에 「만약」이 없어서, 한 칸이라도 빠지면
    # 렌더가 막힌다. 그래서 참/거짓이 아니라 class 에 그대로 꽂는 문자열이다.
    word = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        v = str(c.get("value", ""))
        m = CARD_NUM.match(v)
        c["key"] = ""
        if m:
            c["num"], c["unit"] = m.group(1), m.group(2)
        else:
            c["num"], c["unit"] = v, ""
            c["key"] = "key"
            word.append(c.get("label") or v)
    if len(word) > 1:
        errors.append("숫자 카드 중 «말» 카드가 %d개입니다 (%s) — 강조는 하나뿐입니다. "
                      "하나만 남기고 나머지는 숫자로 쓰십시오 (layout-grammar.md §0-2)"
                      % (len(word), " · ".join(word)))
    return cards


def mark_emphasis(rows, name, where, errors):
    """어느 막대를 칠할지 **데이터가 지목한다.** 규격: layout-grammar.md §6

    1위를 자동으로 칠하지 않는다. 본본은 1위(분사 10개)를 칠하지 않고
    4위(접속사·관계사 4개)를 칠했다 — 1위는 스스로 교정한 것이라 문제가
    아니었고, 4위는 한 지문에 몰려 전부 놓친 것이라 문제였다.
    개수가 아니라 뜻이 강조를 정한다. 지목이 없으면 아무 것도 칠하지 않는다.
    """
    # 빈 값이라도 «모든 줄»에 둔다 — 렌더러에 「만약」이 없다.
    for r in rows:
        r["em"] = ""
    if not name:
        return
    for r in rows:
        if str(r.get("name")) == str(name):
            r["em"] = "em"
            return
    errors.append("%s 강조로 «%s» 를 지목했는데 그런 줄이 없습니다. "
                  "있는 줄: %s" % (where, name, " · ".join(str(r.get("name")) for r in rows)))


RADAR_R = 72.0          # viewBox 0 0 200 200, 중심 (100,100)
RADAR_C = 100.0
RADAR_RINGS = (0.25, 0.5, 0.75, 1.0)


def build_radar(rows):
    """유형별 배점을 레이다 좌표로 편다. 규격: layout-grammar.md §9-2

    판형은 계산을 못 한다(치환만 한다). 그래서 «어디에 점을 찍는가» 는 여기서 낸다.
    SVG 는 y 가 아래로 자라므로 12시에서 시작해 시계 방향으로 돈다.

    축이 셋 미만이면 **그리지 않는다** — 둘로는 삼각형도 안 된다. ok 를 비워 보낸다.
    """
    n = len(rows)
    if n < 3:
        return {"ok": "", "points": "", "rings": [], "spokes": [], "axes": []}
    top = max(num(r.get("points")) for r in rows) or 1.0

    def at(i, frac):
        a = math.radians(-90 + 360.0 * i / n)
        return (RADAR_C + RADAR_R * frac * math.cos(a),
                RADAR_C + RADAR_R * frac * math.sin(a))

    pts, axes, spokes = [], [], []
    for i, r in enumerate(rows):
        x, y = at(i, num(r.get("points")) / top)
        pts.append("%.1f,%.1f" % (x, y))
        sx, sy = at(i, 1.0)
        spokes.append({"x2": "%.1f" % sx, "y2": "%.1f" % sy})
        # 이름은 고리 **밖**에 둔다. 왼쪽 반원이면 오른쪽 맞춤 — 글자가 그림을 안 먹는다.
        lx, ly = at(i, 1.17)
        anchor = "middle" if abs(lx - RADAR_C) < 8 else ("start" if lx > RADAR_C else "end")
        axes.append({"name": r.get("name"), "value": fmt_num(r.get("points")),
                     "count": r.get("count"),
                     "lx": "%.1f" % lx, "ly": "%.1f" % (ly + 3), "anchor": anchor,
                     "em": r.get("em") or ""})
    rings = [{"points": " ".join("%.1f,%.1f" % at(i, f) for i in range(n))}
             for f in RADAR_RINGS]
    return {"ok": "1", "points": " ".join(pts), "rings": rings,
            "spokes": spokes, "axes": axes, "top": fmt_num(top)}


def difficulty_counts(items):
    out = []
    for d in DIFFICULTIES:
        rows = [it for it in items if it.get("difficulty") == d]
        out.append((d, len(rows), round(sum(num(it.get("points")) for it in rows), 1)))
    return out


# ---------------------------------------------------------------- 본체
def build(exam_path, md_dir, out_path, summary=False, excerpt_lines=None):
    exam = json.loads(read_text(exam_path))
    items = exam.get("items")
    if not isinstance(items, list) or not items:
        fail("exam.json 에 items 가 없습니다: %s" % exam_path)

    notes = []                      # 막지는 않지만 사람이 봐야 하는 것
    errors = check_item_fields(items)
    if errors:
        fail(errors)

    q_path = find_md(md_dir, "기출문제")
    a_path = find_md(md_dir, "기출정답해설")
    q_blocks = split_blocks(read_text(q_path), q_path)
    a_blocks = split_blocks(read_text(a_path), a_path)

    exam_nos = set(int(it["no"]) for it in items)
    errors += check_numbers(exam_nos, set(q_blocks), set(a_blocks))
    if errors:
        fail(errors)

    if excerpt_lines:
        max_lines, max_chars = excerpt_lines, excerpt_lines * CHARS_PER_LINE
    elif summary:
        max_lines, max_chars = EXCERPT_SUMMARY, EXCERPT_CHARS_SUMMARY
    else:
        max_lines, max_chars = EXCERPT_DETAIL, EXCERPT_CHARS_DETAIL
    by_no = {}
    for it in items:
        no = int(it["no"])
        qb, ab = q_blocks[no], a_blocks[no]
        where = "%d번" % no

        q_meta = parse_meta_comment(qb, q_path, errors)
        a_meta = parse_meta_comment(ab, a_path, errors)
        errors += check_cross(it, parse_title(ab["title"]), a_meta, where)
        # 문제 MD 는 배점만 적는다 — 제목 줄에 정답을 쓰지 않기 때문이다
        q_title = parse_title(qb["title"])
        if q_meta:
            errors += check_cross(it, q_title, q_meta, "%d번 (기출문제.md)" % no)
        elif q_title.get("points") is not None and num(q_title["points"]) != num(it["points"]):
            errors.append("%d번 (기출문제.md) 배점: 제목 줄 «%s» ≠ exam.json «%s»"
                          % (no, q_title["points"], it["points"]))

        flags = list(it.get("flags") or [])
        for f in (a_meta or {}).get("flags", []) + (q_meta or {}).get("flags", []):
            if f not in flags:
                flags.append(f)

        marks = parse_flag_comments(ab, a_path, errors) + parse_flag_comments(qb, q_path, errors)
        issues = [m for m in marks if m["kind"] != "killer"]
        # flags 에 issue 를 적었으면 이유를 단 주석이 반드시 있어야 한다
        for f in flags:
            if str(f).startswith("issue/"):
                sub = str(f)[len("issue/"):]
                if sub not in ISSUE_KINDS:
                    errors.append("%d번: 알 수 없는 이슈 갈래입니다 «%s» (쓸 수 있는 것: %s)"
                                  % (no, sub, " · ".join(ISSUE_KINDS)))
                elif not any(i["kind"] == sub for i in issues):
                    errors.append("%d번: 이슈 «%s» 에 이유가 없습니다 — "
                                  "`<!-- flag: issue/%s — 왜 이슈인지 -->` 를 해설 MD 에 답니다."
                                  % (no, sub, sub))

        parts = parse_labeled(ab["lines"])
        choices = split_choices(qb["lines"])
        conditions = conditions_of(qb["lines"])
        givens = split_givens(qb["lines"])
        model = strip_markup(text_of(parts.get("모범답안", [])))
        by_no[no] = {
            "item": it,
            # 갈래는 **유형이 먼저 정한다.** 선지 유무«만»으로 가르면, 선지를 못 읽은
            # 객관식이 서술형으로 둔갑해 «모범답안이 없다» 는 엉뚱한 차단이 난다
            # (명지고2 34번).
            #
            # 그런데 유형만 보면 **영어 밖에서 깨진다.** 수학의 유형은 행동영역
            # (「문제해결」), 국어는 다섯 갈래(「문법」)라 서답형이어도 유형에
            # «서술형» 이라는 말이 없다. 그래서 수학·국어 목업 둘 다 서답형에
            # 「객관식」 배지가 붙었고, 양쪽이 똑같은 fix_report.py 로 손을 봤다.
            #
            # 그래서 둘을 **함께** 본다 — 유형이 말해 주거나, 아니면
            # «모범답안이 있고 선지가 없다». 34번은 모범답안이 없으므로 그대로 객관식이다.
            "kind": ("서술형" if is_essay(it.get("type")) or (model and not choices)
                     else "객관식"),
            "conditions": conditions,
            "givens": givens,
            "model_answer": model,
            "flags": flags,
            "issues": issues,
            "title_hint": plain((a_meta or {}).get("title")),
            "why": text_of(parts.get("정답 근거", [])),
            "wrong_reasons": bullets_of(parts.get("오답 근거", [])),
            "steps": bullets_of(parts.get("푸는 순서", [])),
            "concepts": (bullets_of(parts.get("필요 개념", []))
                         or [c.strip() for c in re.split(r"[·,]",
                             text_of(parts.get("필요 개념", []))) if c.strip()]),
            "excerpt": clip_lines(passage_of(qb["lines"]), max_lines, max_chars),
            "excerpt_full": passage_of(qb["lines"]),
            "choices": choices,
            "stem": plain(re.sub(r"\[\s*\d+\s*점\s*\]", "", qb["title"])),
        }

    # ---- 킬러문항 — 기계가 고르되, exam.json 이 직접 고를 수도 있다
    machine_full = pick_killers(items, KILLER_MAX)
    machine_nos = [int(k["no"]) for k in machine_full]
    manual, override_errs = read_override(exam, items)
    errors += override_errs
    if errors:
        fail(errors)                      # 킬러가 정해지기 전에는 다음을 잴 수 없다

    if manual:
        by_item = {int(it["no"]): it for it in items}
        full = [by_item[n] for n in manual]          # 고른 차례를 지킨다
    else:
        full = machine_full
    killers = full[:KILLER_SUMMARY] if summary else full
    killer_nos = set(int(k["no"]) for k in killers)
    chosen_nos = [int(k["no"]) for k in full]
    mode = "수동 선정" if manual else "기계 선정"

    # 손으로 적은 killer 표시는 **선정이 아니라 확인용**이다. 고른 것과 다르면 막는다.
    # 표시만으로 고를 수 있게 두면 «왜 이 문항이 킬러였지» 가 아무 데도 안 남는다.
    for no, rec in by_no.items():
        if "killer" in rec["flags"] and no not in chosen_nos:
            errors.append("%d번: killer 를 손으로 표시했지만 이번에 고른 킬러가 아닙니다 "
                          "(%s: %s). 사람이 고르려면 exam.json 에 "
                          "`\"killer_override\": [%s]` 를 적습니다 — 그래야 리포트에 "
                          "«수동 선정» 이 남습니다. meta 의 flags 는 확인용입니다."
                          % (no, mode, " · ".join("%d번" % n for n in chosen_nos),
                             ", ".join(str(n) for n in chosen_nos)))

    for k in killers:
        no = int(k["no"])
        rec = by_no[no]
        need = (("오답 근거", rec["wrong_reasons"]), ("정답 근거", rec["why"]),
                ("푸는 순서", rec["steps"]), ("필요 개념", rec["concepts"]))
        for label, v in need:
            if not v:
                errors.append("%d번은 킬러문항인데 해설 MD 에 «%s» 가 없습니다. "
                              "킬러는 리포트 본문에 그대로 실립니다." % (no, label))

        # 서술형 대표 문항은 «본문참조» 로 넘어갈 수 없다 (md-contract.md § 3-1).
        # 학부모가 받는 한 장에 빈 칸이 있으면 그 종이는 못 쓴다 — 주의가 아니라 차단이다.
        if rec["kind"] == "서술형":
            if not rec["model_answer"]:
                errors.append("%d번은 서술형 킬러인데 해설 MD 에 «모범답안» 이 없습니다. "
                              "exam.json 의 정답은 «%s» 라서 그대로 두면 학부모 종이에 "
                              "그 글자가 찍힙니다. `**모범답안** — …` 한 줄을 답니다."
                              % (no, k.get("answer")))
            elif is_empty_answer(rec["model_answer"]):
                errors.append("%d번의 «모범답안» 이 «%s» 입니다 — 그건 정답이 아니라 "
                              "정답을 적지 않았다는 말입니다. 실제 답안을 한 줄로 적습니다."
                              % (no, rec["model_answer"]))
        # 카드에 **아무것도** 실을 게 없을 때만 막는다. 선지가 빠진 객관식은 발췌·근거로
        # 카드가 서므로 주의로 알린다 — 막으면 원문이 잘못된 줄 알고 고치려 든다.
        if not (rec["choices"] or rec["conditions"] or rec["givens"] or rec["excerpt"]):
            errors.append("%d번은 대표 문항 상자에 실을 것이 없습니다 — 선지·«조건»·«보기»·"
                          "지문을 하나도 읽지 못했습니다. 빌더가 아는 표기는 선지 `①~⑤` · "
                          "보기 `ⓐ~ⓔ` · `> 조건 1. …` 입니다. 원문이 「단, …」 처럼 다른 "
                          "표기를 쓴다면 원문을 고치지 말고 **그 표기를 알려 주세요** — "
                          "읽는 규칙을 늘리는 것이 맞습니다 (md-contract.md § 4)." % no)
        elif rec["kind"] == "객관식" and not rec["choices"]:
            notes.append("%d번(킬러)의 선지를 읽지 못했습니다 — 카드에 선지 없이 나갑니다. "
                         "기출문제.md 에 `① … ② …` 가 들어왔는지 보세요%s."
                         % (no, " (보기 ⓐ~ⓔ 는 %d개 읽었습니다)" % len(rec["givens"])
                            if rec["givens"] else ""))

    if errors:
        fail(errors)

    # ---- 리포트 조립
    report = {}
    for key in PASSTHROUGH:
        if key in exam:
            report[key] = exam[key]
    report.setdefault("brand", {"academy": "공감에듀", "theme": "clean",
                                "logo_path": None, "logo_bg": "light"})

    meta = dict(exam.get("meta") or {})
    total_points = round(sum(num(it.get("points")) for it in items), 1)
    for key, got in (("total_items", len(items)), ("total_points", total_points)):
        if meta.get(key) is not None and abs(num(meta[key]) - num(got)) > 0.05:
            errors.append("meta.%s: exam.json «%s» ≠ items 를 센 값 «%s» — "
                          "판독에서 문항이 빠졌을 수 있습니다."
                          % (key, meta[key], fmt_num(got)))
        meta[key] = got if key == "total_items" else num(got)
    if errors:
        fail(errors)
    report["meta"] = meta

    report["items"] = []
    for it in items:
        row = {k: it[k] for k in ITEM_FIELDS + ITEM_OPTIONAL if k in it}
        row["answer"] = table_answer(it.get("answer"), it.get("type"))
        row["points"] = num(it.get("points"))               # 3.1 을 3 으로 깎지 않는다
        report["items"].append(row)
    all_types = aggregate(items, "type")
    # 요약본은 배점 상위 3개만 싣는다. 일곱 줄이 들어가면 유형 밴드가 커져 2쪽이 된다
    # (summary-spec.md § 2-1 · § 9). 자르는 것은 만드는 쪽이지 템플릿이 아니다.
    report["types"] = all_types[:TYPES_SUMMARY] if summary else all_types
    report["chapters"] = aggregate(items, "source")

    # 어느 막대를 칠할지는 사람이 지목한다 — exam.json 의 emphasis.
    # 없으면 아무 것도 칠하지 않는다(layout-grammar.md §6). 1위를 대신 칠하지 않는다.
    em = exam.get("emphasis") or {}
    if not isinstance(em, dict):
        errors.append("exam.json 의 emphasis 는 {\"types\": \"…\", \"chapters\": \"…\"} 꼴이어야 합니다.")
        em = {}
    # 자르기 «전» 목록에 지목한다 — 요약본은 상위 3개만 싣는데, 자른 뒤에
    # 재면 4위를 지목한 것이 「그런 줄이 없습니다」로 잘못 걸린다.
    # §6 막대 아래 «한 문장 해석». 숫자만 두면 읽는 사람이 결론을 못 낸다.
    # 지어내지 않는다 — 분석자가 exam.json 에 쓴 것을 그대로 옮긴다. 없으면 빈다.
    for key in ("types_note", "chapters_note"):
        report[key] = plain(exam.get(key) or "")

    # §9-2 / 채움 블록 — 난이도 5단을 «갈래마다 몇 문항 몇 점, 몇 번» 으로 편다.
    # 세는 일이라 사람이 쓸 것이 없다. 빌더가 센다.
    report.setdefault("difficulty", {})
    report["difficulty"]["detail"] = [
        {"label": label, "count": cnt, "points": pts,
         "nos": "·".join(str(int(i["no"])) for i in items
                         if i.get("difficulty") == label) + "번"}
        for label, cnt, pts in difficulty_counts(items) if cnt
    ]

    # §9-2 레이다 — 유형 막대와 같은 데이터를 다른 꼴로 본다.
    # 강조(em)를 먼저 찍고 나서 편다 — 축 이름에 그 표시가 따라가야 한다.
    mark_emphasis(all_types, em.get("types"), "유형별", errors)
    mark_emphasis(report["chapters"], em.get("chapters"), "출제별", errors)
    if summary and em.get("types") and not any(r.get("em") for r in report["types"]):
        print("  [알림] 유형 강조 «%s» 는 요약본 상위 %d줄 밖이라 요약본에는 안 칠해집니다."
              % (em["types"], TYPES_SUMMARY))
    # 레이다는 **자르기 전 전체**를 본다. 요약본의 막대는 상위 3개만 싣지만,
    # 레이다까지 셋이 되면 삼각형 하나라 «분포» 가 안 보인다 — 그게 레이다를
    # 쓰는 까닭 자체를 지운다. 막대는 많이 나온 것을, 레이다는 전체 꼴을 말한다.
    report["radar"] = build_radar(all_types)
    if report.get("overview", {}).get("cards"):
        split_cards(report["overview"]["cards"], errors)
    if errors:
        fail(errors)

    counts = difficulty_counts(items)
    diff = dict(report.get("difficulty") or exam.get("difficulty") or {})
    if not diff.get("summary"):
        hi = [c for c in counts if c[0] in ("상", "중상")]
        diff["summary"] = ("%s으로 상위 구간이 %s점입니다." % (
            ", ".join("%s %d문항 %s점" % (d, n, fmt_num(p)) for d, n, p in hi if n),
            fmt_num(round(sum(c[2] for c in hi), 1))))
    if not diff.get("discriminator"):
        # 요약본이 킬러를 하나만 실어도 «갈린 자리» 는 고른 전체를 말한다 —
        # 상세본과 요약본이 다른 말을 하면 안 된다
        diff["discriminator"] = ("%s번에서 갈렸습니다."
                                 % "·".join(str(n) for n in sorted(chosen_nos)))
    report["difficulty"] = diff

    def killer_row(it):
        no = int(it["no"])
        rec = by_no[no]
        # 객관식은 번호가 정답이고, 서술형은 «모범답안 한 줄» 이 정답이다.
        # 두 꼴을 템플릿이 갈라 그릴 수 있게 kind 를 함께 넘긴다.
        answer = (rec["model_answer"] if rec["kind"] == "서술형"
                  else norm_answer(it.get("answer")))
        steps, step_err = split_steps(rec["steps"])
        for e in step_err:
            errors.append("%d번 킬러: %s" % (no, e))
        return {
            "no": no,
            "kind": rec["kind"],
            # §4 카드 머리띠 오른쪽 = «어디서 온 것인가». 문항이 이미 알고 있다.
            "source": it.get("source") or "",
            "steps_flow": steps,
            "title": rec["title_hint"] or ("%s — %s" % (it.get("type"), it.get("source"))),
            "why": rec["why"],
            "steps": rec["steps"],
            "concepts": rec["concepts"],
            "excerpt": "\n".join(rec["excerpt"]),
            "choices": rec["choices"],
            "conditions": rec["conditions"],
            "givens": rec["givens"],      # <보기> ⓐ~ⓔ — 선지가 이것들의 조합을 고른다
            "answer": answer,
            "wrong_reasons": rec["wrong_reasons"],
            "selection": mode,            # 기계 선정 · 수동 선정 — 카드마다 남긴다
        }

    report["killer"] = [killer_row(it) for it in killers]
    # killer_row() 안에서 담은 오류를 **여기서** 낸다.
    # 마지막 `if errors: fail()` 은 이 줄보다 앞에 있어서, 여기서 안 내면
    # 그대로 버려진다 — ★ 를 둘 찍어도 조용히 통과하고 두 칸이 다 칠해졌다.
    # 재기는 하는데 결과를 아무도 안 보는, 이 스킬이 가장 싫어하는 꼴이었다.
    if errors:
        fail(errors)

    # 킬러를 누가 어떤 규칙으로 골랐는가. 반년 뒤에 «왜 이 문항이 킬러였지» 를 여기서 읽는다.
    report["killer_selection"] = {
        "mode": mode,
        "nos": chosen_nos,
        "rule": ("exam.json 의 killer_override" if manual
                 else "난이도 상 중 배점 높은 순, 동점이면 번호 빠른 쪽, 최대 %d개" % KILLER_MAX),
        "machine_nos": machine_nos,
    }
    if manual:
        # 종이에도 티가 나야 한다. 고지 줄은 배포본·요약본 모두 찍힌다.
        trace = ("킬러문항 %d개는 기계 규칙(난이도 상 중 배점순: %s번)이 아니라 "
                 "학원이 직접 고른 것입니다(수동 선정)."
                 % (len(chosen_nos), "·".join(str(n) for n in machine_nos)))
        base = str(report.get("disclaimer") or "").strip()
        if base and trace not in base:
            report["disclaimer"] = base + " " + trace

    issue_rows = []
    for no in sorted(by_no):
        rec = by_no[no]
        for i in rec["issues"]:
            # 요약본 이슈 발췌는 한 줄 60자다 — 상자가 커지면 총평 자리를 먹는다
            ex = (clip_lines(rec["excerpt_full"], *ISSUE_EXCERPT_SUMMARY)
                  if summary else rec["excerpt"])
            issue_rows.append({
                "no": no,
                "kind": i["kind"],
                "reason": i["reason"],
                "excerpt": "\n".join(ex),
            })
    if summary:
        issue_rows = issue_rows[:ISSUES_SUMMARY]
    report["issues"] = issue_rows

    # 학원이 할 일 한 줄. 학부모가 할 일이 아니다 (summary-spec.md § 2-3).
    # 근거가 없어도 빈 칸으로 두지 않는다 — {{next_action}} 이 남으면 렌더가 막힌다.
    if not str(report.get("next_action") or "").strip():
        kinds = []
        # 요약본은 킬러를 하나만 싣지만, 할 일은 **고른 킬러 전체**에서 뽑는다
        # — 상세본과 요약본이 다른 말을 하면 안 된다
        for k in full:
            t = str(k.get("type") or "").strip()
            if t and t not in kinds:
                kinds.append(t)
        report["next_action"] = (NEXT_ACTION_DEFAULT % "·".join(kinds[:2])
                                 if kinds else NEXT_ACTION_FALLBACK)

    sections = exam.get("sections_summary" if summary else "sections")
    if not sections:
        sections = SUMMARY_SECTIONS if summary else DETAIL_SECTIONS
    sections = [s for s in sections if s != "killer" or report["killer"]]

    # 이슈를 **찾아 놓고 실을 자리를 안 만드는** 일이 없게 한다.
    # 학교 시험에 문제가 있었다는 것을 짚어 주는 리포트는 다른 학원에 없다 — MD 에 적고
    # 이유까지 강제해 놓고 종이에 안 실으면 아무 소용이 없다. 자리는 데이터가 정한다.
    added_issues = False
    if report["issues"]:
        if "issues" not in sections:
            at = sections.index("killer") + 1 if "killer" in sections else len(sections)
            sections.insert(at, "issues")
            added_issues = True
    else:
        sections = [s for s in sections if s != "issues"]   # 빈 섹션은 만들지 않는다
    report["sections"] = sections

    # 요약본이 한 장을 다 못 채우면 남는 자리에 들어갈 것을 우선순위 순서로 넘긴다.
    # 상세본은 그대로다 — 거기엔 빈 자리가 없다.
    if summary:
        report["fill_blocks"] = build_fill_blocks(report, items, sections, notes)

    # 고른 섹션이 쓸 데이터가 없으면 여기서 막는다 — 렌더러보다 먼저, 말이 되게
    missing = []
    for s in sections:
        if s not in SECTION_NEEDS:
            missing.append("sections: 템플릿에 없는 섹션입니다 «%s» (있는 것: %s)"
                           % (s, " · ".join(sorted(SECTION_NEEDS))))
            continue
        for path in SECTION_NEEDS[s]:
            if not lookup(report, path):
                missing.append("섹션 «%s» 이 쓰는 %s 가 exam.json 에 없습니다." % (s, path))
    for path in ("cover.subtitle", "cover.tags"):
        if not lookup(report, path):
            missing.append("표지가 쓰는 %s 가 exam.json 에 없습니다." % path)
    if missing:
        fail(missing)

    # 산출물에서 잰다 — «고쳤나» 가 아니라 «나가는 글자에 남아 있나» 를 본다.
    # 새 경로가 생겨 어느 칸이 이 문을 빠져나가면 여기서 막힌다 (회귀 잠금).
    left = sweep_markup(report)
    if left:
        fail(left)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("[빌드] %s" % out_path)
    print("       %s · %d문항 %s점 · %s"
          % (meta.get("school", "?"), len(items), fmt_num(total_points),
             "요약본" if summary else "상세본"))
    print("       원문 %s" % os.path.basename(q_path))
    print("       해설 %s" % os.path.basename(a_path))
    print("       킬러 %d개 [%s]: %s"
          % (len(killers), mode,
             " · ".join("%d번(%s점)" % (k["no"], fmt_num(k["points"])) for k in killers)))
    if manual:
        print("       └ 기계 규칙이었다면: %s (난이도 상 %d문항 중 배점 순)"
              % (" · ".join("%d번" % n for n in machine_nos),
                 len([i for i in items if i.get("difficulty") == "상"])))
        print("         고지 줄에 «수동 선정» 을 남겼습니다")
    else:
        print("       └ 난이도 상 %d문항 중 배점 순"
              % len([i for i in items if i.get("difficulty") == "상"]))
    print("       이슈 %d건: %s%s"
          % (len(issue_rows), " · ".join("%d번 %s" % (r["no"], r["kind"])
                                         for r in issue_rows) or "없음",
             " → issues 섹션을 넣었습니다" if added_issues else ""))
    if summary:
        ex = report["killer"][0]["excerpt"] if report["killer"] else ""
        print("       유형 상위 %d개(전체 %d갈래) · 섹션 %d개"
              % (len(report["types"]), len(all_types), len(sections)))
        print("       발췌 %d줄 %d자 (한도 %d줄 %d자)%s"
              % (len(ex.splitlines()), len(ex), max_lines, max_chars,
                 " — 잘랐습니다" if ex.endswith(ELLIPSIS.strip()) else ""))
        if report["killer"]:
            k0 = report["killer"][0]
            print("       대표 문항 %d번 [%s] · %s %d개 · 정답 «%s»"
                  % (k0["no"], k0["kind"],
                     "선지" if k0["choices"] else "조건",
                     len(k0["choices"] or k0["conditions"]), k0["answer"]))
        print("       다음 행동: %s" % report["next_action"])
        fb = report.get("fill_blocks") or []
        print("       채움 블록 %d개: %s"
              % (len(fb), " → ".join("%s(%d줄)" % (b["title"], len(b["rows"])) for b in fb)
                 or "없음 — 넘길 데이터가 없습니다"))
        over = ["%s %d자(한도 %d)" % (p, len(str(lookup(report, p) or "")), n)
                for p, n in SUMMARY_LIMITS if len(str(lookup(report, p) or "")) > n]
        if over:
            # 사람이 쓴 문장은 자르지 않는다 — 자르면 말이 끊긴다. 대신 알린다.
            print("       [주의] 요약본 한도를 넘은 칸: %s" % " · ".join(over))
            print("              → 줄이지 않으면 2쪽이 될 수 있습니다 (summary-spec.md § 5)")
    else:
        print("       유형 %d갈래 · 출처 %d갈래 · 섹션 %d개"
              % (len(report["types"]), len(report["chapters"]), len(sections)))
    for n in notes:
        print("       [주의] %s" % n)
    return report


def main():
    argv = sys.argv[1:]
    summary = "--summary" in argv
    excerpt = None
    if "--excerpt-lines" in argv:
        i = argv.index("--excerpt-lines")
        try:
            excerpt = int(argv[i + 1])
        except (IndexError, ValueError):
            print("--excerpt-lines 뒤에 줄 수를 적어 주세요.", file=sys.stderr)
            sys.exit(1)
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__)
        sys.exit(1)
    try:
        build(args[0], args[1], args[2], summary=summary, excerpt_lines=excerpt)
    except BuildError as e:
        print("\n[빌드 실패] %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
