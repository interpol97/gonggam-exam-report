#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.json → **HTML 만** (PDF 로 굽지 않는다). 디자인을 눈으로 고를 때 쓴다.

    python preview.py report.json out.html [--summary] [--theme=nelt] [--fill]

왜 따로 있나 —
    render_report.py 는 쪽수를 «재려고» PDF 를 두 번 굽는다. 한 벌에 57초다.
    그 값은 「A4 한 장인가」를 알아야 할 때만 있다. 아직 **어떤 모양으로 갈지**
    안 정했는데 매번 굽는 것은 낭비다. 그래서 이 파일은 조판만 하고 멈춘다 —
    한 벌에 3초 안팎.

이것으로 «확인했다» 고 말하지 않는다
    쪽수·채움·쪽번호·폰트 서브셋이 전부 빠져 있다. 모양을 고르는 데만 쓰고,
    고른 뒤에는 반드시 render_report.py + gate_check.py 를 태운다.
"""

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import render_report as R          # noqa: E402

# 미리보기는 동봉 폰트를 서브셋하지 않는다 — 그 과정이 가장 오래 걸리고,
# 폰트에 없는 글자 하나로 막히면 «모양을 보는» 일 자체가 안 된다.
PREVIEW_FONT = """
@font-face{font-family:'ReportKR';
  src:local('Pretendard'),local('Pretendard Variable'),local('맑은 고딕'),local('Malgun Gothic');
  font-weight:400 900}
"""


def build(report_path, summary=False, theme=None, fill=False):
    data = json.load(io.open(report_path, encoding="utf-8"))
    if theme:
        data.setdefault("brand", {})["theme"] = theme
    data = R.derive(data)
    brand = data.get("brand") or {}
    sections = list(data.get("sections") or [])
    if not sections:
        raise SystemExit("report.json 에 sections 가 없습니다.")

    # 채움 블록 — 미리보기에서는 높이를 재지 않으므로 «켜 달라» 고 할 때만 켠다.
    blocks = data.get("fill_blocks") or [] if fill else []
    data["fill_on"] = blocks
    data["fill_box"] = [{}] if blocks else []
    sections += [b["section"] for b in blocks
                 if b.get("section") and b["section"] not in sections]

    def sub(m):
        key = m.group(1)
        if key in R.KEEP_KEYS:
            return m.group(0)
        try:
            return R.esc(R.as_text(R.lookup(data, key)))
        except KeyError:
            return m.group(0)

    tpl = io.open(R.template_path(summary), encoding="utf-8").read()
    html = R.apply_internal(tpl, False)
    html, _ = R.apply_sections(html, sections)
    html = R.apply_repeats(html, data, strip_internal=True)
    html = R.ROW_RE.sub(sub, html)
    html = html.replace("{{THEME_CSS}}", R.theme_css(brand.get("theme") or "clean"))
    html = html.replace("{{COVER_LOGO_BLOCK}}", R.logo_block(brand))
    html = R.number_sections(html)
    html = html.replace("{{FONT_CSS}}", PREVIEW_FONT)
    # 쪽번호는 재야 나온다. 미리보기에서는 재지 않으므로 자리만 표시한다.
    html = html.replace("{{PAGE_NUM}}", "–").replace("{{TOTAL_PAGES}}", "–")

    left = R.LEFT_RE.findall(html)
    if left:
        raise SystemExit("채워지지 않은 자리: %s" % " ".join(sorted(set(left))[:6]))
    return html


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    theme = next((f.split("=", 1)[1] for f in flags if f.startswith("--theme=")), None)
    html = build(args[0], summary="--summary" in flags, theme=theme, fill="--fill" in flags)
    io.open(args[1], "w", encoding="utf-8").write(html)
    print("%s  (%.0fKB · 테마 %s)" % (args[1], len(html.encode("utf-8")) / 1024,
                                      theme or "report.json 의 값"))


if __name__ == "__main__":
    main()
