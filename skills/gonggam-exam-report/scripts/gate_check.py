#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
완료 게이트 — 통과 못 하면 전달하지 않는다.

    python gate_check.py <out/> [report.json] [--exam <exam.json>] [--md <md폴더>]
    python gate_check.py --data <report.json> [--exam <exam.json>]

`--data` 는 **종이를 안 보고 데이터만** 잰다 — 빌더가 채우는 칸(em·num·unit·key·
radar·steps_flow·fill_blocks)의 회귀 잠금이다. 크롬이 없는 자리에서도 돌고,
한 벌 57초를 굽기 전에 «렌더가 죽을 자리» 를 먼저 말한다.
**이것만으로 완료를 말하지 않는다** — 조판·쪽수·채움은 하나도 재지 못한다.

경고하지 않는다. 막는다. 옛 스킬은 수식이 0개로 렌더돼도 「성공」을 찍었다.
**0개를 재고 통과하는 것이 가장 나쁜 검사다.** 잴 대상이 없으면 통과가 아니라
차단이거나, 적어도 「무엇을 재지 못했는지」를 이름으로 말하는 주의다.

검사 목록의 정본은 `references/gates.md` 다.

종료코드 0 = 통과, 1 = 차단.
"""

import html as htmlmod
import io
import json
import os
import re
import sys

BANNED = ["100%", "무조건", "보장합니다", "보장", "1위", "적중률", "전원 1등급", "확실히 오릅니다"]
DIFFS = ("상", "중상", "중", "중하", "하")

# ── 조판 기준값 ────────────────────────────────────────────────────────────
FILL_MIN = 0.40          # 마지막 장을 뺀 모든 페이지의 세로 채움률 하한
ORPHAN_AT = 0.85         # 제목이 본문 상자의 이 아래에 있고
ORPHAN_MIN_LINES = 2     # 따라온 줄이 이보다 적으면 홀로 남은 제목
ROW_GAP_MIN = 12.0       # 표 행 구분선으로 볼 **최소** 줄간격(pt) — 한 줄보다 좁으면
                         # 행이 아니라 상자 테두리다 (6pt 짜리 두 줄을 표로 오해했었다)
ROW_GAP_SEED_MAX = 70.0  # 무리를 **여는** 첫 간격의 상한 — 한 줄(28)~두 줄(56) 행은 덮고
                         # 제목선과 첫 행 사이(92)는 덮지 않는 값
ROW_LINES_MAX = 3        # 한 행은 세 줄까지 — 그 표의 한 줄 높이의 몇 배까지 같은 표로 볼까
ROW_MIN_RULES = 3        # 표로 보려면 가로줄이 셋 이상. 둘뿐이면 «고른 간격» 이라 할 근거가
                         # 없다 — 상관없는 상자 테두리 둘을 표로 오해한다
TABLE_MIN_COLS = 3       # 그리고 그 줄들 사이의 글이 세 열 이상으로 서야 표다.
                         # 줄글에 그은 구분선은 한 열이다
CHUNK_GAP = 20.0         # 이만큼 빈 줄이 나오면 «덩어리» 가 끝난 것으로 본다
CHUNK_TOL = 24.0         # 덩어리 높이는 «그려진» 값이라 바깥 여백이 빠져 있다. 그만큼 봐 준다
DARK_LUM = 0.60          # 표 머리글 띠로 볼 최대 밝기
WHITE_TEXT = 0xF0F0F0    # 머리글 글자색(흰색) 판정 기준

# ── 요약본 기준값 — references/summary-spec.md 가 정본 ────────────────────
SUMMARY_MARK = 'class="page sheet"'   # 요약본 템플릿의 바깥 상자 (§ 7)
# 발췌 한도는 **대표 문항의 갈래마다 다르다** (§ 5). 서술형이면 〈조건〉 상자와
# 모범답안 줄이 더 붙어 같은 여섯 줄에 2쪽이 된다 — 실측으로 확인했다.
# 빌더(report_build.limits_for)와 **같은 값**이어야 한다. 한쪽만 고치면
# 빌더가 통과시킨 종이를 게이트가 막거나, 그 반대가 된다.
EXCERPT_LINES = 6                     # 객관식 대표 문항
EXCERPT_CHARS = 420                   # 「6줄」은 찍힌 줄이라 글자 수로도 잰다
EXCERPT_LINES_ESSAY = 4               # 서술형 대표 문항
EXCERPT_CHARS_ESSAY = 280
SUMMARY_CARDS = 4                     # 숫자 카드 정확히 4개 (§ 2-1)
SUMMARY_TYPES = 3                     # 유형은 상위 3개까지 (§ 2-1)

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
PAGE_STAMP = re.compile(r"(\d+)\s*/\s*(\d+)\s*페이지")
MD_HEAD = re.compile(r"^\s{0,3}#{2,4}\s*(\d+)\s*[번.)]")
MD_META = re.compile(r"<!--\s*meta:\s*(\{.*?\})\s*-->", re.S)
MD_POINTS = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*점\s*\]")
MD_DIFF = re.compile(r"난이도\s*[:：]?\s*(중상|중하|상|중|하)")
MD_FLAG = re.compile(r"<!--\s*flag:\s*issue/([^\s\-—–:]+)\s*(?:[—–\-:]\s*(.*?))?\s*-->", re.S)
ISSUE_MARKS = ("이유", "추론 정답", "판독불가", "⟨판독불가⟩", "미확인", "확인 필요", "확인필요")
# references/md-contract.md § 5 — 닫힌 목록. 늘리려면 계약을 먼저 고친다
ISSUE_KINDS = ("복수정답", "조건누락", "범위밖", "배점과다", "유형급변")
# 같은 § 3 — 킬러문항이 채워야 하는 네 칸
KILLER_BLOCKS = ("정답 근거", "오답 근거", "푸는 순서", "필요 개념")

# ── 빌더가 채우는 칸 — references/report-schema.md § 「빌더가 채우는 칸」 ──
# 참/거짓이 아니라 **문자열**이다. class 자리에 그대로 꽂히기 때문이다.
EM_OK = ("", "em")                    # types[] · chapters[] · radar.axes[] · steps_flow[]
KEY_OK = ("", "key")                  # overview.cards[]
RADAR_OK = ("", "1")                  # radar.ok — 판형의 data-ok 에 그대로 꽂는다
CARD_SLOTS = ("num", "unit", "key")   # 모든 카드에 온다
STEP_SLOTS = ("text", "conclusion", "em", "value")   # 모든 줄에 온다
HERE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE_DIR)
SUMMARY_TPL = os.path.join(SKILL_DIR, "assets", "template_summary.html")
# 판형이 내준 채움 자리. **지시자 꼴 그대로** 찾는다 — «fill-[a-z-]+» 로 헐겁게 찾으면
# 테마의 «fill-opacity» 가 자리 이름으로 잡힌다 (render_report.spec_heights 가 그 꼴이다).
FILL_SLOT = re.compile(r"<!--\s*SECTION:(fill-[a-z0-9\-]+)\s*-->")


class Gate(object):
    def __init__(self):
        self.fails = []
        self.warns = []
        self.oks = []

    def check(self, ok, name, detail=""):
        (self.oks if ok else self.fails).append((name, detail))
        return ok

    def warn(self, cond, name, detail=""):
        if cond:
            self.warns.append((name, detail))

    def report(self):
        for n, d in self.oks:
            print("  [통과] %s" % n)
        for n, d in self.warns:
            print("  [주의] %s — %s" % (n, d))
        for n, d in self.fails:
            print("  [차단] %s — %s" % (n, d))
        print()
        if self.fails:
            print("게이트 차단: %d건. 고치기 전에는 전달하지 않습니다." % len(self.fails))
            return 1
        print("게이트 통과 (주의 %d건)" % len(self.warns))
        return 0


def strip_comments(s):
    """«<!-- ... -->» 를 걷어낸다.

    주석은 **사람이 읽는 글이지 종이에 찍히는 글이 아니다.** 안 걷으면 템플릿에
    적어 둔 설명이 검사에 걸린다 — 주석의 «1 / 2 페이지» 예시가 진짜 쪽 표시로,
    주석에 적은 class 이름이 진짜 요소로 세어졌다. 템플릿 담당이 이것 때문에
    주석 문구를 바꿔 우회했고, 그대로 두면 다음 사람도 같은 데 걸린다.
    """
    return re.sub(r"<!--.*?-->", " ", s, flags=re.S)


def check_html(g, path, data=None):
    raw = io.open(path, encoding="utf-8").read()
    html = strip_comments(raw)          # 아래 검사는 전부 «종이에 찍히는 것» 을 잰다
    name = os.path.basename(path)

    left = sorted(set(re.findall(r"\{\{[^}]{0,80}\}\}", html)))
    g.check(not left, "%s · 빈 자리 없음" % name, "남은 자리: %s" % ", ".join(left[:8]))

    # 요약본은 A4 한 장에 **번호 없는 블록**으로 짠다 (summary-spec.md § 7).
    # 그래서 「번호 붙은 섹션 제목」을 요구하는 아래 두 검사를 받지 못한다.
    # **건너뛰지 않는다** — 대신 요약본이 반드시 담아야 하는 블록을 잰다 (§ 2-1).
    is_summary = "요약본" in name or SUMMARY_MARK in html
    if is_summary:
        check_summary_html(g, name, html)
    else:
        check_section_titles(g, name, html, data)

    check_page_marks(g, name, html)
    # 지면 문법 — 강조·범례·레이다·결론 칸 (references/layout-grammar.md)
    check_layout_grammar(g, name, html, data, is_summary)

    g.check("ReportKR" in html and "@font-face" in html, "%s · 동봉 폰트 삽입" % name,
            "폰트가 박히지 않았습니다")
    g.check("cdn." not in html and "https://fonts." not in html, "%s · 외부 의존 없음" % name,
            "CDN 링크가 남아 있습니다")

    # 눈에 보이는 본문만 검사한다 — CSS 의 width:100% 는 광고 문구가 아니다
    visible = re.sub(r"<style.*?</style>|<script.*?</script>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", visible)
    hit = [w for w in BANNED if w in body]
    g.check(not hit, "%s · 금지 문구 없음" % name, "발견: %s" % ", ".join(hit))
    return html


def html_pages(html):
    """HTML 이 스스로 말하는 장수. 없으면 None.

    **HTML 안에서 «장» 을 세지 않는다.** 2패스 쪽나눔으로 바뀐 뒤 HTML 에는 장이라는
    요소가 없다 — 섹션이 그냥 흐르고 장은 인쇄할 때 생긴다. `.page` 를 세던 옛 모형은
    표기 6 ≠ 실제 1 로 **구조적으로 통과할 수 없다.**
    장수는 렌더러가 실측해 `<meta name="gonggam:pages">` 로 내보낸 값이거나,
    쪽 표시 «N / M 페이지» 의 M 이다. 진짜 대조는 check_pdf 가 PDF 실측과 한다.
    """
    m = re.search(r'<meta\s+name="gonggam:pages"\s+content="(\d+)"', html)
    meta = int(m.group(1)) if m else None
    shown = re.sub(r"<style.*?</style>|<script.*?</script>", " ",
                   strip_comments(html), flags=re.S | re.I)
    marks = [(int(a), int(b)) for a, b in PAGE_STAMP.findall(shown)]
    return meta, marks


def check_page_marks(g, name, html):
    """쪽 표시가 저희끼리 어긋나지 않는가 (PDF 와의 대조는 check_pdf 가 한다)."""
    meta, marks = html_pages(html)
    totals = sorted({m[1] for m in marks})

    # 잴 것이 하나도 없으면 통과가 아니라 차단이다
    if not g.check(meta is not None or bool(marks), "%s · 장수 표기 존재" % name,
                   "<meta name=\"gonggam:pages\"> 도 «N / M 페이지» 표시도 없습니다 — "
                   "PDF 와 대조할 표기값이 없습니다"):
        return

    g.check(len(totals) <= 1, "%s · 총쪽수 표기 하나" % name,
            "쪽 표시가 서로 다른 총쪽수를 말합니다: %s" % totals)
    if meta is not None and totals:
        g.check(totals == [meta], "%s · 총페이지 일치" % name,
                "meta 실측 %d쪽 ≠ 쪽 표시의 총쪽수 %s" % (meta, totals))
    total = meta if meta is not None else (totals[0] if totals else 0)

    # 섹션 시작쪽 — 범위 밖이거나 거꾸로 가면 쪽나눔이 어긋난 것이다
    bad = ["%d / %d" % (a, b) for a, b in marks if not (1 <= a <= total)]
    g.check(not bad, "%s · 섹션 시작쪽 범위" % name,
            "총 %d쪽인데 이런 표시가 있습니다: %s" % (total, ", ".join(bad[:5])))
    starts = [a for a, _ in marks]
    g.check(starts == sorted(starts), "%s · 섹션 시작쪽 차례" % name,
            "섹션이 뒤로 갔다 앞으로 옵니다: %s" % starts)


def check_section_titles(g, name, html, data=None):
    """본편 리포트 — 번호 붙은 섹션 제목을 잰다."""
    # 번호와 제목을 같이 본다. «연속인가» 만 보면 같은 섹션이 두 번호를 써도 통과한다 —
    # 실제로 그랬다. 「2. 문항별 분석표」 다음 장이 「3. 문항별 분석표」였고 게이트는 OK 를 찍었다.
    heads = re.findall(r'class="section-title">(\d+)\.\s*([^<]*)', html)
    titles, order = {}, []
    for num, title in heads:
        t = re.sub(r"\s+", " ", title).strip()
        titles.setdefault(t, set()).add(int(num))
        if int(num) not in order:
            order.append(int(num))

    # 제목을 **하나도** 못 찾았는데 「연속」이 통과하던 자리다. 0개는 연속이니까.
    # 템플릿의 class 이름이 바뀌기만 해도 이 검사가 통째로 눈을 감았다.
    g.check(bool(order), "%s · 섹션 제목 존재" % name,
            "class=\"section-title\" 인 제목을 하나도 찾지 못했습니다 — 검사가 0개를 재고 있었습니다")
    g.check(order == list(range(1, len(order) + 1)),
            "%s · 섹션 번호 연속" % name, "매겨진 번호: %s" % order)
    split = {t: sorted(v) for t, v in titles.items() if len(v) > 1}
    g.check(not split, "%s · 한 섹션 = 한 번호" % name,
            "같은 제목이 여러 번호를 씁니다: %s" % split)

    # report.json 이 있으면 «실을 섹션 수» 와 «찍힌 제목 수» 를 맞춰 본다.
    if data is not None:
        want = data.get("sections") or []
        if want:
            g.check(len(order) == len(want), "%s · 섹션 수 = 제목 수" % name,
                    "sections %d개인데 제목은 %d개입니다 (빠진 섹션이 조용히 사라졌습니다)"
                    % (len(want), len(order)))


def check_summary_html(g, name, html):
    """요약본 — 번호 붙은 제목 대신 «한 장에 반드시 담을 것»을 잰다.

    summary-spec.md § 2-1 의 다섯 블록과 § 5 의 한도가 기준이다.
    본편의 「섹션 제목 존재」·「섹션 수 = 제목 수」를 이 검사들이 대신한다 —
    건너뛰는 것이 아니라 **바꿔서 잰다.**
    """
    def cnt(pat):
        return len(re.findall(pat, html))

    # 이름과 조판이 갈리면 말한다. 요약본 조판인데 이름이 «배포본» 이면
    # 게이트는 요약본으로 재고 학부모는 본편인 줄 알고 받는다.
    if SUMMARY_MARK in html:
        g.check("요약본" in name, "%s · 요약본 이름" % name,
                "요약본 조판(.page.sheet)인데 파일 이름에 «요약본» 이 없습니다 — "
                "이름과 실물이 갈립니다 (summary-spec § 9 꼬리칸)")
    else:
        g.check(False, "%s · 요약본 조판" % name,
                "이름은 요약본인데 요약본 템플릿(.page.sheet)으로 찍히지 않았습니다")
        return

    # § 7 — section-title 클래스를 단 요소 **한 개**. 렌더러가 쪽수를 읽는 자리다
    g.check(cnt(r'class="section-title"') == 1, "%s · 요약본 표제 하나" % name,
            "«기출 분석 요약» 표제(class=\"section-title\")가 %d개입니다 — 한 개여야 합니다"
            % cnt(r'class="section-title"'))

    # § 2-1 — 반드시 담는 블록
    need = [("머리글", r'class="hd"'), ("숫자 카드", r'class="card"'),
            ("난이도 5단", r'class="dbox'), ("유형 막대", r'class="bar-row"'),
            ("대표 문항", r'class="killer"'), ("총평", r'class="closing"'),
            ("꼬리말", r'class="ft"')]
    miss = [lab for lab, pat in need if cnt(pat) == 0]
    g.check(not miss, "%s · 요약본 필수 블록" % name,
            "빠진 블록: %s (summary-spec § 2-1)" % " · ".join(miss))

    g.check(cnt(r'class="card"') == SUMMARY_CARDS, "%s · 숫자 카드 4개" % name,
            "카드가 %d개입니다 — overview.cards 는 정확히 %d개여야 합니다"
            % (cnt(r'class="card"'), SUMMARY_CARDS))
    g.check(cnt(r'class="dbox') == len(DIFFS), "%s · 난이도 5칸" % name,
            "난이도 칸이 %d개입니다 — 상·중상·중·중하·하 다섯 칸이어야 합니다" % cnt(r'class="dbox'))
    ntype = cnt(r'class="bar-row"')
    g.check(1 <= ntype <= SUMMARY_TYPES, "%s · 유형 상위 3" % name,
            "유형 막대가 %d줄입니다 — 상위 %d개까지만 넘기세요 (넘치면 2쪽이 됩니다)"
            % (ntype, SUMMARY_TYPES))
    nk = cnt(r'class="killer"')
    g.check(nk == 1, "%s · 대표 문항 하나" % name,
            "대표 문항 상자가 %d개입니다 — killer 를 1개로 잘라서 넘기세요" % nk)
    g.check(cnt(r'class="issue"') <= 1, "%s · 이슈 문항 하나까지" % name,
            "이슈 상자가 %d개입니다 — issues 를 1개로 잘라서 넘기세요" % cnt(r'class="issue"'))
    g.check(cnt(r'<div class="page(?:[ "][^>]*)?>') == 1, "%s · 요약본 한 장" % name,
            "«.page» 가 %d개입니다 — 요약본은 한 장입니다"
            % cnt(r'<div class="page(?:[ "][^>]*)?>'))

    # 대표 문항 속살 — 발췌·정답에 더해 «고를 것» 이 있어야 «대표 문항»이다.
    # 고를 것은 두 꼴이다: 객관식이면 선지, **서술형이면 〈조건〉**.
    # 선지만 요구하면 서술형 대표 문항이 정상인데도 막힌다 —
    # 킬러는 기계가 배점 순으로 고르므로 8점짜리 서술형이 1순위가 되는 일이 흔하다.
    if nk:
        ch, cd = cnt(r'class="k-choice"'), cnt(r'class="cond"')
        g.check(cnt(r'class="k-excerpt"') == 1 and cnt(r'class="k-ans"') == 1
                and (ch >= 2 or cd >= 1), "%s · 대표 문항 속살" % name,
                "발췌 %d · 정답 %d · 선지 %d · 조건 %d — 발췌와 정답, 그리고 "
                "선지(객관식) 또는 조건(서술형)이 있어야 합니다"
                % (cnt(r'class="k-excerpt"'), cnt(r'class="k-ans"'), ch, cd))

    # § 5 — 발췌 한도. 이것이 한 장을 깨는 가장 흔한 자리다
    m = re.search(r'class="k-excerpt">(.*?)</div>', html, re.S)
    if m:
        txt = htmlmod.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        chars = len(re.sub(r"\s+", " ", txt).strip())
        # 갈래는 종이에 찍힌 배지로 읽는다 — report.json 없이도 재야 하기 때문이다.
        essay = bool(re.search(r'class="k-kind"[^>]*>\s*서술형', html))
        lim_l = EXCERPT_LINES_ESSAY if essay else EXCERPT_LINES
        lim_c = EXCERPT_CHARS_ESSAY if essay else EXCERPT_CHARS
        g.check(len(lines) <= lim_l and chars <= lim_c,
                "%s · 발췌 한도" % name,
                "발췌가 %d줄 %d자입니다 (%s 한도 %d줄 %d자) — 판가름 나는 대목만 남기고 «…» 로 "
                "줄이거나, 다른 문항을 고르세요"
                % (len(lines), chars, "서술형" if essay else "객관식", lim_l, lim_c))
    else:
        g.check(not nk, "%s · 발췌 존재" % name, "대표 문항에 발췌(k-excerpt)가 없습니다")


# ═══════════════════════════════════════════════════════════════════════
#  D. 지면 문법 — references/layout-grammar.md 를 기계가 지키게
#
#  규격을 글로만 적어 두면 다음 회차에 조용히 풀린다. 여기서 재는 것은 넣은 값이 아니라
#  **종이에 찍힌 것**이다 — 주석은 이미 걷어낸 뒤에 센다(strip_comments).
#  안 걷으면 판형 주석의 «강조 카드도 같다: class="info-card key"» 같은 설명이 진짜
#  요소로 세어진다 — 실제로 멀쩡한 영어 리포트가 «강조 카드 4개» 로 읽혔다.
# ═══════════════════════════════════════════════════════════════════════

# 범례 칸의 이름이 판형마다 다르다 — 상세본은 `cap`, 요약본의 발췌 범례는 `k-cap`.
# `cap` 만 찾다가 멀쩡히 붙어 있는 요약본 범례를 «없다» 고 막았다.
# 이름 하나를 고집하지 말고 «-cap 으로 끝나는 칸» 을 다 받는다.
CAP_RE = re.compile(r'<div class="(?:[a-z0-9-]*-)?cap"[^>]*>(.*?)</div>', re.S)
SEC_SPLIT = re.compile(r'<div class="sec[ "]')
CARD_ANY = re.compile(r'class="(?:info-)?card[ "]')
CARD_KEY = re.compile(r'class="(?:info-)?card[^"]*\bkey\b')
BAR_ANY = re.compile(r'class="bar-row[ "]')
BAR_EM = re.compile(r'class="bar-row[^"]*\bem\b|data-em="em"')
STEPS_FLOW = re.compile(r'<ol class="steps flow"[^>]*>(.*?)</ol>', re.S)
LI_EM = re.compile(r'<li[^>]*class="[^"]*\bem\b')
EXCERPT_AT = re.compile(r'class="k-excerpt"')
# «색을 쓴 자리» — 발췌 강조 span(.hl) 과 <mark>. "highlight" 는 안 걸린다(\b 경계)
HILITE_AT = re.compile(r'<mark\b|class="[^"]*\bhl\b', re.I)
# «→ 결론» 은 글자가 아니라 칸(.concl)이다. ★ 도 글자가 아니라 li.em 이다
STEP_RAW = re.compile(r'→|->|★')


def _plain(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _sec_label(sec, i):
    m = re.search(r'class="section-title">([^<]{0,40})', sec)
    return "«%s»" % _plain(m.group(1)) if m else "%d번째 구역" % i


def _sections(html):
    """섹션 하나씩. 흐름 조판이라 <div class="sec"> 가 섹션 경계다.

    요약본에는 .sec 이 없다 — 한 장이 통째로 한 구역이다."""
    parts = SEC_SPLIT.split(html)
    return parts[1:] if len(parts) > 1 else [html]


#                    <style>·<script> 통째로          | HTML 주석 통째로
STYLE_RE = re.compile(r"<(style|script)\b.*?</\1>|<!--.*?-->", re.S | re.I)


def _body_only(html):
    """**<style>·<script> 를 걷어낸 본문.** 조판 검사는 반드시 이것을 본다.

    안 걷으면 CSS 규칙 글자 자체가 본문으로 읽힌다 — `.bar-row.em .bar-fill{…}`
    이라는 «선언» 을 «강조된 막대 한 줄» 로 세는 식이다. 실제로 그래서 멀쩡한
    영어 요약본이 「강조 막대 2줄」로 막혔고, 범례 검사는 동봉 폰트의 base64
    한가운데(265114번째 글자)를 «발췌 상자» 로 짚었다.

    검사가 무엇을 세는지 모르면 통과도 차단도 믿을 수 없다.
    """
    return STYLE_RE.sub("", html)


def check_emphasis_once(g, name, html):
    """§0-2 · §11 — **강조는 한 곳만.** 넷 중 둘을 칠하면 둘 다 안 보인다.

    세 가지를 한 번에 잰다 — 숫자 카드의 key(문서 하나에 하나),
    막대의 em(**한 섹션에** 하나), 푸는 순서의 li.em(한 목록에 하나).
    세는 단위가 셋마다 다르다. 막대를 문서 단위로 세면 «유형별» 과 «출제 범위별» 이
    각각 하나씩 칠해진 멀쩡한 리포트가 «2개» 로 읽혀 막힌다.
    """
    html = _body_only(html)
    secs = _sections(html)
    lists = STEPS_FLOW.findall(html)
    ncard, nbar = len(CARD_ANY.findall(html)), len(BAR_ANY.findall(html))

    # 잴 것이 하나도 없으면 통과가 아니라 «못 쟀다» 고 말한다
    if not (ncard or nbar or lists):
        g.warn(True, "%s · 강조 잴 곳 없음" % name,
               "숫자 카드도 막대도 푸는 순서도 없어 강조 규칙을 하나도 재지 못했습니다")
        return

    nkey = len(CARD_KEY.findall(html))
    g.check(nkey <= 1, "%s · 강조 카드 하나" % name,
            "숫자 카드 %d개 중 강조(key)가 %d개입니다 — 둘을 칠하면 둘 다 안 보입니다 "
            "(layout-grammar.md §0-2 · §3)" % (ncard, nkey))

    bad = []
    for i, sec in enumerate(secs, 1):
        n = len(BAR_EM.findall(sec))
        if n > 1:
            bad.append("%s 에 강조된 막대가 %d줄" % (_sec_label(sec, i), n))
    g.check(not bad, "%s · 섹션마다 강조 막대 하나" % name,
            "%s — 칠할 행은 데이터가 하나만 지목합니다 (§6 · exam.json 의 emphasis)"
            % " / ".join(bad[:4]))

    badl = []
    for i, ol in enumerate(lists, 1):
        n = len(LI_EM.findall(ol))
        if n > 1:
            badl.append("%d번째 «푸는 순서» 에 ★ 가 %d칸" % (i, n))
    g.check(not badl, "%s · 목록마다 갈린 칸 하나" % name,
            "%s — 실제로 갈린 칸은 하나입니다 (§5)" % " / ".join(badl[:4]))


def _legend_of(html, pos, kind):
    """그 자리에 따라붙는 11px 범례(.cap)의 글. 없거나 비었으면 빈 문자열.

    바로 아래를 먼저 본다(상세본 §7 꼴). 없으면 바로 위를 본다 —
    요약본은 .cap 을 상자 **머리띠**로 쓴다(template_summary · .box>.cap).
    """
    end = html.find("</div>", pos)
    start = pos if end < 0 else end
    fwd = 500 if kind == "발췌" else 800
    m = CAP_RE.search(html[start:start + fwd])
    if m and _plain(m.group(1)):
        return _plain(m.group(1))
    for c in reversed(CAP_RE.findall(html[max(0, pos - 800):pos])):
        if _plain(c):
            return _plain(c)
    return ""


def check_legend(g, name, html):
    """§7 · §11 — **색을 쓰고 범례를 안 붙이지 않는다.**

    발췌 상자와 하이라이트는 색·선으로 뜻을 말한다. 그 뜻을 적은 11px 한 줄이
    없으면 빨간 표시가 무슨 뜻인지 아무도 모른다. 판형이 범례를 빼면 여기서 걸린다.
    """
    html = _body_only(html)
    spots = [("발췌", m.start()) for m in EXCERPT_AT.finditer(html)]
    spots += [("하이라이트", m.start()) for m in HILITE_AT.finditer(html)]
    if not spots:
        g.warn(True, "%s · 범례 잴 곳 없음" % name,
               "발췌 상자도 하이라이트도 없어 범례 규칙을 재지 못했습니다")
        return
    bad = []
    for kind, pos in spots:
        if not _legend_of(html, pos, kind):
            bad.append("%s(%d번째 글자 자리) 곁에 범례가 없거나 비었습니다" % (kind, pos))
    g.check(not bad, "%s · 색을 썼으면 범례" % name,
            "%s — 하이라이트·발췌에는 11px 범례(.cap)가 따라옵니다 "
            "(layout-grammar.md §7 · §11). 잰 자리 %d곳 중 %d곳이 비었습니다"
            % (" / ".join(bad[:4]), len(spots), len(bad)))


def check_radar_markup(g, name, html, is_summary):
    """§9-2 — **축이 셋 미만이면 레이다를 그리지 않는다.** 둘로는 삼각형도 안 된다.

    판형은 `data-ok` 가 비면 상자를 숨긴다. 숨기는 것과 안 그리는 것은 다르다 —
    테마가 display:none 을 한 줄 덮으면 빈 육각형이 그대로 인쇄된다. 그래서
    «숨겼나» 가 아니라 «점을 찍었나» 를 잰다.
    """
    m = re.search(r'<div class="box radar"[^>]*data-ok="([^"]*)"', html)
    if not m:
        if is_summary:
            g.warn(True, "%s · 레이다 잴 것 없음" % name,
                   "요약본에 레이다 상자가 없습니다 (sections 에 radar 가 없으면 정상입니다) — "
                   "데이터 쪽 축 수는 «데이터 · 레이다 축» 이 잽니다")
        return
    ok = m.group(1).strip()
    rest = html[m.end():]
    nxt = rest.find('<div class="box')
    block = rest if nxt < 0 else rest[:nxt]
    axes = len(re.findall(r'class="rd-lbl"', block))
    pts = re.search(r'class="rd-area"[^>]*points="([^"]*)"', block)
    drawn = bool(axes) or bool(pts and pts.group(1).strip())
    if not ok:
        g.check(not drawn, "%s · 레이다 축 3 미만이면 안 그린다" % name,
                "radar.ok 가 비었는데 SVG 가 그려졌습니다(축 %d개 · 꼭짓점 %s) — "
                "둘로는 삼각형도 안 됩니다 (§9-2)"
                % (axes, "있음" if (pts and pts.group(1).strip()) else "없음"))
    else:
        g.check(axes >= 3, "%s · 레이다 축 3 이상" % name,
                "radar.ok 가 켜졌는데 축이 %d개뿐입니다 — 셋부터 그립니다 (§9-2)" % axes)


def check_steps_flow(g, name, html, data, is_summary):
    """§5 — «→ 결론» 과 «★» 은 종이에 **글자로 찍히면 안 된다.**

    화살표는 결론 칸(.concl)이 CSS 로 붙이고, ★ 는 갈린 칸(li.em)으로 바뀐다.
    MD 에 적은 그대로 찍혔다면 바꾸는 자리(report_build.split_steps)를 안 거쳤거나
    판형이 steps_flow 를 안 쓰는 것이다. **실제로 그렇게 인쇄됐었다.**

    재는 곳을 «푸는 순서 목록 안» 으로 좁힌다. 종이 전체에서 → 를 찾으면
    어법 선지의 «which→when» 과 교정표의 «goes→go» 가 전부 걸려
    멀쩡한 영어 리포트를 막는다 — 거기서의 → 는 결론이 아니라 글자가 맞다.
    """
    lists = STEPS_FLOW.findall(html)
    if not lists:
        if not is_summary:
            g.warn(True, "%s · 푸는 순서 잴 곳 없음" % name,
                   "«푸는 순서» 목록(ol.steps.flow)이 하나도 없어 결론 칸 규칙을 재지 못했습니다")
        return

    raw = []
    for i, ol in enumerate(lists, 1):
        for li in re.findall(r"<li\b.*?</li>", ol, re.S):
            t = _plain(li)
            hit = sorted(set(STEP_RAW.findall(t)))
            if hit:
                raw.append("%d번째 목록 «%s» 에 %s" % (i, t[:22], "·".join(hit)))
    g.check(not raw, "%s · 결론은 글자가 아니라 칸" % name,
            "%s 가 글자로 찍혔습니다 — «→» 는 결론 칸(.concl)이 CSS 로 붙이고 "
            "«★» 은 li.em 으로 바뀝니다 (layout-grammar.md §5)" % " / ".join(raw[:4]))

    # 판형이 steps_flow 를 아예 안 쓰는 경우 — 데이터엔 있는데 종이엔 칸이 없다.
    # 요약본은 다른 판형이니 재지 않는다(report.json 을 같이 받아도).
    if data is None or is_summary:
        return
    want_c = want_e = 0
    for k in data.get("killer") or []:
        for s in k.get("steps_flow") or []:
            if str(s.get("conclusion") or "").strip():
                want_c += 1
            if str(s.get("em") or "").strip():
                want_e += 1
    got_c = len(re.findall(r'class="concl"', html))
    got_e = sum(len(LI_EM.findall(ol)) for ol in lists)
    g.check(not (want_c and not got_c), "%s · 결론 칸을 쓰는 판형" % name,
            "데이터에 «→ 결론» 이 %d개 있는데 종이에는 결론 칸(.concl)이 하나도 없습니다 — "
            "판형이 steps_flow 를 안 쓰고 있습니다 (§5)" % want_c)
    g.check(not (want_e and not got_e), "%s · 갈린 칸 표시" % name,
            "데이터가 갈린 칸을 %d개 지목했는데 종이에는 li.em 이 하나도 없습니다 — "
            "★ 가 조용히 사라졌습니다 (§5)" % want_e)


def check_layout_grammar(g, name, html, data, is_summary):
    """지면 문법 넷 — 강조·범례·레이다·결론 칸."""
    check_emphasis_once(g, name, html)
    check_legend(g, name, html)
    check_radar_markup(g, name, html, is_summary)
    check_steps_flow(g, name, html, data, is_summary)


def check_pdf(g, path):
    size = os.path.getsize(path)
    name = os.path.basename(path)
    head = io.open(path, "rb").read(5)
    g.check(head == b"%PDF-", "%s · PDF 형식" % name, "머리가 %r" % head)
    n = len(re.findall(rb"/Type\s*/Page[^s]", io.open(path, "rb").read()))
    g.check(n > 0, "%s · 페이지 존재" % name, "페이지 0")
    # 크기 하한은 «본문이 아예 안 찍혔나» 를 보는 눈금이다. 동봉 폰트만 19KB 라
    # 한 쪽짜리(요약본)는 정상이어도 20KB 를 못 넘는다 — 쪽수에 맞춰 눈금을 고른다.
    # 빈 본문은 이제 «본문 살아남음» 이 글자 단위로 잡는다.
    floor = 20000 if n > 1 else 8000
    g.check(size > floor, "%s · 크기 정상" % name,
            "%d bytes (%d쪽 기준 하한 %d) — 본문이 비었을 수 있습니다" % (size, n, floor))

    # HTML 이 «10쪽» 이라 찍어 놓고 PDF 는 12쪽이 나온 적이 있다 —
    # 긴 표가 한 장을 넘기면 쪽번호가 통째로 어긋난다. HTML 끼리만 맞춰 보면 못 잡는다.
    # 짝이 되는 HTML 이 없으면 **건너뛰지 않고 막는다.**
    # 예전에는 조용히 넘어갔다 — 이름이 다른 PDF 를 넣었더니 쪽수가 12↔13 으로
    # 어긋난 채 «게이트 통과» 가 찍혔다. 0개를 재고 통과하는 것이 가장 나쁜 검사다.
    html = path[:-4] + ".html"
    if not os.path.exists(html):
        g.check(False, "%s · 짝 HTML 존재" % name,
                "같은 이름의 .html 이 없어 쪽수를 대조할 수 없습니다: %s" % os.path.basename(html))
        return
    src = io.open(html, encoding="utf-8").read()
    meta, marks = html_pages(src)
    said = []
    if meta is not None:
        said.append(("meta 실측", meta))
    for tot in sorted({m[1] for m in marks}):
        said.append(("쪽 표시", tot))
    # 표기가 하나도 없으면 «대조 안 함» 이 아니라 **차단**이다.
    # 못 재게 된 것을 통과로 바꾸지 않는다.
    g.check(bool(said), "%s · 쪽수 표기 존재" % name,
            "HTML 에 <meta name=\"gonggam:pages\"> 도 «N / M 페이지» 도 없어 "
            "PDF 실제 %d쪽과 대조할 수 없습니다" % n)
    off = ["%s %d쪽" % (lab, v) for lab, v in said if v != n]
    # «0쪽» 은 렌더가 아직 쪽수를 재지 않은 **중간 상태**다. 2패스 렌더가 자리표를 먼저
    # 써 두고 나중에 실측값으로 덮는데, 그 사이에 게이트를 돌리면 여기 걸린다.
    # 막는 것은 맞다 — 0쪽이라 적힌 HTML 은 내보낼 것이 못 된다. 다만 왜인지는 말해 준다.
    why = ("«0쪽» 은 렌더가 쪽수를 재기 전의 자리표입니다 — 렌더가 끝난 뒤 다시 재세요"
           if any(v == 0 for _, v in said) else "내용이 한 장을 넘쳤습니다")
    g.check(not off, "%s · 표기 쪽수 = 실제 쪽수" % name,
            "%s ≠ PDF 실제 %d쪽 — %s" % (" / ".join(off), n, why))


# ══════════════════════════════════════════════════════════════════════════
#  A. 조판 검사 — PDF 를 실제로 열어서 잰다
# ══════════════════════════════════════════════════════════════════════════

def _open_pdf(g, path):
    """PyMuPDF 로 연다. 없으면 **막는다** — 못 재는 것을 통과로 바꾸지 않는다."""
    try:
        import fitz
    except ImportError:
        g.check(False, "조판 검사 · PyMuPDF 필요",
                "PDF 를 열지 못해 조판을 하나도 재지 못했습니다. pip install pymupdf")
        return None
    try:
        return fitz.open(path)
    except Exception as e:
        g.check(False, "%s · PDF 열림" % os.path.basename(path), "%s: %s" % (type(e).__name__, e))
        return None


def _page_geom(page):
    """글자·도형·본문 상자를 뽑는다.

    한 페이지에는 «페이지 전체를 덮는 바탕」이 깔려 있다. 그걸 잉크로 세면
    어느 페이지나 93% 가 나와서 채움률 검사가 통째로 무의미해진다 — 그래서 뺀다.
    """
    H, W = page.rect.height, page.rect.width
    spans = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            for s in ln["spans"]:
                t = s["text"].strip()
                if t:
                    spans.append({"bbox": s["bbox"], "text": t,
                                  "size": s.get("size", 0), "color": s.get("color", 0)})
    draws, frame = [], None
    for d in page.get_drawings():
        r = d["rect"]
        if r.height > 0.85 * H and r.width > 0.85 * W:
            if frame is None or r.height > frame.height:
                frame = r
            continue
        draws.append(d)
    box = frame if frame is not None else page.rect
    return spans, draws, box


def _is_stamp(sp):
    return bool(PAGE_STAMP.search(sp["text"]))


def _ink_extent(spans, draws):
    ys = []
    for s in spans:
        ys.append(s["bbox"][1])
        ys.append(s["bbox"][3])
    for d in draws:
        ys.append(d["rect"].y0)
        ys.append(d["rect"].y1)
    if not ys:
        return None
    return min(ys), max(ys)


def _titles(spans):
    """섹션 제목 — 「N. 무엇」 꼴의 큰 글자."""
    out = []
    for s in spans:
        if s["size"] >= 12.5 and re.match(r"^\d+\.\s*\S", s["text"]):
            out.append(s)
    return out


def _row_runs(draws, box):
    """고른 간격으로 이어지는 가로줄 = 표의 행 구분선."""
    bands = {}
    for d in draws:
        r = d["rect"]
        if r.height <= 2.5 and r.width >= 15:
            y = round(r.y0)
            bands[y] = bands.get(y, 0.0) + r.width
    wide = sorted(y for y, w in bands.items() if w >= 0.4 * box.width)

    # 줄간격 상한을 **고정값으로 두지 않는다.** 그 표의 실제 한 줄 높이에서 잰다.
    # 45pt 로 못 박았더니 두 줄짜리 행(56pt)에서 한 표가 두 무리로 쪼개졌고,
    # 두 번째 무리에 머리글을 요구해 **머리글이 있는데도 막았다.**
    # 한 행은 한 줄이거나 두세 줄이다 — 그 표의 가장 좁은 간격(= 한 줄 행)의
    # 정수배면 같은 표로 본다.
    runs, cur, base = [], [], None
    for y in wide:
        if not cur:
            cur = [y]
            continue
        gap = y - cur[-1]
        if gap < ROW_GAP_MIN:                      # 같은 자리에 겹쳐 그은 선
            continue
        if base is None:
            ok = gap <= ROW_GAP_SEED_MAX           # 첫 간격 — 한 줄~두 줄 행까지
        else:
            k = int(round(gap / base))
            ok = 1 <= k <= ROW_LINES_MAX and abs(gap - k * base) <= 0.35 * base
        if ok:
            cur.append(y)
            base = min(base or gap, gap)
        else:
            if len(cur) >= ROW_MIN_RULES:
                runs.append(cur)
            cur, base = [y], None
    if len(cur) >= ROW_MIN_RULES:
        runs.append(cur)
    return runs


def _first_chunk(spans, draws, box):
    """그 장 **맨 위에 앉은 불가분 덩어리**의 높이.

    카드(테두리·바탕이 있는 상자)가 맨 위에 있으면 그 높이,
    없으면 첫 큰 빈 줄까지의 높이. 앞 장의 남은 자리와 견주어
    «여백이 게으름인가, 밀려서 생긴 것인가» 를 가른다.
    """
    top = min([s["bbox"][1] for s in spans] or [box.y0])
    cards = [d["rect"] for d in draws
             if d["rect"].y0 <= top + 25 and d["rect"].height >= 40
             and d["rect"].width >= 0.4 * box.width]
    if cards:
        return max(r.height for r in cards)
    iv = sorted([(s["bbox"][1], s["bbox"][3]) for s in spans])
    if not iv:
        return 0.0
    end = iv[0][1]
    for a, b in iv[1:]:
        if a - end >= CHUNK_GAP:
            break
        end = max(end, b)
    return end - iv[0][0]


def _columns(spans, y0, y1):
    """그 구간의 글이 몇 갈래(열)로 서 있나 — 표인지 줄글인지 가르는 자리."""
    xs = sorted(s["bbox"][0] for s in spans if y0 - 4 < s["bbox"][1] < y1 + 4)
    cols, last = 0, None
    for x in xs:
        if last is None or x - last > 12:
            cols += 1
        last = x
    return cols


def _header_bands(spans, draws, box):
    """표 머리글 = 진한 색 띠 + 그 안의 흰 글씨. 막대그래프·배지와 이것으로 갈린다."""
    bands = {}
    for d in draws:
        r = d["rect"]
        f = d.get("fill")
        if not f or len(f) < 3:
            continue
        lum = 0.299 * f[0] + 0.587 * f[1] + 0.114 * f[2]
        if lum >= DARK_LUM or not (6 <= r.height <= 60) or r.width < 15:
            continue
        y = round(r.y0)
        e = bands.setdefault(y, {"w": 0.0, "y0": r.y0, "y1": r.y1})
        e["w"] += r.width
        e["y1"] = max(e["y1"], r.y1)
    out = []
    for y, e in sorted(bands.items()):
        if e["w"] < 0.4 * box.width:
            continue
        white = [s for s in spans
                 if s["color"] >= WHITE_TEXT and e["y0"] - 2 <= s["bbox"][1] <= e["y1"] + 2]
        if white:
            out.append(e)
    return out


def check_pdf_layout(g, path):
    """조판 — 제목만 있는 장 · 머리글 없는 표 · 채움률 · 내용 잘림."""
    name = os.path.basename(path)
    doc = _open_pdf(g, path)
    if doc is None:
        return
    n = doc.page_count
    # 이름으로도, 조판으로도 알아본다. 이름만 보면 꼬리칸이 «배포본» 으로 잘못 붙은
    # 요약본이 1쪽 검사를 통째로 피해 간다 (summary-spec § 9).
    is_summary = "요약본" in name
    pair = path[:-4] + ".html"
    if not is_summary and os.path.exists(pair):
        is_summary = SUMMARY_MARK in strip_comments(io.open(pair, encoding="utf-8").read())

    thin, orphan, headless, clipped, stampbad = [], [], [], [], []
    fills, exempt, nostamp, totals = [], [], [], set()
    texts, remains, chunks = [], [], []

    for pno in range(1, n + 1):
        page = doc[pno - 1]
        spans, draws, box = _page_geom(page)
        body = [s for s in spans if not _is_stamp(s)]
        boxh = max(box.height, 1.0)

        # ── 쪽번호 도장. 없는 장 = 앞 장이 넘쳐 흘러나온 장 = 내용이 잘린 자리
        texts.append(page.get_text())
        stamps = PAGE_STAMP.findall(texts[-1])
        cover = (pno == 1 and not stamps)
        if cover:
            exempt.append(pno)
        elif not stamps:
            nostamp.append(pno)
        else:
            cur, tot = int(stamps[0][0]), int(stamps[0][1])
            if cur != pno:
                stampbad.append("p%d 에 «%d / %d» 가 찍혀 있음" % (pno, cur, tot))
            totals.add(tot)

        # ── 본문이 인쇄 상자 밖으로 나갔나.
        # 크롬은 인쇄 영역 밖을 **그리지 않고 지운다.** 그래서 이 검사만으로는
        # 잘린 내용을 영영 못 잡는다 — 0개를 재고 통과하는 검사가 된다.
        # 진짜 검사는 아래 check_text_survived(): HTML 에 있던 글이 PDF 에 남았나.
        for s in body:
            if s["bbox"][3] > box.y1 + 1 or s["bbox"][1] < box.y0 - 1:
                clipped.append("p%d «%s» y=%.0f (상자 %.0f~%.0f)"
                               % (pno, s["text"][:16], s["bbox"][3], box.y0, box.y1))
                break

        # ── 칸이 짓눌렸나 (2026-09-23 신설)
        #
        # 처음엔 «가로로 넘쳤나» 를 쟀다. 그 검사는 죽어 있었다 — 일부러 긴
        # meta.term 을 넣어 봤더니 x 는 570pt 그대로였다. flex 가 넘치는 대신
        # **옆 칸을 짓눌러서** 버티기 때문이다. 머리띠 왼쪽이 한 글자 폭이 되어
        # 「공 / 감 / 에 / 듀」 로 세로로 쪼개졌고 제목이 통째로 밀려났는데,
        # 글자는 전부 PDF 에 남아 있어 «글이 살아남았나» 검사도 통과했다.
        #
        # 그래서 넘침이 아니라 **짓눌림**을 잰다. 한 글자짜리 줄이 세로로
        # 줄줄이 쌓이는 것이 그 서명이다. 한글 세로쓰기를 하지 않는 한 이건
        # 언제나 사고다.
        # 짓눌린 글자는 **한 글자마다 블록이 따로** 나온다. 그래서 블록 안이
        # 아니라 쪽 전체에서 모은 뒤 «같은 x 에 세로로 바짝 쌓였나» 로 가른다.
        # 그냥 「한 글자짜리 줄」을 세면 난이도 배지(「상」·「중」·「하」)가 걸린다 —
        # 배지도 한 글자에 같은 x 지만, 표 한 행씩 떨어져 있어 줄 간격이 멀다.
        ones = []
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = "".join(s["text"] for s in ln["spans"]).strip()
                x0, y0, x1, y1 = ln["bbox"]
                # 한글 음절만 센다. 숫자·동그라미 번호를 같이 세면 선지 「①②③④」와
                # 푸는 순서 「1 2 3 4」가 그대로 걸린다 — 실제로 멀쩡한 영어 리포트
                # 5·6·7쪽이 그 때문에 막혔다. 짓눌림의 서명은 «낱말이 음절마다
                # 쪼개지는 것» 이지 «번호가 세로로 놓이는 것» 이 아니다.
                if len(t) == 1 and (x1 - x0) < 20 and "가" <= t <= "힣":
                    ones.append((round(x0), y0, max(y1 - y0, 1.0)))
        ones.sort()
        squeezed, run = 0, 1 if ones else 0
        for i in range(1, len(ones)):
            px, py, ph = ones[i - 1]
            x, y, h = ones[i]
            run = run + 1 if (abs(x - px) <= 3 and (y - py) < max(ph, h) * 1.9) else 1
            squeezed = max(squeezed, run)
        if squeezed >= 4:
            clipped.append("p%d — 칸이 짓눌렸습니다: 한 글자짜리 줄이 %d개 연달아 "
                           "쌓였습니다(옆 칸이 너무 길어 이 칸을 밀어냈습니다)"
                           % (pno, squeezed))

        # ── 제목만 있고 내용이 없는 장 / 맨 아래 홀로 남은 제목
        # 흐름 조판에서는 한 장에 섹션이 여럿 올 수 있다. 그래서 「제목 아래」를
        # **다음 제목까지**로 끊는다. 안 끊으면 뒤 섹션의 본문이 앞 제목의 본문으로
        # 보여, 제목만 남은 섹션을 **통과시킨다** — 실제로 그랬다.
        tt = _titles(spans)
        for k, t in enumerate(tt):
            ty1 = t["bbox"][3]
            stop = tt[k + 1]["bbox"][1] if k + 1 < len(tt) else box.y1 + 1
            below = [s for s in body if ty1 + 2 < s["bbox"][1] < stop]
            deep = max([s["bbox"][3] for s in below] or [ty1])
            if not below or (deep - ty1) < 24:
                thin.append("p%d «%s» 아래에 본문이 없습니다" % (pno, t["text"][:20]))
            # 제목의 **자리**가 아니라 제목 아래에 **몇 줄이 따라왔나**를 본다.
            # 자리만 보면 「제목 + 설명 + 한 줄」이 장 끝에 놓인 멀쩡한 조판도
            # 「홀로 남았다」고 막는다 — 홀로 남지 않았는데.
            lines = len({round(s["bbox"][1]) for s in below})
            if lines < ORPHAN_MIN_LINES and ty1 > box.y0 + ORPHAN_AT * boxh:
                orphan.append("p%d «%s» 아래에 %d줄밖에 없이 장이 끝납니다"
                              % (pno, t["text"][:20], lines))

        # ── 표가 이어지는 장에 머리글이 있나
        #
        # **장 단위로 본다.** 막는 것은 「표 행만 있고 머리글이 없는 장」이지
        # 「행 무리마다 머리글이 붙었는가」가 아니다. 무리마다 요구하면 한 표가
        # 어떤 이유로든 두 무리로 갈릴 때 **머리글이 있는데도 막는다.**
        # 「가로줄이 여러 줄이면 표」는 너무 넓은 판정이다 — 총평 상자의 구분선 셋을
        # 표로 오인해 머리글을 요구했다. 표라면 그 줄들 사이의 글이 **여러 열**로 선다.
        runs = [r for r in _row_runs(draws, box)
                if _columns(body, r[0], r[-1]) >= TABLE_MIN_COLS]
        if runs:
            first = min(r[0] for r in runs)
            rows = sum(len(r) + 1 for r in runs)
            above = [h for h in _header_bands(spans, draws, box) if h["y1"] <= first + 1]
            if not above:
                headless.append("p%d 표 행 %d줄이 있는데 그 위에 머리글 띠가 없습니다 "
                                "(첫 행선 y=%.0f)" % (pno, rows, first))

        # ── 채움률. 남은 자리도 같이 적어 둔다 — 다음 장 첫 덩어리와 견주려고
        ex = _ink_extent(body, draws)
        ratio = 0.0 if ex is None else (ex[1] - ex[0]) / boxh
        fills.append((pno, ratio, cover))
        remains.append(box.y1 - (ex[1] if ex else box.y0))
        chunks.append(_first_chunk(body, draws, box))

    # 쪽번호 없는 장이 가장 중한 증거다 — 앞 장이 넘쳐 흘러나온 자리다. 먼저 말한다.
    msg = []
    if nostamp:
        msg.append("쪽번호 없는 장 p%s — 앞 장이 넘쳐 흘렀습니다(내용이 경계에서 갈렸습니다)"
                   % ", p".join(str(p) for p in nostamp))
    if totals - {n}:
        msg.append("표기 총쪽수 %s ≠ 실제 %d쪽" % (sorted(totals - {n}), n))
    msg += stampbad[:3]
    g.check(not msg, "%s · 쪽번호 장마다 일치" % name, " / ".join(msg))
    g.check(not clipped, "%s · 내용 잘림 없음" % name, " / ".join(clipped[:3]))
    g.check(not thin, "%s · 제목만 있는 장 없음" % name, " / ".join(thin[:4]))
    g.check(not orphan, "%s · 홀로 남은 제목 없음" % name, " / ".join(orphan[:4]))
    g.check(not headless, "%s · 표 머리글 있음" % name, " / ".join(headless[:4]))

    # 마지막 장은 뺀다 — 끝 장은 남는 것이 정상이다
    measured = [(p, r) for p, r, cov in fills if p != n and not cov]
    skipped = [p for p, r, cov in fills if cov and p != n]
    if not measured:
        g.warn(True, "%s · 채움률 잴 장 없음" % name,
               "마지막 장과 표지를 빼면 남는 장이 없습니다 (총 %d쪽) — 재지 못했습니다" % n)
    else:
        # 여백이 **게으름**인가, 다음 덩어리가 안 들어가 **밀려서** 생긴 것인가.
        # 카드는 break-inside:avoid 라 반으로 안 잘린다. 안 들어가면 통째로 다음 장으로
        # 밀리고 앞 장 아래에 여백이 남는다 — 그건 규칙이 **제대로 작동한 결과**다.
        # 그 여백까지 같은 자로 벌하면 사람은 «카드를 자르는 쪽» 으로 도망간다.
        low, pushed = [], []
        for p, r in measured:
            if r >= FILL_MIN:
                continue
            remain = remains[p - 1]
            nxt = chunks[p] if p < len(chunks) else 0.0
            # 재는 값은 «그려진» 높이라 바깥 여백이 빠져 있다. 아슬아슬한 자리에서
            # 실제로는 안 들어간 것을 «들어갔을 텐데» 로 잘못 읽는다 — 한 줄 남짓 봐 준다.
            if nxt > remain - CHUNK_TOL:
                pushed.append("p%d %.0f%% (남은 자리 %.0fpt < 다음 덩어리 %.0fpt)"
                              % (p, 100 * r, remain, nxt))
            else:
                low.append("p%d %.0f%% (남은 자리 %.0fpt · 다음 덩어리 %.0fpt)"
                           % (p, 100 * r, remain, nxt))
        avg = 100.0 * sum(r for _, r in measured) / len(measured)
        g.check(not low, "%s · 채움률 %d%% 이상" % (name, int(FILL_MIN * 100)),
                "평균 %.0f%% · 모자란 장: %s — 뒤에 밀린 덩어리도 없이 비었습니다. "
                "줄 수를 늘리거나 섹션을 합치세요" % (avg, ", ".join(low)))
        if pushed:
            g.warn(True, "%s · 밀려서 생긴 여백" % name,
                   "%s — 다음 덩어리가 통째로 밀린 자리라 채움률에서 뺐습니다 "
                   "(카드를 쪼개지 마세요)" % ", ".join(pushed))
    if skipped:
        g.warn(True, "%s · 표지 채움률 면제" % name,
               "표지(p%s)는 쪽번호가 없는 장이라 채움률에서 뺐습니다"
               % ", p".join(str(p) for p in skipped))

    # ── C. 요약본은 1장이다
    if is_summary:
        g.check(n == 1, "%s · 요약본 1쪽" % name,
                "요약본이 %d쪽입니다. 1쪽이어야 합니다 — 원문 줄 수를 줄이세요" % n)
    elif os.path.exists(pair):
        check_section_pages(g, name, strip_comments(io.open(pair, encoding="utf-8").read()), texts)

    check_text_survived(g, path, doc)
    doc.close()


SEC_MARK = re.compile(
    r'class="section-title">\s*(\d+)\.\s*([^<]{0,30}).{0,400}?class="page-mark">\s*(\d+)\s*/',
    re.S)


def check_section_pages(g, name, src, texts):
    """HTML 이 「1. 시험 개요는 2쪽」이라 적었으면 PDF 2쪽에 그 제목이 있어야 한다.

    옛 모형은 HTML 의 `.page` 를 세어 장 구조를 봤다. 흐름 조판으로 바뀌어 그 «장» 이
    사라졌으니, 장이 제대로 갈렸는지는 **쪽 표시와 PDF 를 맞춰서** 본다.
    표시가 제목과 짝지어지지 않으면 **건너뛰지 않고 막는다** — 못 재게 된 것이다.
    """
    titles = len(re.findall(r'class="section-title"', src))
    if not titles:
        return                       # 섹션 제목 자체가 없는 산출물 — 다른 검사가 본다
    pairs = SEC_MARK.findall(src)
    if not g.check(len(pairs) == titles, "%s · 섹션 시작쪽 표시" % name,
                   "섹션 제목 %d개 중 %d개만 쪽 표시와 짝지어집니다 — 어느 섹션이 몇 쪽에서 "
                   "시작하는지 잴 수 없습니다" % (titles, len(pairs))):
        return
    bad = []
    for num, title, page in pairs:
        p = int(page)
        if not (1 <= p <= len(texts)):
            bad.append("%s번 섹션이 %s쪽이라는데 PDF 는 %d쪽뿐" % (num, page, len(texts)))
            continue
        key = re.sub(r"\s+", "", htmlmod.unescape(title))[:8]
        flat = re.sub(r"\s+", "", texts[p - 1])
        if ("%s." % num + key) not in flat and key not in flat:
            bad.append("«%s. %s» 는 %s쪽이라는데 그 쪽에 없습니다" % (num, title.strip(), page))
    g.check(not bad, "%s · 섹션 시작쪽 일치" % name, " / ".join(bad[:4]))


def _chunks(html):
    """HTML 에 눈에 보이게 적힌 글 토막들."""
    body = re.split(r"<body[^>]*>", html, maxsplit=1)   # <head> 의 <title> 은 종이에 안 찍힌다
    t = body[1] if len(body) > 1 else html
    t = re.sub(r"<style.*?</style>|<script.*?</script>|<!--.*?-->", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\x00", t)
    out = []
    for piece in t.split("\x00"):
        s = re.sub(r"\s+", "", htmlmod.unescape(piece))
        if len(s) >= 12:
            out.append(s)
    return out


def check_text_survived(g, pdf_path, doc):
    """HTML 에 적힌 글이 PDF 에 남았나 — 「페이지 경계에서 반쪽 난」 것을 잡는 진짜 검사.

    크롬은 인쇄 영역을 넘긴 내용을 **말없이 지운다.** 좌표만 봐서는 아무 일도
    없었던 것처럼 보인다. 그래서 글자 자체가 살아남았는지를 센다.
    """
    name = os.path.basename(pdf_path)
    html_path = pdf_path[:-4] + ".html"
    if not os.path.exists(html_path):
        return                      # 짝 HTML 없음은 check_pdf 가 이미 막았다
    want = _chunks(io.open(html_path, encoding="utf-8").read())
    got = re.sub(r"\s+", "", "".join(doc[i].get_text() for i in range(doc.page_count)))
    g.check(bool(want), "%s · 대조할 본문 존재" % name, "HTML 에서 글 토막을 하나도 못 뽑았습니다")
    lost = [c for c in want if c not in got]
    g.check(not lost, "%s · 본문 살아남음" % name,
            "HTML 에는 있는데 PDF 에 없는 글 %d토막 (경계에서 잘렸습니다): %s"
            % (len(lost), " / ".join("«%s…»" % c[:24] for c in lost[:3])))


# ══════════════════════════════════════════════════════════════════════════
#  B. MD ↔ 리포트 대조
# ══════════════════════════════════════════════════════════════════════════

def _one_answer(s):
    """정답 하나를 견줄 수 있는 꼴로. «②» 와 «2» 는 같은 정답이다."""
    s = s.strip()
    if len(s) == 1 and s in CIRCLED:
        return str(CIRCLED.index(s) + 1)
    if s.isdigit():
        return str(int(s))
    return re.sub(r"\s+", " ", s)        # 겹친 공백만 고른다 — **글자는 지우지 않는다**


def norm_answer(v):
    """정답을 견줄 수 있는 꼴로 만든다.

    두 가지를 받는다.

    * **서술형은 한 낱말이 아니다.** 문장이 통째로 온다 —
      「정답 ask if your wish was to add an interactive element」.
      옛 방식은 공백에서 끊어 «ask» 만 읽고 exam.json 과 다르다며 막았다.
      겹친 공백은 같은 값으로 보되 **글자를 지우지는 않는다.**
    * **복수정답 «3,4».** 「틀린 것을 **두 개** 고르시오」는 내신에 흔하다.
      적는 차례는 사람마다 다르니 **집합으로 견준다** — «4,3» 도 같은 정답이다.
    """
    s = " ".join(str("" if v is None else v).split())
    if not s:
        return ""
    if "," in s:
        parts = [_one_answer(p) for p in s.split(",")]
        parts = [p for p in parts if p]
        return ",".join(sorted(parts))
    return _one_answer(s)


def exam_items(obj):
    """exam.json / report.json 어느 쪽을 줘도 문항 배열을 꺼낸다."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("items", "questions", "문항"):
            v = obj.get(k)
            if isinstance(v, list) and v:
                return v
    return []


def parse_md(text):
    """문항 단위로 쪼갠다 → ({번호: {head, body, meta, flags}}, 겹친 번호)

    md-contract.md § 1: 같은 번호가 두 번 나오면 막는다. 덮어쓰고 넘어가면
    둘 중 무엇을 읽었는지 모르는 채로 통과한다.
    """
    lines = text.splitlines()
    heads = []
    for i, ln in enumerate(lines):
        m = MD_HEAD.match(ln)
        if m:
            heads.append((i, int(m.group(1)), ln))
    out, seen, dup = {}, set(), []
    for k, (i, no, ln) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = "\n".join(lines[i + 1:end])
        meta = {}
        mm = MD_META.search(ln + "\n" + body[:800])
        if mm:
            try:
                meta = json.loads(mm.group(1))
            except ValueError:
                meta = {"__broken__": True}
        if no in seen:
            dup.append(no)
        seen.add(no)
        flags = [str(f) for f in (meta.get("flags") or [])]
        out[no] = {"head": ln, "body": body, "meta": meta, "flags": flags,
                   "issue_notes": MD_FLAG.findall(ln + "\n" + body)}
    return out, sorted(set(dup))


def md_blocks(body):
    """해설 덩어리를 네 칸으로 쪼갠다 (md-contract § 3) → {칸 이름: 내용}

    칸 제목(«**정답 근거**») 에서 다음 칸 제목까지가 그 칸의 내용이다.
    「다음 `**` 까지」로 자르면 **안 된다** — 내용 안에 굵은 글씨(모범답안 등)가
    한 번이라도 나오면 그 칸이 빈 것처럼 보인다. 실제로 서술형 19번이 그랬다.
    """
    pat = re.compile(r"\*\*\s*(%s)\s*\*\*" % "|".join(KILLER_BLOCKS))
    hits = list(pat.finditer(body))
    out = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        out[m.group(1)] = body[m.end():end]
    return out


def head_answer(head):
    """제목 줄에서 정답을 읽는다 — **배점 대괄호 앞까지가 정답이다.**

        ## 36번  정답 ask if your wish was to add an interactive element  [5점] · 난이도 상 · 서술형
                      └──────────────────── 여기까지 ────────────────────┘

    공백에서 끊으면 «ask» 만 읽는다. 실제 기출(명지고2 2026-1학기 기말)에서
    서술형 넷이 그래서 막혔다 — **MD 가 맞고 게이트가 틀렸다.**
    자르는 자리는 `report_build.py` 의 `parse_title` 과 같다 (배점 `[` · 난이도 구분 `·`).
    """
    body = re.sub(r"^\s*#{2,4}\s*\d+\s*[번.)]\s*", "", head).strip()
    if not body.startswith("정답"):
        return None
    tail = body[len("정답"):]
    cut = len(tail)
    for mark in ("[", "·"):                       # 배점·난이도 앞까지가 정답이다
        i = tail.find(mark)
        if i >= 0:
            cut = min(cut, i)
    ans = tail[:cut].strip()
    # 「(추론 정답 — 학교 정답표 미확인)」 같은 꼬리 괄호는 정답이 아니다 (md-contract § 2).
    # 38번의 «(A) her dream / (B) …» 를 다치지 않게 **그 말이 든 괄호만** 떼어 낸다.
    ans = re.sub(r"\s*\([^()]*(?:추론|미확인)[^()]*\)\s*$", "", ans).strip()
    return ans or None


def md_field(rec, key, source="any"):
    """제목 줄과 meta 주석을 **따로** 읽는다.

    md-contract.md § 2 는 「제목 줄 · meta · exam.json 이 넷 중 하나라도 어긋나면」
    막으라고 한다. 둘을 합쳐서 하나로 보면 서로 어긋난 것을 영영 못 본다.
    """
    if source == "meta":
        return rec["meta"].get(key)
    if source == "any" and key in rec["meta"]:
        return rec["meta"][key]
    head = rec["head"]
    if key == "answer":
        return head_answer(head)
    if key == "points":
        m = MD_POINTS.search(head)
        return m.group(1) if m else None
    if key == "difficulty":
        m = MD_DIFF.search(head)
        return m.group(1) if m else None
    if key == "type":
        tail = head.split("·")[-1].strip()
        tail = re.sub(r"\(.*?\)", "", tail).strip()
        if tail and tail != head.strip() and not MD_DIFF.search(tail):
            return tail
        return None
    return None


def check_md(g, md_dir, items, killer_nos, from_exam=True):
    # 대조의 기준은 **언제나 exam.json** 이다. report.json 이 가진 값은 학부모에게
    # «보여 주는» 값이라 원값과 다를 수 있다 — 서술형 정답이 표에서 «서술형» 으로
    # 찍히는 것처럼. 표시값으로 MD 를 나무라면 표시 규칙이 하나 늘 때마다 오차단이 난다.
    if not g.check(from_exam, "MD 대조 · 대조 기준이 exam.json",
                   "--md 를 줬는데 --exam 이 없습니다. report.json 의 값은 «보여 주는» 값이라 "
                   "MD 의 원값과 다를 수 있습니다 — «--exam <exam.json>» 을 함께 주세요"):
        return
    if not os.path.isdir(md_dir):
        g.check(False, "MD 대조 · 폴더 존재", "%s 를 찾지 못했습니다" % md_dir)
        return
    files = [os.path.join(md_dir, f) for f in sorted(os.listdir(md_dir)) if f.endswith(".md")]
    quiz = [f for f in files if "기출문제" in os.path.basename(f)]
    sols = [f for f in files if "기출정답해설" in os.path.basename(f)]

    # 잴 것이 없으면 통과가 아니라 차단이다
    if not g.check(bool(items), "MD 대조 · 대조할 문항 데이터",
                   "exam.json / report.json 이 없어 MD 를 무엇과도 맞춰 볼 수 없습니다"):
        return
    g.check(bool(quiz or sols), "MD 대조 · 대조할 MD 존재",
            "%s 에 «기출문제» · «기출정답해설» MD 가 없습니다 (md 파일 %d개)" % (md_dir, len(files)))
    if not (quiz or sols):
        return
    # md-contract.md § 7 — 같은 낱말을 가진 파일이 둘이면 막는다.
    # 어느 것을 읽었는지 모르는 채로 내보내지 않는다.
    g.check(len(quiz) <= 1 and len(sols) <= 1, "MD 대조 · 읽을 파일이 하나씩",
            "기출문제 %s / 기출정답해설 %s"
            % ([os.path.basename(f) for f in quiz], [os.path.basename(f) for f in sols]))
    if len(quiz) > 1 or len(sols) > 1:
        return

    want = {}
    for it in items:
        no = it.get("no", it.get("number", it.get("번호")))
        if no is None:
            continue
        want[int(no)] = it
    g.check(bool(want), "MD 대조 · 문항 번호 읽힘", "items 에 no 가 없습니다")
    if not want:
        return

    # ── 번호 집합
    for f in quiz + sols:
        rec, dup = parse_md(io.open(f, encoding="utf-8").read())
        base = os.path.basename(f)
        g.check(bool(rec), "%s · 문항 제목 읽힘" % base,
                "«## 11번» / «## 11.» 꼴 제목을 하나도 찾지 못했습니다")
        if not rec:
            continue
        g.check(not dup, "%s · 번호 겹침 없음" % base,
                "같은 번호가 두 번 나옵니다: %s번 — 어느 쪽을 읽었는지 알 수 없습니다" % dup)
        miss = sorted(set(want) - set(rec))
        extra = sorted(set(rec) - set(want))
        g.check(not miss and not extra, "%s · 문항 번호 집합 일치" % base,
                "MD 에 없는 번호 %s / MD 에만 있는 번호 %s" % (miss, extra))

    # ── 제목 줄의 값 ↔ exam.json
    for f in sols:
        base = os.path.basename(f)
        rec, _dup = parse_md(io.open(f, encoding="utf-8").read())
        broken = sorted(n for n, r in rec.items() if r["meta"].get("__broken__"))
        g.check(not broken, "%s · meta 주석 JSON" % base, "깨진 meta 주석: %s번" % broken)

        bad_a, bad_p, bad_d, bad_t = [], [], [], []
        no_a, no_p, no_d, no_t = [], [], [], []

        def cmp3(no, key, ex, eq, show, bad, missing):
            """제목 줄 · meta 주석 · exam.json 셋을 맞춰 본다 (md-contract § 2).

            어느 쪽이 어긋났는지 **이름을 대고** 말한다 — 「MD 가 다릅니다」로는
            어디를 고쳐야 하는지 알 수 없다.
            """
            r = rec[no]
            head_v, meta_v = md_field(r, key, "head"), md_field(r, key, "meta")
            if head_v is None:
                missing.append(no)
            for src, v in (("제목 줄", head_v), ("meta 주석", meta_v)):
                if v is None or not eq(v, ex):
                    if v is not None:
                        bad.append("%d번 %s %s ≠ exam.json %s" % (no, src, show(v), show(ex)))

        def eq_ans(a, b):
            return norm_answer(a) == norm_answer(b)

        def eq_num(a, b):
            try:
                return b is None or abs(float(a) - float(b)) < 0.001
            except (TypeError, ValueError):
                return False

        def eq_txt(a, b):
            return not b or re.sub(r"\s+", "", str(a)) == re.sub(r"\s+", "", str(b))

        for no in sorted(set(rec) & set(want)):
            it = want[no]
            cmp3(no, "answer", it.get("answer"), eq_ans, lambda v: "«%s»" % v, bad_a, no_a)
            cmp3(no, "points", it.get("points"), eq_num, lambda v: "[%s점]" % v, bad_p, no_p)
            cmp3(no, "difficulty", it.get("difficulty"), eq_txt, lambda v: "«%s»" % v, bad_d, no_d)
            cmp3(no, "type", it.get("type"), eq_txt, lambda v: "«%s»" % v, bad_t, no_t)

        g.check(not bad_a, "%s · 정답 일치" % base, " / ".join(bad_a[:5]))
        g.check(not no_a, "%s · 정답 표기 존재" % base, "제목 줄에 «정답 ②» 가 없는 문항: %s" % no_a)
        g.check(not bad_p, "%s · 배점 일치" % base, " / ".join(bad_p[:5]))
        g.check(not no_p, "%s · 배점 표기 존재" % base, "제목 줄에 «[5점]» 이 없는 문항: %s" % no_p)
        g.check(not bad_d, "%s · 난이도 일치" % base, " / ".join(bad_d[:5]))
        g.check(not no_d, "%s · 난이도 표기 존재" % base, "제목 줄에 «난이도 상» 이 없는 문항: %s" % no_d)
        g.check(not bad_t, "%s · 유형 일치" % base, " / ".join(bad_t[:5]))
        g.check(not no_t, "%s · 유형 표기 존재" % base, "제목 줄 끝에 유형이 없는 문항: %s" % no_t)

        # ── killer 는 네 칸이 전부 있어야 한다 (md-contract § 3)
        #    그 글이 리포트 본문에 그대로 실리기 때문이다.
        kill = sorted(set(killer_nos)
                      | {n for n in want if want[n].get("killer")}
                      | {n for n in want if "killer" in [str(x) for x in (want[n].get("flags") or [])]}
                      | {n for n, r in rec.items() if "killer" in r["flags"]})
        nokill = []
        for no in sorted(kill):
            r = rec.get(no)
            if r is None:
                nokill.append("%d번 MD 에 문항이 없음" % no)
                continue
            got = md_blocks(r["body"])
            miss = [b for b in KILLER_BLOCKS
                    if len(re.sub(r"[\s*·\-—–]", "", got.get(b, ""))) < 12]
            if miss:
                nokill.append("%d번 %s 없음" % (no, "·".join(miss)))
        g.check(not nokill, "%s · 킬러문항 네 칸" % base,
                "%s (킬러는 정답 근거·오답 근거·푸는 순서·필요 개념이 전부 있어야 합니다)"
                % " / ".join(nokill[:5]))
        g.warn(not kill, "%s · 킬러문항 표시 없음" % base,
               "killer 로 표시된 문항이 하나도 없어 네 칸을 잴 대상이 없었습니다")

        # ── issue 인데 이유가 없으면 차단 (md-contract § 5)
        noreason, badkind = [], []
        for no in sorted(set(rec) & set(want)):
            it, r = want[no], rec[no]
            iss = it.get("issue")
            kinds = {f.split("/", 1)[1] for f in r["flags"] if f.startswith("issue/")}
            kinds |= {str(f).split("/", 1)[1]
                      for f in (it.get("flags") or []) if str(f).startswith("issue/")}
            notes = {k: (v or "").strip() for k, v in r["issue_notes"]}
            kinds |= set(notes)
            for k in sorted(kinds):
                if k not in ISSUE_KINDS:
                    badkind.append("%d번 «%s» (쓸 수 있는 갈래: %s)"
                                   % (no, k, " · ".join(ISSUE_KINDS)))

            flagged = bool(kinds) or bool(iss) \
                or it.get("confidence") == "low" or it.get("answer_source") == "추론"
            if not flagged:
                continue

            why = ""
            for k in sorted(kinds):                      # <!-- flag: issue/갈래 — 이유 -->
                if notes.get(k):
                    why = notes[k]
            if not why and isinstance(iss, str):
                why = iss.strip()
            # basis 는 «유형 판정» 근거지 «이 문항이 수상한» 이유가 아니다.
            # 여기에 basis 를 넣으면 모든 문항이 이유를 가진 셈이 돼 검사가 죽는다.
            for k in ("issue_reason", "issue_note", "note"):
                if not why:
                    why = str(it.get(k) or "").strip()
            if why:
                continue
            body = r["head"] + r["body"]
            if not any(m in body for m in ISSUE_MARKS):
                noreason.append("%d번%s" % (no, ("(%s)" % ",".join(sorted(kinds))) if kinds else ""))
        g.check(not noreason, "%s · issue 문항 이유" % base,
                "issue 표시인데 «<!-- flag: issue/갈래 — 이유 -->» 도 데이터의 이유도 없습니다: %s"
                % ", ".join(noreason[:8]))
        g.check(not badkind, "%s · issue 갈래 닫힌 목록" % base, " / ".join(badkind[:4]))


# ── 빌더가 채우는 칸 — 회귀 잠금 ──────────────────────────────────────────
# 규격 정본은 references/report-schema.md § 「빌더가 채우는 칸」 이다.
#
# **왜 데이터를 재는가** — 렌더러의 치환자에는 「만약」이 없다. `em` · `key` · `num` 이
# 한 줄이라도 빠지면 «{{em}}» 이 글자로 남아 **렌더가 통째로 실패한다.** 지금까지는
# 렌더가 죽고 나서야 알았다. 여기서 먼저 잡으면 한 벌 57초를 굽기 전에 안다.
# 여섯 검사 모두 report.json 과 판형 **글자**만 본다 — 크롬이 없어도 잰다.


def _is_summary_data(d):
    """요약본 report.json 인가. 표시 둘을 본다.

    `fill_blocks` 는 `--summary` 일 때만 나가고, `items` 섹션은 상세본만 싣는다.
    요약본은 유형을 상위 셋으로 **자르므로** 강조 지목이 그 밖으로 밀릴 수 있다 —
    그때는 차단이 아니라 주의다. 이름이 틀린 것과 순위에 밀린 것은 다른 일이다.
    """
    if "fill_blocks" in d:
        return True
    secs = d.get("sections")
    return isinstance(secs, list) and "items" not in secs


def _slot_bad(row, key, allowed, where):
    """칸 하나를 잰다 — 있는가 · 문자열인가 · 닫힌 목록 안인가.

    참/거짓을 막는 것이 핵심이다. `em: true` 는 종이에 `class="True"` 로 나가
    **아무 것도 칠하지 않으면서 아무 것도 알리지 않는다.**
    """
    if not isinstance(row, dict):
        return "%s 이 «칸 묶음» 이 아닙니다 (%r)" % (where, row)
    if key not in row:
        return "%s 에 %s 가 없습니다" % (where, key)
    v = row.get(key)
    if not isinstance(v, str):
        return "%s 의 %s 가 %r 입니다 — 참/거짓이 아니라 문자열입니다" % (where, key, v)
    if allowed is not None and v not in allowed:
        return "%s 의 %s 가 «%s» 입니다 — %s 중 하나입니다" % (
            where, key, v, " 또는 ".join("«%s»" % a for a in allowed))
    return ""


def _row_at(rows, i):
    r = rows[i] if i < len(rows) else None
    name = ""
    if isinstance(r, dict):
        name = str(r.get("name") or r.get("label") or "")[:16]
    return "%d번째 줄%s" % (i + 1, (" «%s»" % name) if name else "")


def _em_rows(rows):
    return [str(r.get("name")) for r in rows
            if isinstance(r, dict) and str(r.get("em") or "").strip() == "em"]


def check_em_slots(g, d):
    """① `em` 이 **모든 줄**에 있는가 — types · chapters · radar.axes.

    한 줄이라도 빠지면 렌더가 통째로 실패한다. 그래서 빈 값이라도 모든 줄에 온다.
    """
    where = [("types", d.get("types") or []), ("chapters", d.get("chapters") or [])]
    rd = d.get("radar")
    if isinstance(rd, dict) and (rd.get("axes") or []):
        where.append(("radar.axes", rd["axes"]))

    total = sum(len(rows) for _, rows in where if isinstance(rows, list))
    if not total:
        g.warn(True, "데이터 · 막대 em 잴 곳 없음",
               "types 도 chapters 도 radar.axes 도 비어 있어 em 을 한 줄도 재지 못했습니다")
        return

    bad = []
    for label, rows in where:
        if not isinstance(rows, list):
            bad.append("%s 가 목록이 아닙니다" % label)
            continue
        for i in range(len(rows)):
            msg = _slot_bad(rows[i], "em", EM_OK, "%s 의 %s" % (label, _row_at(rows, i)))
            if msg:
                bad.append(msg)
    g.check(not bad, "데이터 · em 이 모든 줄에",
            "%s (%d줄 중 %d줄) — 빈 값이라도 모든 줄에 옵니다. 한 줄만 빠져도 "
            "«{{em}}» 이 남아 렌더가 통째로 실패합니다 (report-schema.md § 빌더가 채우는 칸)"
            % (" / ".join(bad[:4]), total, len(bad)))


def check_card_slots(g, d):
    """② `num` · `unit` · `key` 가 **모든 숫자 카드**에 있는가.

    §3 — 값은 크게, 단위는 작게 붙여 한 덩어리로 둔다. 판형이 둘을 따로 받는다.
    그리고 §0-2 — «말» 카드(`key`)는 넷 중 하나뿐이다.
    """
    cards = (d.get("overview") or {}).get("cards")
    if not isinstance(cards, list) or not cards:
        g.warn(True, "데이터 · 숫자 카드 잴 곳 없음",
               "overview.cards 가 비어 있어 num·unit·key 를 한 칸도 재지 못했습니다")
        return

    bad = []
    for i in range(len(cards)):
        for key in CARD_SLOTS:
            msg = _slot_bad(cards[i], key, KEY_OK if key == "key" else None,
                            "카드 %s" % _row_at(cards, i))
            if msg:
                bad.append(msg)
    g.check(not bad, "데이터 · num·unit·key 가 모든 카드에",
            "%s (카드 %d개) — 한 칸만 빠져도 «{{num}}» 이 남아 렌더가 통째로 실패합니다 "
            "(layout-grammar.md §3)" % (" / ".join(bad[:4]), len(cards)))

    word = [str(c.get("label") or c.get("value") or "?") for c in cards
            if isinstance(c, dict) and str(c.get("key") or "").strip() == "key"]
    g.check(len(word) <= 1, "데이터 · 강조 카드 하나",
            "«말» 카드가 %d개입니다 (%s) — 넷 중 둘을 칠하면 둘 다 안 보입니다 "
            "(layout-grammar.md §0-2 · §3)" % (len(word), " · ".join(word)))


def check_emphasis_link(g, d, exam):
    """③ `emphasis` 가 지목한 이름이 **실제 줄에 있고 그 줄에만** 칠해졌는가.

    exam.json 의 지목이 report.json 까지 살아서 갔는가를 잰다. 두 갈래로 샌다 —
    지목이 조용히 사라지거나(칠할 줄을 안 칠한다), 지목이 없는데 무언가
    칠해지거나(§6 «1위를 자동으로 칠하지 않는다»). 둘 다 종이만 봐서는 모른다.
    """
    src = exam if isinstance(exam, dict) and exam.get("emphasis") is not None else d
    em = src.get("emphasis")
    if em is None:
        em = {}
    if not isinstance(em, dict):
        g.check(False, "데이터 · 강조 지목 꼴",
                'emphasis 가 %r 입니다 — {"types": "…", "chapters": "…"} 꼴이어야 합니다' % (em,))
        return
    if exam is None and not em:
        g.warn(True, "데이터 · 강조 지목 대조 못 함",
               "--exam 을 주지 않아 «지목한 이름이 실제 줄에 있는가» 를 대조하지 "
               "못했습니다 (아래 «칠한 줄 하나» 만 쟀습니다)")

    is_sum = _is_summary_data(d)
    for field, label in (("types", "유형별"), ("chapters", "출제별")):
        rows = d.get(field) or []
        if not isinstance(rows, list) or not rows:
            continue
        names = [str(r.get("name")) for r in rows if isinstance(r, dict)]
        painted = _em_rows(rows)
        want = em.get(field)
        want = str(want).strip() if want not in (None, "") else ""

        g.check(len(painted) <= 1, "데이터 · %s 칠한 줄 하나" % label,
                "%s 막대에 강조가 %d줄입니다 (%s) — 칠할 행은 하나만 지목합니다 "
                "(layout-grammar.md §6)" % (label, len(painted), " · ".join(painted)))

        if not want:
            g.check(not painted, "데이터 · %s 지목 없으면 안 칠한다" % label,
                    "%s 에 지목(exam.json 의 emphasis.%s)이 없는데 «%s» 가 칠해졌습니다 — "
                    "1위를 자동으로 칠하지 않습니다 (§6 · §11)"
                    % (label, field, " · ".join(painted)))
            continue

        if want not in names:
            # 요약본은 유형을 상위 셋으로 자른다 — 순위에 밀린 것은 이름이 틀린 것과 다르다
            if is_sum and field == "types":
                g.warn(True, "%s 강조가 요약본 밖" % label,
                       "«%s» 는 요약본에 실리는 상위 %d줄 밖이라 요약본에는 안 칠해집니다"
                       % (want, len(names)))
            else:
                g.check(False, "데이터 · %s 지목한 줄이 있다" % label,
                        "«%s» 를 지목했는데 그런 줄이 없습니다. 있는 줄: %s — "
                        "조용히 안 칠하고 넘어가지 않습니다 (§6)" % (want, " · ".join(names)))
            continue

        g.check(painted == [want], "데이터 · %s 지목한 줄이 칠해졌다" % label,
                "«%s» 를 지목했는데 칠해진 줄은 %s — 지목이 report.json 까지 "
                "못 갔습니다 (§6)"
                % (want, ("«%s»" % " · ".join(painted)) if painted else "없습니다"))


def check_radar_slots(g, d):
    """④ `radar.ok` 가 «1» 인데 축이 3 미만이면 막는다.

    §9-2 — 둘로는 삼각형도 안 된다. `ok` 는 참/거짓이 아니라 «1» 또는 «» 다:
    판형이 `data-ok` 에 그대로 꽂으므로 `true` 가 오면 상자가 켜진 채 빈 채로 나간다.
    """
    rd = d.get("radar")
    if rd is None:
        g.warn(True, "데이터 · 레이다 칸 잴 것 없음",
               "report.json 에 radar 가 없습니다 — 빌더가 펴지 않았습니다")
        return
    if not isinstance(rd, dict):
        g.check(False, "데이터 · 레이다 꼴", "radar 가 %r 입니다" % (rd,))
        return

    msg = _slot_bad(rd, "ok", RADAR_OK, "radar")
    g.check(not msg, "데이터 · 레이다 ok 값",
            "%s — 판형의 data-ok 에 그대로 꽂힙니다 (§9-2)" % msg)

    ok = rd.get("ok") if isinstance(rd.get("ok"), str) else ""
    axes = rd.get("axes") or []
    if ok.strip() != "1":
        return
    g.check(len(axes) >= 3, "데이터 · 레이다 ok=1 이면 축 셋 이상",
            "radar.ok 가 «1» 인데 축이 %d개입니다 — 셋부터 그립니다. 둘로는 삼각형도 "
            "안 됩니다 (§9-2)" % len(axes))
    g.check(bool(str(rd.get("points") or "").strip()), "데이터 · 레이다 꼭짓점",
            "radar.ok 가 «1» 인데 points 가 비었습니다 — 켜 놓고 점을 안 찍으면 "
            "빈 고리만 인쇄됩니다 (§9-2)")


def check_steps_flow_data(g, d):
    """⑤ 한 «푸는 순서» 에 갈린 칸(`em`)이 둘 이상이면 막는다.

    §5 — 실제로 갈린 칸은 하나다. 그리고 네 칸(text·conclusion·em·value)이
    **모든 줄에** 온다 — 화살표가 없으면 `conclusion` 은 빈 문자열이지 없는 칸이 아니다.
    """
    lists = []
    for k in d.get("killer") or []:
        if isinstance(k, dict) and k.get("steps_flow") is not None:
            lists.append((k.get("no"), k.get("steps_flow")))
    if not lists:
        g.warn(True, "데이터 · 푸는 순서 잴 곳 없음",
               "killer[].steps_flow 가 하나도 없어 갈린 칸 규칙을 재지 못했습니다")
        return

    bad, many = [], []
    for no, rows in lists:
        if not isinstance(rows, list):
            bad.append("%s번의 steps_flow 가 목록이 아닙니다" % no)
            continue
        for i in range(len(rows)):
            for key in STEP_SLOTS:
                msg = _slot_bad(rows[i], key, EM_OK if key == "em" else None,
                                "%s번 푸는 순서 %d번째 칸" % (no, i + 1))
                if msg:
                    bad.append(msg)
        n = len([r for r in rows
                 if isinstance(r, dict) and str(r.get("em") or "").strip() == "em"])
        if n > 1:
            many.append("%s번에 ★ 가 %d칸" % (no, n))

    g.check(not bad, "데이터 · 푸는 순서 네 칸",
            "%s (목록 %d개) — 빈 값이라도 모든 줄에 옵니다 (report-schema.md)"
            % (" / ".join(bad[:4]), len(lists)))
    g.check(not many, "데이터 · 목록마다 갈린 칸 하나",
            "%s — 실제로 갈린 칸은 하나입니다 (layout-grammar.md §5 · md-contract.md §3-2)"
            % " / ".join(many[:4]))


def check_fill_slots(g, d):
    """⑥ `fill_blocks[].section` 이 판형의 `SECTION:fill-*` 이름과 맞는가.

    안 맞으면 렌더러는 **막지 않고 조용히 뺀다** — `fill_candidates` 가 「켤 자리
    없음」 한 줄만 남긴다. 요약본 아래가 53mm 비어도 아무 것도 안 켜졌던 사고가
    그것이다(수학 목업에서야 드러났다).

    `key` 를 `section` 자리에 적는 것도 막는다. 「study-plan」은 **요약본 판형에도
    있는 진짜 섹션 이름**이라, 렌더러가 채움 자리 대신 그 섹션을 켠다.
    """
    fb = d.get("fill_blocks")
    if fb is None:
        return                       # 상세본은 채움 블록을 갖지 않는다 (--summary 전용)
    if not isinstance(fb, list):
        g.check(False, "데이터 · 채움 블록 꼴", "fill_blocks 가 %r 입니다" % (fb,))
        return
    if fb and not _is_summary_data(d):
        g.check(False, "데이터 · 채움 블록은 요약본만",
                "상세본 report.json 에 채움 블록이 %d개 있습니다 — "
                "--summary 일 때만 나갑니다" % len(fb))
        return
    if not fb:
        g.warn(True, "데이터 · 채움 블록 잴 곳 없음",
               "fill_blocks 가 비어 있어 자리 이름을 하나도 재지 못했습니다")
        return

    if not os.path.exists(SUMMARY_TPL):
        g.check(False, "데이터 · 채움 자리 대조",
                "요약본 판형을 찾지 못해 자리 이름을 대조하지 못했습니다: %s" % SUMMARY_TPL)
        return
    slots = sorted(set(FILL_SLOT.findall(io.open(SUMMARY_TPL, encoding="utf-8").read())))
    g.check(bool(slots), "데이터 · 판형에 채움 자리",
            "요약본 판형에 «SECTION:fill-…» 자리가 하나도 없습니다 — 대조할 것이 없습니다")
    if not slots:
        return

    bad, seen = [], {}
    for i, b in enumerate(fb, 1):
        if not isinstance(b, dict):
            bad.append("%d번째 블록이 «칸 묶음» 이 아닙니다" % i)
            continue
        name = str(b.get("title") or b.get("key") or i)
        sec = b.get("section")
        if not isinstance(sec, str) or not sec.strip():
            bad.append("«%s» 에 section 이 없습니다 — 렌더러가 key 로 대신 찾다가 "
                       "엉뚱한 섹션을 켭니다" % name)
            continue
        sec = sec.strip()
        if sec not in slots:
            bad.append("«%s» 의 자리 이름 «%s» 가 판형에 없습니다" % (name, sec))
            continue
        seen.setdefault(sec, []).append(name)

    dup = ["%s 에 %s" % (s, " · ".join(v)) for s, v in seen.items() if len(v) > 1]
    g.check(not bad, "데이터 · 채움 자리 이름",
            "%s — 판형이 내준 자리는 %s 입니다. key(상세본 섹션 이름)와 "
            "section(판형 자리 이름)은 **다릅니다** (report-schema.md § fill_blocks)"
            % (" / ".join(bad[:4]), " · ".join(slots)))
    g.check(not dup, "데이터 · 한 자리에 한 블록",
            "%s — 한 자리에 둘을 넣으면 뒤엣것이 앞엣것을 덮습니다" % " / ".join(dup))


def check_builder_fields(g, d, exam=None):
    """빌더가 채우는 칸 여섯 — em · num/unit/key · 강조 지목 · 레이다 · 푸는 순서 · 채움 자리."""
    check_em_slots(g, d)
    check_card_slots(g, d)
    check_emphasis_link(g, d, exam)
    check_radar_slots(g, d)
    check_steps_flow_data(g, d)
    check_fill_slots(g, d)


def check_data(g, path):
    d = json.load(io.open(path, encoding="utf-8"))
    meta = d.get("meta") or {}
    items = d.get("items") or []

    g.check(bool(items), "데이터 · 문항 존재", "items 가 비었습니다")
    if not items:
        return d

    g.check(len(items) == meta.get("total_items"), "데이터 · 문항 수 일치",
            "meta %s ≠ 실제 %d" % (meta.get("total_items"), len(items)))

    s = sum(float(i.get("points") or 0) for i in items)
    g.check(abs(s - float(meta.get("total_points") or 0)) < 0.01, "데이터 · 배점 합 일치",
            "합 %g ≠ 총점 %s" % (s, meta.get("total_points")))

    noans = [i.get("no") for i in items if not str(i.get("answer") or "").strip()]
    g.check(not noans, "데이터 · 정답 채워짐", "정답 없는 문항: %s" % noans)

    # 숫자로 적힌 정답은 선지 범위 안이어야 한다 (서술형의 글자 정답은 그대로 둔다)
    oob = [i.get("no") for i in items
           if str(i.get("answer") or "").strip().isdigit()
           and not (1 <= int(str(i.get("answer")).strip()) <= 5)]
    g.check(not oob, "데이터 · 정답 선지 범위", "①~⑤ 밖의 정답: %s" % oob)

    baddiff = [i.get("no") for i in items if i.get("difficulty") not in DIFFS]
    g.check(not baddiff, "데이터 · 난이도 5단", "규격 밖: %s" % baddiff)

    nobasis = [i.get("no") for i in items if not str(i.get("basis") or "").strip()]
    g.check(not nobasis, "데이터 · 유형 판정 근거", "basis 없는 문항: %s" % nobasis)

    # §9-2 — 레이다는 축이 셋부터다. 둘로는 삼각형도 안 된다.
    # 종이 쪽은 check_radar_markup 이 재고, 여기서는 빌더가 낸 값을 쟄다 —
    # 요약본의 sections 에 radar 가 없으면 종이에는 상자가 아예 안 나온다.
    rd = d.get("radar")
    if isinstance(rd, dict):
        axes = rd.get("axes") or []
        ok = str(rd.get("ok") or "").strip()
        drawn = bool(axes) or bool(str(rd.get("points") or "").strip())
        if ok:
            g.check(len(axes) >= 3, "데이터 · 레이다 축 3 이상",
                    "radar.ok 가 켜졌는데 축이 %d개입니다 — 셋부터 그립니다 (§9-2)" % len(axes))
        else:
            g.check(not drawn, "데이터 · 레이다 축 3 미만이면 안 그린다",
                    "radar.ok 가 비었는데 축 %d개·꼭짓점이 있습니다 — "
                    "안 그릴 거면 좌표를 내지 않습니다 (§9-2)" % len(axes))
    else:
        g.warn(True, "데이터 · 레이다 쟴 것 없음",
               "report.json 에 radar 가 없습니다 — 빌더가 펼지 않았습니다")

    low = [i.get("no") for i in items if i.get("confidence") == "low"]
    if low:
        g.check(bool(d.get("low_confidence_reviewed")),
                "데이터 · 저신뢰 판독 확인됨",
                "원장님 확인 기록(low_confidence_reviewed)이 없습니다. 문항 %s" % low)

    guessed = [i.get("no") for i in items if i.get("answer_source") == "추론"]
    g.warn(bool(guessed), "추론으로 낸 정답이 있습니다", "문항 %s — 학교 정답표로 덮어쓰기를 권합니다" % guessed)

    gc = d.get("grade_cut") or {}
    if gc.get("enabled"):
        g.check(bool(str(gc.get("basis") or "").strip()), "데이터 · 등급컷 근거",
                "등급컷을 켰는데 산출 근거(basis)가 없습니다")
        g.check(bool(str(gc.get("disclaimer") or "").strip()), "데이터 · 등급컷 고지",
                "「예상치」 고지 문구가 없습니다")
    return d


def parse_args(argv):
    out, data, exam, md = None, None, None, None
    dataonly = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--data" and i + 1 < len(argv):
            # 종이 없이 데이터만 잰다 — 두 번째 자리(report.json)를 첫 자리로 받는다
            data, dataonly = argv[i + 1], True
            i += 2
        elif a == "--exam" and i + 1 < len(argv):
            exam = argv[i + 1]
            i += 2
        elif a == "--md" and i + 1 < len(argv):
            md = argv[i + 1]
            i += 2
        elif a.startswith("--"):
            raise SystemExit("모르는 인자입니다: %s\n%s" % (a, __doc__))
        elif out is None:
            out = a
            i += 1
        elif data is None:
            data = a
            i += 1
        else:
            raise SystemExit("인자가 너무 많습니다: %s\n%s" % (a, __doc__))
    return out, data, exam, md, dataonly


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out, datapath, exampath, mddir, dataonly = parse_args(sys.argv[1:])
    g = Gate()

    exam = None
    if exampath:
        exam = json.load(io.open(exampath, encoding="utf-8"))

    # ── 데이터만 재는 길 — 크롬도 산출 폴더도 없이 돈다
    if dataonly:
        print("\n=== 완료 게이트 (데이터만) ===")
        data = check_data(g, datapath)
        check_builder_fields(g, data, exam)
        g.warn(True, "조판 미검사",
               "--data 로 돌려 종이를 하나도 보지 않았습니다 — 쪽수·채움률·잘림·"
               "쪽번호는 재지 못했습니다. 이것만으로 완료를 말하지 않습니다")
        sys.exit(g.report())

    print("\n=== 완료 게이트 ===")
    htmls = [os.path.join(out, f) for f in sorted(os.listdir(out)) if f.endswith(".html")]
    pdfs = [os.path.join(out, f) for f in sorted(os.listdir(out)) if f.endswith(".pdf")]

    data = None
    if datapath:
        data = check_data(g, datapath)
        # 빌더가 채우는 칸 여섯 — 종이가 아니라 데이터를 잰다.
        # 렌더가 죽고 나서야 알던 것을 여기서 먼저 말한다.
        check_builder_fields(g, data, exam)
    else:
        g.warn(True, "report.json 미검사", "데이터 검사를 하려면 두 번째 인자로 주세요")

    g.check(bool(htmls), "산출 · HTML 존재", "%s 에 html 이 없습니다" % out)
    for p in htmls:
        check_html(g, p, data)

    if pdfs:
        # HTML 은 있는데 PDF 만 빠진 산출물이 있으면 그 산출물의 조판은 통째로 재지 못한다.
        # 예전에는 그것이 아무 표시 없이 지나갔다 — 「PDF 가 하나라도 있으면」 통과였다.
        lone = [os.path.basename(h) for h in htmls
                if not os.path.exists(h[:-5] + ".pdf")]
        g.check(not lone, "산출 · HTML 마다 PDF", "PDF 가 없는 HTML: %s" % ", ".join(lone))
        for p in pdfs:
            check_pdf(g, p)
            check_pdf_layout(g, p)
    else:
        sums = [os.path.basename(h) for h in htmls if "요약본" in os.path.basename(h)]
        g.warn(True, "PDF 없음",
               "render_pdf.py 를 아직 돌리지 않았습니다 — 조판(제목만 있는 장·표 머리글·채움률"
               "·내용 잘림%s)을 하나도 재지 못했습니다%s"
               % ("·요약본 쪽수" if sums else "",
                  (" / 요약본: %s" % ", ".join(sums)) if sums else ""))

    # ── MD ↔ 리포트 대조
    # 문항도 킬러 목록도 **같은 파일**에서 가져온다. --exam 을 줬는데 report.json 의
    # 킬러 번호를 섞으면 다른 회차의 번호로 남의 MD 를 나무라게 된다.
    items, killer_nos, src = [], set(), None
    if exam is not None:
        src = exam
    elif data is not None:
        src = data
    if src is not None:
        items = exam_items(src)
        if isinstance(src, dict):
            for k in src.get("killer") or []:
                if isinstance(k, dict) and k.get("no") is not None:
                    killer_nos.add(int(k["no"]))

    if mddir:
        check_md(g, mddir, items, killer_nos, from_exam=bool(exampath))
    else:
        g.warn(True, "MD 대조 미실시",
               "--md <폴더> 를 주지 않아 MD 의 번호·정답·배점·난이도·유형을 하나도 대조하지 못했습니다")

    sys.exit(g.report())


if __name__ == "__main__":
    main()
