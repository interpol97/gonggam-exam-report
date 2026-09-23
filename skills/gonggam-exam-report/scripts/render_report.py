#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report.json  →  리포트 HTML (+ 쪽수를 잰 PDF)

Claude 는 HTML 을 쓰지 않는다. 데이터만 쓴다. 조판은 여기서 한다.
그래서 LaTeX 이스케이프 사고가 원천적으로 일어나지 않는다 —
파이썬 문자열 안에 \\frac 을 넣는 코드가 아예 없다.

사용:
    python render_report.py report.json out/            # 배포본
    python render_report.py report.json out/ --internal # 내부본
    python render_report.py report.json out/ --summary  # 요약본 템플릿으로

쪽 나눔 — **추측하지 않는다**
    옛 방식은 «한 장에 20행» 같은 상수로 표를 미리 쪼개서 한 장씩 담았다.
    내용이 조금만 길어지면 한 장이 두 장으로 넘쳐 표기 쪽수와 실제 쪽수가 어긋났고
    (12쪽 표기 / 13쪽 인쇄), 짧은 섹션도 한 장을 통째로 먹어 채움률이 35% 였다.

    지금은 섹션이 그냥 흐른다. 잘리면 안 되는 것만 CSS 불가분 단위로 묶는다
    (표의 행·카드·콜아웃·제목+본문·고아/과부 2줄 — assets/template.html @media print).
    쪽번호는 **실제 PDF 를 재서** 박는다:

      1패스  쪽번호 자리에 고정폭 «00 / 00» 을 넣고 렌더 → PDF
             (자리표시자를 흐름 밖 absolute 로 두어 숫자가 바뀌어도 조판이 안 밀린다)
      측정   PyMuPDF 로 총 쪽수와 «각 섹션 제목이 몇 쪽에 있는지» 를 읽는다
      2패스  진짜 숫자를 넣어 다시 렌더 → PDF → 다시 재서 «쓴 값 == 잰 값» 을 확인
             같아질 때까지 (최대 4패스) 돌리고, 끝내 안 맞으면 렌더를 실패시킨다

템플릿 지시자
    <!-- SECTION:key -->...<!-- /SECTION:key -->   sections 에 없으면 통째로 제거
    <!-- REPEAT:path -->...<!-- /REPEAT:path -->   목록을 되풀이 (path 는 점 표기 가능)
    {{KEY}} {{a.b}}                                치환 (없으면 렌더 실패)
    {{#SEC}}                                       섹션 번호 — 섹션 블록마다 하나
    {{PAGE_NUM}} {{TOTAL_PAGES}}                   쪽번호 — 사람이 세지 않는다.
                                                   {{PAGE_NUM}} 은 그 섹션이 **시작하는** 쪽이며
                                                   반드시 섹션 제목 뒤에 놓는다
    {{@index}} {{@n}}                              REPEAT 안에서 0부터 / 1부터
"""

import base64
import io
import json
import mimetypes
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)      # 어디서 부르든 outname 을 찾는다
SKILL = os.path.dirname(HERE)
TEMPLATE = os.path.join(SKILL, "assets", "template.html")
TEMPLATE_SUMMARY = os.path.join(SKILL, "assets", "template_summary.html")
THEMES = os.path.join(SKILL, "assets", "themes")
FONTS = os.path.join(SKILL, "assets", "fonts")

# 배포본에서 빼는 섹션·필드 (내부본은 전부 남긴다)
INTERNAL_ONLY_FIELDS = ("basis", "confidence", "answer_source", "note")

# 쪽번호 자리표시자 — 고정폭 두 글자. 흐름 밖(absolute)이라 폭이 바뀌어도 조판은 그대로다.
PLACEHOLDER = "00"
MAX_PASSES = 4
MAX_FILL_ROUNDS = 4        # 채움 블록을 넣고 빼며 다시 그리는 횟수 한도


class RenderError(Exception):
    pass


# ---------------------------------------------------------------- 값 찾기
def lookup(data, path):
    """'a.b.c' 를 따라 내려간다. 없으면 KeyError."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            # 범위를 벗어나면 IndexError 로 **죽는다.** 부르는 쪽은 KeyError 만
            # 잡으므로, 「채워지지 않은 자리」라는 곱은 말 대신 역추적이 뜬다.
            # {{killer.0.no}} 를 쓰는데 killer 가 빈 목록일 때가 그 자리다.
            if int(part) >= len(cur):
                raise KeyError(path)
            cur = cur[int(part)]
        else:
            raise KeyError(path)
    return cur


def as_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, float) and v == int(v):
        return str(int(v))          # 배점 3.0 을 «3.0점» 으로 찍지 않는다
    if isinstance(v, (list, tuple)):
        return " · ".join(as_text(x) for x in v)
    if isinstance(v, dict):
        # 사전이 그대로 «{'a': 1}» 로 인쇄된 적이 있다. 조용히 새어 나가게 두지 않는다.
        raise RenderError("값이 사전입니다 — 한 칸에 넣을 수 없습니다: %r" % (v,))
    return str(v)


def esc(s):
    """HTML 로 들어가는 모든 값은 escape 한다.

    국어 지문의 «<보기>» 가 태그로 먹혀 화면에서 통째로 사라진 적이 있다.
    이 스킬에서 Claude 는 데이터만 쓰고 markup 은 쓰지 않으므로, 값에 든 <,&,"
    는 **언제나** 글자다."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def unesc(s):
    """escape 를 되돌린다 — PDF 안에서 글자로 찾으려면 원래 글자여야 한다."""
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&"))


# ---------------------------------------------------------------- 내부본 전용
INTERNAL_RE = re.compile(r"<!--\s*INTERNAL\s*-->(.*?)<!--\s*/INTERNAL\s*-->", re.S)


def apply_internal(html, internal):
    """내부본에만 남기는 칸 (판정 근거·판독 신뢰도).
    배포본은 칸 자체가 사라진다 — 빈 칸이 남으면 학부모가 «왜 비었나» 묻는다."""
    return INTERNAL_RE.sub((lambda m: m.group(1)) if internal else "", html)


# ---------------------------------------------------------------- 섹션
SEC_RE = re.compile(r"<!--\s*SECTION:([a-z0-9\-]+)\s*-->(.*?)<!--\s*/SECTION:\1\s*-->", re.S)


def apply_sections(html, keep):
    """고르지 않은 섹션을 마커째 제거하고, **섹션마다 번호를 하나씩** 준다.

    번호를 여기서 매기는 것이 중요하다. 예전에는 치환이 다 끝난 뒤 `{{#SEC}}` 가
    나온 순서대로 매겼는데, 긴 표를 여러 장으로 쪼개면 **같은 섹션이 두 번호를
    썼다** — 「2. 문항별 분석표」 다음 장이 「3. 문항별 분석표」가 됐고 목차가 무너졌다.
    섹션 블록 단위로 매기면 그 안의 모든 페이지가 같은 번호를 쓴다."""
    keep = set(keep)
    seen = []
    n = {"v": 0}

    def sub(m):
        key, body = m.group(1), m.group(2)
        if key not in keep:
            return ""
        seen.append(key)
        if "{{#SEC}}" in body:
            n["v"] += 1
            body = body.replace("{{#SEC}}", str(n["v"]))
        return body

    out = SEC_RE.sub(sub, html)
    missing = [k for k in keep if k not in seen]
    if missing:
        raise RenderError("템플릿에 없는 섹션을 골랐습니다: %s" % ", ".join(sorted(missing)))
    return out, seen


# ---------------------------------------------------------------- 되풀이
REPEAT_RE = re.compile(r"<!--\s*REPEAT:([a-zA-Z0-9_.\-]+)\s*-->(.*?)<!--\s*/REPEAT:\1\s*-->", re.S)


def apply_repeats(html, data, strip_internal):
    """가장 안쪽부터 펼친다."""
    while True:
        m = REPEAT_RE.search(html)
        if not m:
            return html
        path, body = m.group(1), m.group(2)
        try:
            rows = lookup(data, path)
        except KeyError:
            raise RenderError("REPEAT 대상이 report.json 에 없습니다: %s" % path)
        if not isinstance(rows, list):
            raise RenderError("REPEAT 대상이 목록이 아닙니다: %s" % path)

        chunks = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                row = {"value": row}
            row = dict(row)
            if strip_internal:
                # 지우지 않고 비운다 — 지우면 {{basis}} 가 허공에 남아 렌더가 실패한다
                for f in INTERNAL_ONLY_FIELDS:
                    if f in row:
                        row[f] = ""

            row["@index"] = i
            row["@n"] = i + 1
            # 행 안의 중첩 REPEAT(killer.steps 같은 것)은 «그 행»을 범위로 펼친다.
            # 바깥부터 펼치되 안쪽은 행 범위에서 찾아야 한다 — 루트에는 steps 가 없다.
            scope = dict(data)
            scope.update(row)
            chunks.append(fill_row(apply_repeats(body, scope, strip_internal), row, data))
        html = html[: m.start()] + "".join(chunks) + html[m.end():]


ROW_RE = re.compile(r"\{\{([@a-zA-Z0-9_.\-]+)\}\}")
KEEP_KEYS = ("#SEC", "PAGE_NUM", "TOTAL_PAGES")


def fill_row(body, row, root):
    """REPEAT 한 줄. 행에 없는 키는 루트에서 찾는다 (브랜드·메타 참조용)."""
    def sub(m):
        key = m.group(1)
        if key in KEEP_KEYS:
            return m.group(0)          # 쪽번호는 맨 마지막에 «재서» 넣는다
        if key in row:
            return esc(as_text(row[key]))
        try:
            return esc(as_text(lookup(root, key)))
        except KeyError:
            return m.group(0)          # 바깥 단계에서 처리하도록 남긴다
    return ROW_RE.sub(sub, body)


# ---------------------------------------------------------------- 번호
def number_sections(html):
    """남은 섹션에 1부터 다시 매긴다. 결번이 생길 수 없다."""
    counter = {"n": 0}

    def sub(_m):
        counter["n"] += 1
        return str(counter["n"])

    return re.sub(r"\{\{#SEC\}\}", sub, html)


# ---------------------------------------------------------------- 쪽번호 (측정식)
# 자리표는 «소스에 보이는 글자» 로만 짓는다. 파일 안에 눈에 안 보이는 제어문자를 박아 두면
# 다음에 손대는 사람이 그것을 못 본다 — 이 저장소에서 이미 여러 번 난 사고다.
SENTINEL = chr(1)                            # 데이터에는 들어올 일이 없는 글자
PAGE_NUM_TOKEN = SENTINEL + "PN%d" + SENTINEL   # HTML 에 남을 일이 없는 자리표
TOTAL_TOKEN = SENTINEL + "TP" + SENTINEL
MARK_RE = re.compile(r'class="section-title"[^>]*>(.*?)<|\{\{PAGE_NUM\}\}', re.S)


def stage_page_marks(html):
    """`{{PAGE_NUM}}` 을 자리표로 바꾸고, 그 자리가 «어느 섹션 제목의 쪽인가» 를 기록한다.

    쪽번호는 섹션이 **시작하는** 쪽이다. 그래서 찾을 표지는 바로 앞의 섹션 제목이며,
    나중에 PDF 안에서 그 제목 글자를 찾아 몇 쪽인지 읽는다."""
    anchors = []
    state = {"title": None, "n": 0}

    def sub(m):
        if m.group(1) is not None:                    # 섹션 제목을 지나간다
            state["title"] = unesc(re.sub(r"<[^>]+>", "", m.group(1)))
            return m.group(0)
        if state["title"] is None:
            raise RenderError(
                "{{PAGE_NUM}} 이 섹션 제목보다 먼저 나왔습니다.\n"
                "  → 쪽번호는 «그 섹션이 시작하는 쪽» 이므로 제목 뒤에 두어야 합니다."
            )
        anchors.append(state["title"])
        tok = PAGE_NUM_TOKEN % state["n"]
        state["n"] += 1
        return tok

    html = MARK_RE.sub(sub, html)
    html = html.replace("{{TOTAL_PAGES}}", TOTAL_TOKEN)
    return html, anchors


def paint_marks(skeleton, anchors, pages, total):
    """자리표에 숫자(또는 고정폭 자리표시자)를 박는다."""
    out = skeleton
    for i in range(len(anchors)):
        v = PLACEHOLDER if pages is None else str(pages[i])
        out = out.replace(PAGE_NUM_TOKEN % i, v)
    return out.replace(TOTAL_TOKEN, PLACEHOLDER if total is None else str(total))


def squash(s):
    """공백을 전부 지운다 — PDF 텍스트는 줄바꿈 자리에 공백이 생기거나 없어진다."""
    return re.sub(r"\s+", "", s)


def mark_is_printed(pdf_path):
    """1패스의 자리표시자(«00 / 00»)가 **종이에 나왔나.**

    안 나왔다면 그 판형은 쪽 표시를 인쇄에서 감춘다는 뜻이다(기본 템플릿이 그렇다 —
    종이의 쪽번호는 render_pdf.py 가 실측해 찍는다). 그러면 숫자를 바꿔도 조판이
    변할 수 없으니 두 번째로 그릴 이유가 없다.

    ⚠ 판형을 만드는 쪽에 주는 규칙 — 쪽 표시를 인쇄에서 감출 거면 `display:none` 이나
    흐름 밖(absolute)으로 감춘다. 자리는 차지한 채 감추면(visibility:hidden) 숫자 폭이
    바뀌며 조판이 밀릴 수 있고, 그러면 이 지름길이 어긋난다."""
    import fitz

    doc = fitz.open(pdf_path)
    text = squash("".join(p.get_text() for p in doc))
    doc.close()
    return (PLACEHOLDER + "/" + PLACEHOLDER) in text


def measure_pdf(pdf_path, anchors):
    """PDF 를 열어 총 쪽수와 각 섹션 제목이 있는 쪽을 읽는다. 사람이 세지 않는다."""
    try:
        import fitz                                   # PyMuPDF
    except ImportError:
        raise RenderError(
            "PyMuPDF 가 없어 쪽수를 «잴» 수 없습니다.\n"
            "  → pip install pymupdf\n"
            "  쪽번호를 추측해서 찍지는 않습니다 — 표기와 실제가 어긋난 채 나가는 것이 더 나쁩니다."
        )
    doc = fitz.open(pdf_path)
    total = doc.page_count
    texts = [squash(p.get_text()) for p in doc]
    doc.close()

    pages, start = [], 0
    for a in anchors:
        needle = squash(a)
        hit = None
        for i in range(start, len(texts)):
            if needle and needle in texts[i]:
                hit, start = i + 1, i
                break
        if hit is None:
            raise RenderError(
                "PDF 안에서 섹션 제목을 찾지 못했습니다: «%s»\n"
                "  → 제목이 이미지로 그려졌거나 폰트에 ToUnicode 가 없을 수 있습니다." % a.strip()
            )
        pages.append(hit)
    return total, pages


# ---------------------------------------------------------------- 남은 높이 재기·채우기
MM = 72.0 / 25.4                       # 1mm 가 PDF 로 몇 pt 인가
STAMP_RE = re.compile(r"^\d+\s*/\s*\d+\s*(?:페이지|쪽)$")
UNIT_PT = {"mm": MM, "cm": MM * 10, "in": 72.0, "pt": 1.0, "px": 0.75}


def page_bottom_limit(html, page_height):
    """인쇄 한계 y. `@page` 의 아래 여백을 **읽어서** 정한다 — 짐작하지 않는다.
    읽을 수 없으면 None 을 돌려주고, 부르는 쪽은 채우기를 건너뛴다."""
    m = re.search(r"@page\s*\{[^}]*?margin\s*:\s*([^;}]+)", html, re.I)
    if not m:
        return None
    nums = []
    for v in m.group(1).split():
        g = re.match(r"^(-?\d+(?:\.\d+)?)(mm|cm|in|pt|px)$", v.strip())
        if not g:
            return None
        nums.append(float(g.group(1)) * UNIT_PT[g.group(2)])
    if not nums:
        return None
    bottom = nums[2] if len(nums) >= 3 else nums[0]     # 1·2값이면 위아래가 같다
    return page_height - bottom


def ink_rows(page):
    """이 장에서 잉크가 있는 세로 구간들. 쪽번호 도장과 바탕 사각형은 잉크로 세지 않는다."""
    H = page.rect.height
    rows = []
    for b in page.get_text("blocks"):
        t = (b[4] or "").strip()
        if t and not STAMP_RE.match(" ".join(t.split())):
            rows.append([b[1], b[3]])
    for d in page.get_drawings():
        r = d["rect"]
        if r.height <= 0.3 or r.width <= 0.3 or r.height > H * 0.8:
            continue
        fill = d.get("fill")
        if fill and len(fill) >= 3 and all(c > 0.97 for c in fill) and d.get("stroke") is None:
            continue
        rows.append([r.y0, r.y1])
    rows.sort()
    merged = []
    for a, b in rows:
        if merged and a <= merged[-1][1] + 0.5:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def blank_band(pdf_path, html):
    """(빈 띠 높이 mm, 그 띠가 시작하는 위치 mm). 못 재면 (None, None).
    자리를 함께 돌려주는 것은 «어디가 비었는지» 를 사람이 대조할 수 있게 하기 위해서다."""
    import fitz

    doc = fitz.open(pdf_path)
    page = doc[doc.page_count - 1]
    H = page.rect.height
    rows = ink_rows(page)
    doc.close()
    limit = page_bottom_limit(html, H)
    if limit is None or not rows:
        return None, None
    gaps = [(rows[i + 1][0] - rows[i][1], rows[i][1]) for i in range(len(rows) - 1)]
    gaps.append((limit - rows[-1][1], rows[-1][1]))
    top_gap, top_y = max(gaps)
    return top_gap / MM, top_y / MM


def blank_mm(pdf_path, html):
    """마지막 장에서 **가장 큰 빈 띠**가 몇 mm 인가. 못 재면 None.

    «마지막 글자 아래» 만 재면 안 된다 — 꼬리말이 맨 아래에 붙는 판형에서는 그 값이
    늘 0 이다. 요약본에서 실제로 비는 자리는 총평과 꼬리말 **사이**다. 그래서 장 안의
    빈 띠를 모두 재고 가장 큰 것을 고른다 (사람 눈에 «여백» 으로 보이는 바로 그 자리)."""
    import fitz

    doc = fitz.open(pdf_path)
    page = doc[doc.page_count - 1]
    H = page.rect.height
    rows = ink_rows(page)
    doc.close()
    limit = page_bottom_limit(html, H)
    if limit is None or not rows:
        return None
    gaps = [rows[i + 1][0] - rows[i][1] for i in range(len(rows) - 1)]
    gaps.append(limit - rows[-1][1])
    return max(gaps) / MM


SPEC_MD = os.path.join(SKILL, "references", "summary-spec.md")


def spec_heights():
    """채움 블록의 **실측 최소 높이**를 규격에서 읽는다 (summary-spec.md §4-1).

    판형을 만든 쪽이 크롬으로 재서 규격에 적는다 — 렌더러는 그것을 읽을 뿐이다.
    표의 어느 칸에 있든 «fill-xxx» 와 «NN.Nmm» 이 같은 줄에 있으면 읽는다."""
    if not os.path.exists(SPEC_MD):
        return {}
    out = {}
    for line in io.open(SPEC_MD, encoding="utf-8"):
        keys = re.findall(r"fill-[a-z0-9\-]+", line)
        mm = re.search(r"(\d+(?:\.\d+)?)\s*mm", line)
        if len(keys) == 1 and mm:
            out[keys[0]] = float(mm.group(1))
    return out


def fill_candidates(data, tpl):
    """빌더가 우선순위대로 넘긴 채움 블록을 «켤 수 있는 것» 으로 추린다.

    켜는 방법은 **섹션**이다 — 판형이 `<!-- SECTION:fill-xxx -->` 로 자리를 내주고,
    렌더러가 `sections` 에 그 이름을 넣으면 켜진다.

    최소 높이는 **규격(summary-spec.md §4-1)이 정본**이고, 없으면 블록의 `min_mm`
    을 쓴다. 둘 다 없으면 그 블록은 뺀다 — 높이를 짐작해서 골랐다가 한 장을 넘기면
    아무것도 안 넣은 것만 못하다. 무엇이 없어서 뺐는지는 줄로 남긴다."""
    heights = spec_heights()
    out, why = [], []
    for i, b in enumerate(data.get("fill_blocks") or []):
        if not isinstance(b, dict):
            continue
        name = str(b.get("key") or b.get("title") or i)
        sec = b.get("section") or b.get("key")
        if not sec or ("<!-- SECTION:%s -->" % sec) not in tpl:
            why.append("«%s» 켤 자리 없음 (판형에 SECTION:%s 가 없습니다 — 블록에 section 을 적어 주세요)"
                       % (name, sec or "?"))
            continue
        mm = heights.get(sec)
        if mm is None:
            try:
                mm = float(b.get("min_mm"))
            except (TypeError, ValueError):
                mm = None
        if not mm or mm <= 0:
            why.append("«%s» 최소 높이 없음 (summary-spec.md §4-1 실측표나 블록의 min_mm)" % name)
            continue
        out.append(dict(b, section=sec, min_mm=float(mm), name=name))
    return out, why


def pick_fill(cands, room_mm):
    """남은 높이에 **들어갈 만큼만** 고른다. 우선순위 차례 그대로."""
    used, picked = 0.0, []
    for b in cands:
        if used + b["min_mm"] > room_mm:
            break
        picked.append(b)
        used += b["min_mm"]
    return picked, used


# ---------------------------------------------------------------- 브랜딩
FIG_MAX_MB = 3.0


def embed_figures(data):
    """`killer[].figures[].src` 를 **종이에 심는다** — 파일 길을 data URI 로 바꾼다.

    HTML 한 장으로 돌아다니는 산출물이라 바깥 파일을 가리키면 남에게 보냈을 때
    그림만 빈다. 글꼴·로고와 같은 규칙이다.

    없는 파일은 **막는다.** 그림이 빠진 채로 조용히 나가는 쪽이 더 나쁘다 —
    과학은 그림이 곧 문항이라 한 장만 비어도 그 문항이 뜻을 잃는다.
    """
    n = 0
    for k in data.get("killer") or []:
        for f in k.get("figures") or []:
            src = f.get("src") or ""
            if src.startswith("data:"):
                continue
            if not os.path.exists(src):
                raise RenderError(
                    "문항 그림이 없습니다: %s (%d번 «%s»)\n"
                    "  MD 의 ![…](…) 가 가리키는 자리에 파일이 있어야 합니다."
                    % (src, k.get("no", 0), f.get("alt", "")))
            mb = os.path.getsize(src) / 1048576.0
            if mb > FIG_MAX_MB:
                raise RenderError("문항 그림이 너무 큽니다: %s (%.1fMB · 한도 %.1fMB)"
                                  % (src, mb, FIG_MAX_MB))
            mime = mimetypes.guess_type(src)[0] or "image/png"
            with open(src, "rb") as fh:
                f["src"] = "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode())
            n += 1
    return n


def logo_block(brand):
    path = brand.get("logo_path")
    name = brand.get("academy") or "공감에듀"
    if not path:
        return '<div class="cover-brand-text">%s</div>' % name
    if not os.path.exists(path):
        raise RenderError("로고 파일이 없습니다: %s" % path)
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    img = '<img src="data:%s;base64,%s" alt="%s" class="cover-logo">' % (mime, b64, name)
    # 밝은 배경 로고는 흰 박스로 감싼다. 어두운 로고는 흰색으로 반전한다.
    if (brand.get("logo_bg") or "light") == "light":
        return '<div class="cover-logo-box">%s</div>' % img
    return '<div class="cover-logo-plain">%s</div>' % img


def cached_subset(src, chars, sources=None):
    """서브셋 결과를 임시폴더에 재워 둔다 — 같은 폰트·같은 글자면 다시 깎지 않는다.

    2.1MB woff2 두 벌을 깎아 brotli 로 다시 누르는 데 PC 가 바쁘면 수십 초가 든다.
    한 번 렌더에 두 벌, 게이트 한 바퀴에 일곱 번 렌더면 그것만으로 몇 분이다.

    열쇠에 **원본 폰트의 크기·수정시각과 글자 집합**이 들어간다 — 폰트를 바꾸거나
    글자가 하나만 달라져도 열쇠가 달라지므로 낡은 것이 잘못 쓰일 수 없다."""
    import hashlib
    import subset_font

    st = os.stat(src)
    key = hashlib.sha1(("%s|%d|%d|%s" % (os.path.basename(src), st.st_size,
                                         int(st.st_mtime), "".join(sorted(chars)))
                        ).encode("utf-8")).hexdigest()
    box = os.path.join(tempfile.gettempdir(), "gonggam-report-fontcache")
    hit = os.path.join(box, key + ".woff2")
    if os.path.exists(hit):
        with open(hit, "rb") as f:
            data = f.read()
        if data:
            return data, "%.0fKB (재사용)" % (len(data) / 1e3)

    data, note = subset_font.build(src, chars, sources)
    try:
        os.makedirs(box, exist_ok=True)
        tmp = hit + ".%d.part" % os.getpid()        # 여럿이 같이 돌아도 반쪽 파일이 안 남는다
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, hit)
    except OSError:
        pass                                        # 재워 두지 못해도 렌더는 옳다
    return data, note


def font_face_css(chars, sources=None):
    """동봉 woff2 만 쓴다. 없으면 렌더를 막는다 (조용한 대체 금지).
    쓰인 글자만 남겨서 박는다 — 전체를 담으면 산출물이 5MB 를 넘어 메일에 못 붙인다.

    숫자 0~9 는 **언제나** 넣는다. 1패스(«00»)와 2패스(«13») 의 폰트가 달라지면
    두 패스의 조판이 달라질 수 있기 때문이다 — 같은 폰트로 두 번 그려야 쪽수가 안 흔들린다.

    굵기는 셋이다 — 400 본문 · 700 강조 · **900 제목·큰 숫자.**
    900 이 없으면 브라우저가 말없이 700 으로 떨어뜨린다. 그러면 원장님 눈에는
    «굵기가 반영 안 된» 보고서로 보인다. 그래서 **하나라도 없으면 막는다.**

    sources 는 «없는 글자가 어디에 있나» 를 말하기 위한 것이다 (판형·테마·데이터).
    없어도 막는 판단은 같다 — 자리를 못 짚을 뿐이다. references/glyphs.md."""
    import subset_font

    chars = set(chars) | set("0123456789")
    need = ["NotoSansKR-400.woff2", "NotoSansKR-700.woff2", "NotoSansKR-900.woff2"]
    missing = [n for n in need if not os.path.exists(os.path.join(FONTS, n))]
    if missing:
        raise RenderError(
            "동봉 폰트가 없습니다: %s\n"
            "  → %s 에 넣어 주세요. 시스템 폰트로 대체하지 않습니다 "
            "(PC 마다 글자폭이 달라져 쪽수가 달라집니다).\n"
            "  900(Black)이 빠졌다면 700 으로 물러서지 않습니다 — 굵기가 조용히 가늘어지는 쪽이 더 나쁩니다."
            % (", ".join(missing), FONTS)
        )
    out, notes = [], []
    for n in need:
        weight = 900 if "900" in n else (700 if "700" in n else 400)
        src = os.path.join(FONTS, n)
        try:
            data, note = cached_subset(src, chars, sources)
        except subset_font.FontError as e:
            raise RenderError(str(e))
        notes.append("%d %s" % (weight, note))
        b64 = base64.b64encode(data).decode()
        out.append(
            "@font-face{font-family:'ReportKR';font-weight:%d;font-style:normal;"
            "font-display:block;src:url(data:font/woff2;base64,%s) format('woff2');}" % (weight, b64)
        )
    return "\n".join(out), notes


def theme_css(name):
    p = os.path.join(THEMES, "%s.css" % name)
    if not os.path.exists(p):
        have = sorted(x[:-4] for x in os.listdir(THEMES) if x.endswith(".css")) if os.path.isdir(THEMES) else []
        raise RenderError("그런 테마가 없습니다: %s (있는 것: %s)" % (name, ", ".join(have)))
    return io.open(p, encoding="utf-8").read()


# ---------------------------------------------------------------- 본체
LEFT_RE = re.compile(r"\{\{[^}]{0,80}\}\}")


def derive(data):
    """계산은 전부 여기서 한다. Claude 는 산수를 하지 않는다.

    ⛔ 여기서 목록을 «한 장에 N개» 로 쪼개지 않는다. 그 N 은 추측이었고,
       내용이 길어지면 한 장이 두 장으로 넘쳐 쪽수가 통째로 어긋났다.
       쪽 나눔은 브라우저가 하고, 쪽번호는 PDF 를 재서 넣는다."""
    # 막대 너비 — 가장 큰 배점을 100%로 잡는다
    for key in ("types", "chapters"):
        rows = data.get(key) or []
        if not rows:
            continue
        top = max(float(r.get("points") or 0) for r in rows) or 1.0
        for r in rows:
            r["width"] = round(float(r.get("points") or 0) / top * 100)

    # 난이도 5칸 — 문항에서 직접 센다. 따로 적어 둔 숫자를 믿지 않는다
    items = data.get("items") or []
    if items:
        counts = {}
        for i in items:
            counts[i.get("difficulty")] = counts.get(i.get("difficulty"), 0) + 1
        d = data.setdefault("difficulty", {})
        d["bins"] = [{"label": k, "count": counts.get(k, 0)} for k in ("상", "중상", "중", "중하", "하")]

    derive_killers(data)
    return data


# 킬러문항 카드에서 «있을 때만 그리는» 상자들 — (내용 필드, 상자 이름)
KILLER_BOXES = (("excerpt", "excerpt_box"),)
# givens = 〈보기〉 — 기호(ⓐⓑⓒ)가 글에 이미 들어 있다. 템플릿이 다시 매기지 않는다:
# 선지와 오답 근거가 **그 기호로** 보기를 가리키므로 번호를 새로 매기면 말이 어긋난다.
KILLER_LIST_BOXES = (("givens", "given_box"), ("choices", "choice_box"),
                     ("conditions", "cond_box"), ("wrong_reasons", "wrong_box"))


def derive_killers(data):
    """킬러문항 카드를 «있는 것만» 그릴 수 있게 다듬는다.

    템플릿 지시자에는 «만약» 이 없다 — SECTION 과 REPEAT 뿐이다. 그래서 조건부로
    그려야 하는 상자는 **한 칸짜리 목록**으로 만들어 둔다. 내용이 없으면 빈 목록이라
    상자째 안 그려진다. 「선지가 없는 서술형에 빈 선지 상자」 같은 것이 안 생긴다.

    객관식은 선지·정답 번호를, 서술형은 조건·모범답안을 쓴다. 갈래는 `kind` 가 정한다
    (report_build.py 가 넣어 준다. 없으면 객관식으로 본다)."""
    for k in data.get("killer") or []:
        if not isinstance(k, dict):
            continue
        k.setdefault("kind", "객관식")
        essay = str(k["kind"]) == "서술형"
        k["answer_label"] = "모범답안" if essay else "정답"
        # 객관식 정답은 «3» 한 글자라 제목 옆 배지로 좋다. 서술형 모범답안은 한 문장이라
        # 배지에 넣으면 제목을 밀어내고 두 줄로 접힌다 — 그래서 제 상자를 준다.
        k.setdefault("answer", "")
        has_answer = bool(str(k.get("answer") or "").strip())
        k["answer_box"] = [{}] if has_answer and not essay else []
        k["answer_block_box"] = [{}] if has_answer and essay else []
        for field, box in KILLER_BOXES:
            k.setdefault(field, "")
            k[box] = [{}] if str(k.get(field) or "").strip() else []
        for field, box in KILLER_LIST_BOXES:
            k.setdefault(field, [])
            k[box] = [{}] if k.get(field) else []
        for field in ("steps", "concepts"):
            k.setdefault(field, [])            # 옛 표본에는 없을 수 있다
    return data


def template_path(summary):
    if not summary:
        return TEMPLATE
    if not os.path.exists(TEMPLATE_SUMMARY):
        raise RenderError(
            "요약본 템플릿이 아직 없습니다: %s\n"
            "  → --summary 는 assets/template_summary.html 을 씁니다. 그 파일을 먼저 두세요.\n"
            "  (없다고 기본 템플릿으로 슬쩍 대체하지 않습니다 — 요약본을 시켰는데 전체본이\n"
            "   나가는 편이 더 나쁩니다.)" % TEMPLATE_SUMMARY
        )
    return TEMPLATE_SUMMARY


def to_pdf(html_path, pdf_path):
    import render_pdf
    from render_pdf import html_to_pdf
    # 쪽수를 맞추는 중간 패스에서는 «판형이 찍은 번호가 낡았다» 는 알림을 끈다 —
    # 중간에는 낡은 것이 정상이고, 맞는지는 이 파일의 수렴 검사와 게이트가 본다.
    render_pdf.WARN_ODD_STAMPS = False
    try:
        html_to_pdf(html_path, pdf_path)
    except SystemExit as e:
        raise RenderError(
            "쪽수를 재려면 PDF 를 만들어야 하는데 실패했습니다.\n  %s" % e)


def render(data, out_dir, internal=False, summary=False, src=None):
    # src 는 report.json 의 경로다. 조판에는 쓰이지 않는다 — 폰트에 없는 글자를 만났을 때
    # «데이터 몇 번째 줄» 까지 짚어 주기 위해서만 쓴다.
    data = derive(data)
    nfig = embed_figures(data)
    brand = data.get("brand") or {}
    sections = data.get("sections")
    if not sections:
        raise RenderError("report.json 에 sections 가 없습니다.")

    tpl = io.open(template_path(summary), encoding="utf-8").read()

    # 단순 치환 — 남은 {{a.b}} 를 데이터에서 찾는다
    def sub(m):
        key = m.group(1)
        if key in KEEP_KEYS:
            return m.group(0)
        try:
            return esc(as_text(lookup(data, key)))
        except KeyError:
            return m.group(0)

    def expand(selected):
        """고른 채움 블록까지 얹어 «뼈대» 를 만든다. 채움이 바뀌면 다시 펼쳐야 한다.

        켜는 방법은 두 가지를 다 지원한다 — 판형이 섹션(`SECTION:fill-xxx`)으로 자리를
        내주면 `sections` 에 이름을 넣고, 목록(`REPEAT:fill_on`)을 쓰면 목록으로 준다."""
        data["fill_on"] = list(selected)
        data["fill_box"] = [{}] if selected else []
        on = list(sections) + [b["section"] for b in selected
                               if b.get("section") and b["section"] not in sections]
        html = apply_internal(tpl, internal)
        html, kept = apply_sections(html, on)
        html = apply_repeats(html, data, strip_internal=not internal)
        html = ROW_RE.sub(sub, html)
        html = html.replace("{{THEME_CSS}}", theme_css(brand.get("theme") or "clean"))
        html = html.replace("{{COVER_LOGO_BLOCK}}", logo_block(brand))
        html = number_sections(html)
        skeleton, anchors = stage_page_marks(html)
        if not anchors:
            raise RenderError("템플릿에 {{PAGE_NUM}} 이 하나도 없습니다 — 쪽번호를 박을 자리가 없습니다.")
        return skeleton, anchors, kept

    # 채움 후보 — 빌더가 우선순위대로 넘긴다. 최소 높이는 규격·데이터가 말한다
    cands, why_not = fill_candidates(data, tpl) if summary else ([], [])
    for line in why_not:
        print("[채움] 뺌 — %s" % line)

    def usable(block, others):
        """그 블록을 켜면 **정말 펼쳐지는가**. 데이터가 없으면 렌더가 멈추므로 미리 본다."""
        try:
            expand(others + [block])
            return True
        except RenderError as e:
            print("[채움] 뺌 — «%s» 를 켜면 펼쳐지지 않습니다: %s"
                  % (block["name"], str(e).splitlines()[0]))
            return False

    cands = [c for i, c in enumerate(cands) if usable(c, [])]
    can_fill = bool(cands)

    skeleton, anchors, kept = expand([])

    # 폰트는 한 번만 만들어 모든 패스가 **같은 글자폭**을 쓰게 한다.
    # 채움 블록의 글자까지 미리 담는다 — 2패스에서 블록이 켜져도 두부가 안 난다.
    import subset_font
    painted = paint_marks(skeleton, anchors, None, None)
    chars = subset_font.chars_of(painted)
    if can_fill:
        full, full_anchors, _ = expand(cands)
        painted = paint_marks(full, full_anchors, None, None)
        chars = chars | subset_font.chars_of(painted)
        skeleton, anchors, kept = expand([])

    # 폰트에 없는 글자가 나오면 «어디에 있는지» 를 말해야 한다 — 판형인지 테마인지
    # 데이터인지. 조판 결과만 보면 셋이 이미 한 덩어리라 원인을 못 짚는다.
    # 조판 결과는 **앞의 셋에서 못 찾았을 때만** 쓰는 마지막 수단이다.
    font_src = [subset_font.source("판형", template_path(summary), tpl),
                subset_font.source("테마", os.path.join(THEMES, "%s.css" % (brand.get("theme") or "clean")))]
    if src and os.path.exists(src):
        font_src.append(subset_font.source("데이터", src))
    font_src.append(subset_font.source("조판 결과", "(조판된 HTML)", painted,
                                       kind="html", fallback=True))
    font_css, font_notes = font_face_css(chars, font_src)

    def build(skeleton, anchors, pages, total):
        out = paint_marks(skeleton, anchors, pages, total)
        out = out.replace("{{FONT_CSS}}", font_css)
        # 남은 플레이스홀더가 있으면 렌더를 실패시킨다 — 빈 칸이 인쇄되는 것보다 낫다
        left = sorted(set(LEFT_RE.findall(out)))
        if left:
            raise RenderError(
                "채워지지 않은 자리가 %d 개 남았습니다:\n  %s" % (len(left), "\n  ".join(left[:20]))
            )
        return out

    os.makedirs(out_dir, exist_ok=True)
    meta = data.get("meta") or {}
    from outname import outname                      # 이름은 한 곳에서만 짓는다
    # 꼬리칸 어휘는 공용 규격(gonggam-material-studio/assets/filename_check.py)이 정한다.
    # 여기서 낱말을 지어내지 않는다 — 규격이 두 벌이 되면 반드시 갈라진다.
    # 꼬리칸은 **하나**다: 요약본 · 상세본 · 배포본 · 내부본 중 하나 (분량과 종은 다른 축이다).
    # «요약본» 이라는 낱말 자체가 규격이다 — 게이트가 이 이름으로 요약본을 알아보고
    # 「A4 한 장을 넘기면 차단」을 건다. 줄여 적으면 그 검사를 피해 가게 된다.
    tail = ["요약본"] if summary else ["내부본" if internal else "배포본"]
    name = outname(
        "기출분석리포트", meta.get("grade", "H1"), meta.get("school", "학교"),
        meta.get("term", ""), meta.get("subject", "과목"),
        tail=tail, ext="html",
        brand=brand.get("academy") or "공감에듀",
    )
    path = os.path.join(out_dir, name)
    pdf_path = path[:-5] + ".pdf"

    def paginate(skeleton, anchors, seed):
        """«쓴 쪽번호 == 잰 쪽번호» 가 될 때까지 재면서 수렴시킨다."""
        written = seed                                # 처음에는 고정폭 자리표시자
        for step in range(1, MAX_PASSES + 1):
            t0 = time.time()
            with io.open(path, "w", encoding="utf-8") as f:   # 닫고 나서 크롬에 넘긴다
                f.write(build(skeleton, anchors, *(written or (None, None))))
            to_pdf(path, pdf_path)
            total, pages = measure_pdf(pdf_path, anchors)
            if written == (pages, total):
                print("[쪽수] %d패스에서 같은 값이 나왔습니다 — 수렴 (%.1f초)"
                      % (step, time.time() - t0))
                return total, pages
            print("[쪽수] %d패스 — 총 %d쪽, 섹션 시작쪽 %s (%.1f초)"
                  % (step, total, ", ".join(str(p) for p in pages), time.time() - t0))
            written = (pages, total)

            # 쪽 표시가 **종이에 안 나오는** 판형(자리표시자가 PDF 글에 없다)이면
            # 숫자를 넣어도 조판이 바뀔 수 없다 — 종이의 쪽번호는 도장이 이미 실측으로 찍었다.
            # 그러면 두 번 그릴 이유가 없다. 크롬 한 벌이 통째로 절약된다.
            #
            # **자리표시자로 그린 패스에서만** 이 판단을 한다. 앞 바퀴의 값을 물려받아
            # 시작한 패스는 «00 / 00» 이 애초에 없으므로, 그것을 «안 나오는 판형» 으로
            # 읽으면 낡은 숫자가 찍힌 PDF 를 최종본으로 믿게 된다 (실제로 «1 / 2» 가
            # 한 장짜리 요약본에 찍혔다).
            if step == 1 and seed is None and not mark_is_printed(pdf_path):
                with io.open(path, "w", encoding="utf-8") as f:
                    f.write(build(skeleton, anchors, pages, total))
                print("       쪽 표시가 인쇄에 나오지 않는 판형이라 한 벌만 그렸습니다 "
                      "(종이 쪽번호는 PDF 실측 도장).")
                return total, pages
        raise RenderError(
            "쪽번호가 %d 패스 안에 수렴하지 않았습니다.\n"
            "  → 쪽번호를 넣자 조판이 밀리는 자리가 있다는 뜻입니다. "
            "쪽번호 칸이 흐름 밖(absolute)인지 확인하세요." % MAX_PASSES
        )

    # ── 쪽수를 맞추고, 요약본이면 «남은 높이» 를 재서 채운다 ──
    # 한 장은 절대 안 깨진다. 채우려다 2쪽이 되면 아무것도 안 넣은 것만 못하다.
    selected, seed, room, used, fill_note = [], None, None, 0.0, ""
    for round_no in range(1, MAX_FILL_ROUNDS + 1):
        total, pages = paginate(skeleton, anchors, seed)
        if not can_fill:
            break
        seed = (pages, total)                         # 다음 바퀴는 아는 값에서 시작한다

        if summary and total > 1 and selected:
            dropped = selected.pop()                  # 넘쳤다 — 마지막 블록을 빼고 다시
            print("[채움] 한 장을 넘겨 «%s» 를 뺍니다 (남은 블록 %d개)"
                  % (dropped.get("title") or dropped.get("key") or "블록", len(selected)))
            skeleton, anchors, kept = expand(selected)
            continue

        if room is None:                              # 1패스: 빈 자리를 잰다
            html_now = io.open(path, encoding="utf-8").read()
            room, band_top = blank_band(pdf_path, html_now)
            if room is None:
                print("[채움] 남은 높이를 잴 수 없어 채우지 않았습니다 "
                      "(판형에 @page 여백 선언이 없습니다)")
                break
            print("[채움] 빈 띠 %.1fmm (종이 위에서 %.0fmm 자리)" % (room, band_top))
            selected, used = pick_fill(cands, room)
            if not selected:
                print("[채움] 남은 %.1fmm 에 들어갈 블록이 없어 빈 채로 둡니다 "
                      "(가장 작은 블록 %.1fmm) — 억지로 늘리지 않습니다"
                      % (room, min(c["min_mm"] for c in cands)))
                break
            print("[채움] 남은 %.1fmm — %s 를 넣고 다시 그립니다"
                  % (room, " · ".join(str(b.get("title") or b.get("key")) for b in selected)))
            skeleton, anchors, kept = expand(selected)
            continue

        # 채우고 다시 그린 뒤: 정말 들어갔나
        after = blank_mm(pdf_path, io.open(path, encoding="utf-8").read())
        if selected and after is not None and room is not None and after > room - 1.0:
            print("[주의] 고른 블록이 종이에 반영되지 않았습니다 — 판형의 fill_on 자리를 확인하세요")
        if selected:
            used = sum(b["min_mm"] for b in selected)     # 빼고 남은 것으로 다시 센다
            fill_note = ("채움: %s (남은 %.1fmm 중 %.1fmm 사용%s)"
                         % (" · ".join(str(b.get("title") or b.get("key")) for b in selected),
                            room, used,
                            ", 남김 %.1fmm" % after if after is not None else ""))
        break

    html = io.open(path, encoding="utf-8").read()
    print("[렌더] %s" % path)
    print("       섹션 %d개: %s" % (len(kept), " · ".join(kept)))
    if nfig:
        print("       문항 그림 %d장 심음" % nfig)
    print("       총 %d 페이지 — PDF 실측 · 테마 %s · %s%s"
          % (total, brand.get("theme") or "clean", tail[0],
             " (내부 칸 포함)" if internal and summary else ""))
    print("       섹션 시작쪽: %s" % ", ".join(
        "%s→%d쪽" % (a.strip(), p) for a, p in zip(anchors, pages)))
    if fill_note:
        print("       %s" % fill_note)
    print("       폰트 %s · HTML %.1fMB" % (" / ".join(font_notes), len(html.encode("utf-8")) / 1e6))
    print("       PDF %s" % pdf_path)
    return path


def list_themes():
    """있는 테마를 세어서 말한다. 사람이 세지 않는다 —
    문진 표(asking.md Q3)와 실제 파일이 어긋나면 그 테마는
    «파일은 있는데 고를 길이 없는» 상태가 된다."""
    have = sorted(x[:-4] for x in os.listdir(THEMES) if x.endswith(".css"))
    print("테마 %d개: %s" % (len(have), " · ".join(have)))
    print("고르는 법 — report.json 의 brand.theme, 또는 --theme <이름>")
    return have


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    theme = next((f.split("=", 1)[1] for f in flags if f.startswith("--theme=")), None)
    flags = [f for f in flags if not f.startswith("--theme=")]
    if "--list-themes" in flags:
        list_themes()
        return
    unknown = [f for f in flags if f not in ("--internal", "--summary")]
    if unknown:
        print("모르는 옵션입니다: %s" % " ".join(unknown), file=sys.stderr)
        print(__doc__)
        sys.exit(1)
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    data = json.load(io.open(args[0], encoding="utf-8"))
    if theme:
        data.setdefault("brand", {})["theme"] = theme
    try:
        render(data, args[1], internal="--internal" in flags, summary="--summary" in flags,
               src=args[0])
    except RenderError as e:
        print("\n[렌더 실패] %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
