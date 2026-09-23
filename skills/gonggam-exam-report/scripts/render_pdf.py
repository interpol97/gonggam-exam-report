#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
리포트 HTML → PDF (헤드리스 크롬) + 장마다 쪽번호 도장

    python render_pdf.py 리포트.html 리포트.pdf
    python render_pdf.py 리포트.html 리포트.pdf --no-stamp   (도장 없이)

Windows·리눅스 양쪽에서 크롬/엣지를 찾는다. 옛 스킬은 /root·/usr/bin 만 뒤져서
원장님 PC 에서 그냥 실패했다.

Paged.js 를 끼우지 않는다 — 비동기 대기라는 사고 지점만 새로 생긴다.
폰트는 HTML 안에 base64 로 박혀 있으므로 file:// 로도 CORS 문제가 없다.

쪽번호를 왜 «찍어» 넣나
────────────────────────────────────────────────────────────
옛 방식은 HTML 에 `.page` 카드를 한 장씩 만들어 그 안에 쪽번호를 박았다. 그러려면
«한 장에 몇 줄이 들어가나» 를 추측해야 했고, 내용이 길어지면 카드 하나가 두 장으로
넘쳐 쪽번호가 통째로 어긋났다(12쪽 표기 / 13쪽 인쇄).

지금은 내용이 그냥 흐른다. 대신 **다 인쇄된 PDF 를 열어** 몇 장인지 세고, 장마다
같은 자리에 「N / M 페이지」를 찍는다. 조판이 끝난 뒤에 세므로 어긋날 수가 없다.
CSS 로는 못 하는 일이다 — 브라우저는 «지금 몇 장째인가» 를 내용에 알려주지 않는다.

표지는 찍지 않는다. HTML 에 `<div class="cover">` 가 있으면 1장이 표지다.
이미 쪽번호가 있는 장(요약본처럼 스스로 찍는 판형)도 건드리지 않는다.
"""

import glob
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
SKILL = os.path.dirname(HERE)
FONTS = os.path.join(SKILL, "assets", "fonts")
STAMP_FONT = os.path.join(FONTS, "NotoSansKR-400.woff2")

STAMP_TEXT = "%d / %d 페이지"
STAMP_CHARS = "0123456789 /페이지"
STAMP_SIZE = 8.5
STAMP_COLOR = (0.42, 0.45, 0.50)
STAMP_RIGHT_PT = 26.0          # 오른쪽 여백 (A4 9mm 여백 안쪽)
STAMP_BOTTOM_PT = 18.0         # 아래 여백
HAS_STAMP = re.compile(r"\d+\s*/\s*\d+\s*(?:페이지|쪽)")
# 크롬을 기다려 주는 시간. 바쁜 PC 에서는 한 벌 뽑는 데 몇 분이 걸린다 — 넉넉히 준다.
BROWSER_TIMEOUT = float(os.environ.get("GONGGAM_PDF_TIMEOUT") or 300)
# 판형이 스스로 찍은 쪽번호가 실제 장과 다를 때 알릴 것인가.
# 이 파일을 직접 부르면(=최종 산출물) 알리고, render_report.py 가 쪽수를 맞추는 **중간
# 패스**에서는 끈다 — 중간에는 낡은 숫자가 찍혀 있는 것이 정상이고, 마지막에 맞춰진다.
WARN_ODD_STAMPS = True

CANDIDATES = [
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/opt/google/chrome/chrome",
    "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
    os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
]


def find_browser():
    env = os.environ.get("GONGGAM_CHROME")
    if env and os.path.exists(env):
        return env
    for pat in CANDIDATES:
        if "*" in pat:
            hit = sorted(glob.glob(pat))
            if hit:
                return hit[0]
        elif os.path.exists(pat):
            return pat
    return None


def to_url(path):
    path = os.path.abspath(path).replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    return "file://" + path


# ---------------------------------------------------------------- 쪽번호 도장
_STAMP_TTF = []                # 한 프로세스에서 한 번만 깎는다 (렌더 한 벌에 두 번 부른다)


def stamp_font_bytes():
    """도장에 쓸 글자만 남긴 TTF. 동봉 woff2 에서 깎아 쓴다 —
    시스템 폰트를 부르지 않는다(PC 마다 글자폭이 달라진다)."""
    if _STAMP_TTF:
        return _STAMP_TTF[0]
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(STAMP_FONT)
    opts = subset.Options()
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=[ord(c) for c in STAMP_CHARS])
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = None                     # woff2 로 받아 TTF 로 낸다
    font.save(buf)
    font.close()
    _STAMP_TTF.append(buf.getvalue())
    return _STAMP_TTF[0]


def stamp_pages(pdf_path, skip_first):
    """다 그려진 PDF 를 열어 장 수를 세고, 장마다 같은 자리에 쪽번호를 찍는다."""
    try:
        import fitz                        # PyMuPDF
    except ImportError:
        raise SystemExit(
            "PyMuPDF 가 없어 쪽번호를 찍을 수 없습니다.\n"
            "  → pip install pymupdf\n"
            "  쪽번호 없는 PDF 를 조용히 내보내지는 않습니다 (게이트가 어차피 막습니다).\n"
            "  도장 없이 뽑아야 한다면 --no-stamp 를 주세요."
        )
    if not os.path.exists(STAMP_FONT):
        raise SystemExit("도장용 동봉 폰트가 없습니다: %s" % STAMP_FONT)

    ttf = stamp_font_bytes()
    font = fitz.Font(fontbuffer=ttf)
    doc = fitz.open(pdf_path)
    n = doc.page_count
    done, kept = 0, []
    for i, page in enumerate(doc):
        if i == 0 and skip_first:
            kept.append(1)
            continue
        if HAS_STAMP.search(page.get_text()):      # 스스로 찍는 판형은 건드리지 않는다
            kept.append(i + 1)
            continue
        # 크롬이 남긴 그래픽 상태(축소·상하반전)를 물려받지 않게 기존 내용을 q/Q 로 감싼다.
        # 이걸 빼먹었더니 도장이 **왼쪽 위 구석에 2pt 크기로** 찍혔다. 게이트는
        # 글자가 «있다»만 보고 통과시켰다 — 그래서 아래에서 자리까지 직접 확인한다.
        page.wrap_contents()
        text = STAMP_TEXT % (i + 1, n)
        w = font.text_length(text, fontsize=STAMP_SIZE)
        x = page.rect.width - STAMP_RIGHT_PT - w
        y = page.rect.height - STAMP_BOTTOM_PT
        tw = fitz.TextWriter(page.rect, color=STAMP_COLOR)
        tw.append(fitz.Point(x, y), text, font=font, fontsize=STAMP_SIZE)
        tw.write_text(page)
        done += 1
    tmp = pdf_path + ".stamp.tmp"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, pdf_path)
    verify_stamps(pdf_path, kept)
    print("[쪽번호] %d/%d 장에 찍음%s"
          % (done, n, " (건너뜀: %s장)" % ", ".join(str(k) for k in kept) if kept else ""))
    return n


def verify_stamps(pdf_path, kept):
    """찍은 뒤에 **다시 열어서** 자리를 확인한다 — 오른쪽 아래 여백에 제 크기로 앉았나.

    «글자가 있다» 만 보는 검사는 이 사고를 통과시킨다. 자리를 재는 검사만 막는다."""
    import fitz

    doc = fitz.open(pdf_path)
    n = doc.page_count
    bad, odd = [], []
    for i, page in enumerate(doc):
        if (i + 1) in kept:
            # 스스로 찍는 판형이라 건너뛴 장. 그 장이 «제 번호» 를 달고 있는지는 본다 —
            # 표지(1장)는 원래 번호가 없다. 어긋나면 알린다(막는 것은 게이트의 몫).
            got = HAS_STAMP.findall(page.get_text())
            nums = re.findall(r"(\d+)\s*/\s*(\d+)", " ".join(got) if got else "")
            # «00 / 00» 은 1패스의 자리표시자다 — 아직 숫자를 안 넣은 것이라 사고가 아니다.
            # 쪽번호는 1부터이므로 0 이 보이면 자리표시자로 본다.
            if nums and int(nums[0][0]) and int(nums[0][1]) \
                    and (int(nums[0][0]) != i + 1 or int(nums[0][1]) != n):
                odd.append("p%d 에 «%s / %s» 가 찍혀 있습니다"
                           % (i + 1, nums[0][0], nums[0][1]))
            continue
        W, H = page.rect.width, page.rect.height
        hit = None
        for b in page.get_text("blocks"):
            if HAS_STAMP.match((b[4] or "").strip()):
                hit = b
                break
        if hit is None:
            bad.append("p%d 에 쪽번호가 없습니다" % (i + 1))
            continue
        x0, y0, x1, y1 = hit[:4]
        if x1 < W * 0.6 or y0 < H * 0.9 or (y1 - y0) < STAMP_SIZE * 0.6:
            bad.append("p%d 쪽번호가 엉뚱한 자리·크기입니다 (%.0f,%.0f)-(%.0f,%.0f)"
                       % (i + 1, x0, y0, x1, y1))
    doc.close()
    if odd and WARN_ODD_STAMPS:
        print("[주의] 판형이 스스로 찍은 쪽번호가 실제 장과 다릅니다 — %s\n"
              "       (게이트의 «쪽번호 장마다 일치» 가 막습니다.)" % " / ".join(odd[:3]))
    if bad:
        raise SystemExit(
            "쪽번호 도장이 제자리에 앉지 않았습니다:\n  %s\n"
            "  → 페이지의 그래픽 상태를 감싸지 못했을 수 있습니다 (wrap_contents)."
            % "\n  ".join(bad[:5])
        )
    return n


def has_cover(html_path):
    """표지가 있으면 1장은 쪽번호를 찍지 않는다. «있다고 가정»하지 않고 읽어서 본다."""
    try:
        html = io.open(html_path, encoding="utf-8").read()
    except OSError:
        return False
    return bool(re.search(r'<div class="cover(?:[ "][^>]*)?>', html))


def html_to_pdf(html_path, pdf_path, stamp=True):
    browser = find_browser()
    if not browser:
        raise SystemExit(
            "크롬·엣지를 찾지 못했습니다.\n"
            "  설치돼 있는데 못 찾으면 환경변수로 알려 주세요:\n"
            "    GONGGAM_CHROME=<크롬 실행파일 경로>"
        )
    print("[브라우저] %s" % browser)

    profile = tempfile.mkdtemp(prefix="gonggam-pdf-")
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--user-data-dir=%s" % profile,
        "--print-to-pdf=%s" % os.path.abspath(pdf_path),
        to_url(html_path),
    ]
    # 먼저 지운다 — 크롬이 실패했는데 «지난번 PDF» 가 남아 있으면 그것을 새 결과로
    # 착각한다. 조용히 옛 파일을 내보내는 것이 가장 나쁘다.
    if os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
        except OSError as e:
            raise SystemExit("이전 PDF 를 지울 수 없습니다 (뷰어에서 열려 있나요?): %s" % e)

    # 크롬은 PDF 를 다 쓰고도 «종료»를 못 하고 매달릴 때가 있다 (PC 가 바쁠 때 자주).
    # 그때 파일은 멀쩡히 나와 있다 — 그래서 시간을 재고, 결과물이 있으면 그것으로 간다.
    # 무한정 기다리면 렌더가 통째로 멈춘다.
    out = err = b""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=BROWSER_TIMEOUT)
        out, err = r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        out, err = e.stdout or b"", e.stderr or b""
        if not os.path.exists(pdf_path):
            raise SystemExit(
                "크롬이 %d초 안에 PDF 를 내놓지 못했습니다.\n%s" % (BROWSER_TIMEOUT, err[-800:]))
        print("[주의] 크롬이 %d초 안에 끝나지 않아 PDF 만 받고 끊었습니다." % BROWSER_TIMEOUT)
    if not os.path.exists(pdf_path):
        raise SystemExit("PDF 가 생성되지 않았습니다.\n%s\n%s" % (out[-800:], err[-800:]))

    size = os.path.getsize(pdf_path)
    if size < 20000:
        raise SystemExit("PDF 가 %d bytes 뿐입니다 — 본문이 렌더되지 않았을 수 있습니다." % size)

    if stamp:
        stamp_pages(pdf_path, skip_first=has_cover(html_path))
        size = os.path.getsize(pdf_path)
    print("[PDF] %s (%.2f MB)" % (pdf_path, size / 1024.0 / 1024.0))
    return pdf_path


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    html_to_pdf(args[0], args[1], stamp="--no-stamp" not in sys.argv)


if __name__ == "__main__":
    main()
