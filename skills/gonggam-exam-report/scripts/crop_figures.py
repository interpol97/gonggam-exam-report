#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시험지에서 그림(그래프·도형·장치도)을 잘라낸다.

    python crop_figures.py <시험지.pdf|페이지이미지폴더> <figures.json> <출력폴더>

── 왜 «다시 그리지» 않고 «자르는가»
수학·과학 문항의 도형은 수치가 곧 문제다. ∠A=100°, AB=5 를 기하학적으로 맞게
다시 그리는 일은 실패율이 높고, 틀리면 **문제 자체가 달라진다.**
원본을 그대로 자르면 충실도가 100% 다. 100% 가 있는데 위험을 질 이유가 없다.

── 분업은 그대로다
Claude 는 **좌표만 준다.** 자르는 것은 기계가 한다 — HTML 을 쓰지 않는 것과 같은 이유다.
좌표는 판단이고 자르기는 산수다.

── figures.json (Claude 가 만든다)
{
  "source": "myeongji_2026_1_mid_math.pdf",
  "dpi": 300,
  "figures": [
    {"no": 18, "page": 3, "crop": [0.12, 0.34, 0.58, 0.61],
     "kind": "graph", "alt": "좌표평면. x축 시간(s), y축 속도(m/s). 직선 A·B"}
  ]
}
crop 은 그 **페이지 기준 정규화 좌표** [x0, y0, x1, y1] (0~1, 왼쪽 위가 0,0).
"""

import io
import json
import os
import re
import sys

PAD = 0.012          # 잘린 라벨이 없도록 사방에 여유를 둔다 (페이지 비율)
MIN_PX = 80          # 이보다 작으면 좌표를 잘못 준 것이다
MIN_INK = 0.004      # 잉크가 이보다 적으면 빈 자리를 자른 것이다


def ink_ratio(png_bytes):
    """흰 바탕이 아닌 화소의 비율. 빈 자리를 잘랐는지 보는 유일하게 확실한 방법이다."""
    from PIL import Image

    im = Image.open(io.BytesIO(png_bytes)).convert("L")
    im.thumbnail((400, 400))                      # 빠르게 — 비율만 보면 된다
    px = list(im.getdata())
    if not px:
        return 0.0
    return sum(1 for v in px if v < 235) / float(len(px))


def guard_blank(no, png_bytes):
    """빈 그림을 «조용히» 저장하지 않는다.
    실제로 그 사고가 났다 — 좌표를 잘못 준 줄 모르고 백지 png 가 MD 에 박혔다."""
    r = ink_ratio(png_bytes)
    if r < MIN_INK:
        raise CropError(
            "%s번: 잘라낸 자리가 비어 있습니다 (잉크 %.2f%%)\n"
            "  페이지 번호나 crop 좌표가 틀렸습니다. 페이지를 먼저 확인하세요:\n"
            "    python crop_figures.py <시험지.pdf> --pages <미리보기폴더>"
            % (no, r * 100))
    return r


class CropError(Exception):
    pass


def _need_fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        raise CropError(
            "PyMuPDF 가 필요합니다 — pip install pymupdf\n"
            "  (그림을 자르지 못하면 수학·과학 문항은 MD 로 옮길 수 없습니다)"
        )


def clamp01(v):
    return max(0.0, min(1.0, float(v)))


def crop_from_pdf(pdf_path, figs, out_dir, dpi=300):
    fitz = _need_fitz()
    doc = fitz.open(pdf_path)
    made = []
    for f in figs:
        page_no = int(f["page"]) - 1
        if not (0 <= page_no < len(doc)):
            raise CropError("%s번: %d페이지가 없습니다 (전체 %d쪽)"
                            % (f.get("no"), page_no + 1, len(doc)))
        page = doc[page_no]
        pr = page.rect

        x0, y0, x1, y1 = [clamp01(v) for v in f["crop"]]
        if x1 <= x0 or y1 <= y0:
            raise CropError("%s번: crop 좌표가 뒤집혔습니다 %s" % (f.get("no"), f["crop"]))
        # 여유를 두되 페이지를 넘지 않게
        x0, y0 = clamp01(x0 - PAD), clamp01(y0 - PAD)
        x1, y1 = clamp01(x1 + PAD), clamp01(y1 + PAD)

        rect = fitz.Rect(pr.x0 + x0 * pr.width, pr.y0 + y0 * pr.height,
                         pr.x0 + x1 * pr.width, pr.y0 + y1 * pr.height)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)

        if pix.width < MIN_PX or pix.height < MIN_PX:
            raise CropError(
                "%s번: 잘라낸 그림이 %dx%d 로 너무 작습니다 — 좌표를 다시 잡으세요"
                % (f.get("no"), pix.width, pix.height))

        data = pix.tobytes("png")
        r = guard_blank(f.get("no"), data)          # 빈 자리면 여기서 멈춘다
        name = "q%02d.png" % int(f["no"])
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(data)
        made.append({"no": f["no"], "file": "figs/" + name,
                     "px": [pix.width, pix.height], "ink": round(r, 4),
                     "kind": f.get("kind", ""), "alt": f.get("alt", "")})
        print("  [자름] %s  %dx%d px  잉크 %.1f%%  %s"
              % (name, pix.width, pix.height, r * 100, f.get("kind", "")))
    doc.close()
    return made


def crop_from_images(folder, figs, out_dir):
    """사진·스캔 입력. 페이지 번호가 파일 이름 순서와 같아야 한다."""
    from PIL import Image

    # 자연 정렬 — 그냥 sorted() 면 p1, p10, p11, p2 순이 된다.
    # 10쪽을 넘는 사진 묶음에서 **페이지 순서가 통째로 뒤집힌다.**
    def natkey(s):
        return [int(t) if t.isdigit() else t.lower()
                for t in re.split(r"(\d+)", s)]

    pages = sorted((f for f in os.listdir(folder)
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))),
                   key=natkey)
    if not pages:
        raise CropError("페이지 이미지가 없습니다: %s" % folder)

    made = []
    for f in figs:
        i = int(f["page"]) - 1
        if not (0 <= i < len(pages)):
            raise CropError("%s번: %d번째 이미지가 없습니다 (전체 %d장)"
                            % (f.get("no"), i + 1, len(pages)))
        im = Image.open(os.path.join(folder, pages[i])).convert("RGB")
        W, H = im.size
        x0, y0, x1, y1 = [clamp01(v) for v in f["crop"]]
        box = (int(clamp01(x0 - PAD) * W), int(clamp01(y0 - PAD) * H),
               int(clamp01(x1 + PAD) * W), int(clamp01(y1 + PAD) * H))
        out = im.crop(box)
        if out.width < MIN_PX or out.height < MIN_PX:
            raise CropError("%s번: 잘라낸 그림이 %dx%d 로 너무 작습니다"
                            % (f.get("no"), out.width, out.height))
        buf = io.BytesIO()
        out.save(buf, "PNG")
        r = guard_blank(f.get("no"), buf.getvalue())
        name = "q%02d.png" % int(f["no"])
        out.save(os.path.join(out_dir, name))
        # 사진은 기울기·그림자 때문에 인쇄 품질을 장담하지 못한다 — 표시를 남긴다
        made.append({"no": f["no"], "file": "figs/" + name,
                     "px": [out.width, out.height], "kind": f.get("kind", ""),
                     "alt": f.get("alt", ""), "ink": round(r, 4),
                     "figure_quality": "low"})
        print("  [자름] %s  %dx%d px  잉크 %.1f%%  (사진 — 품질 low)"
              % (name, out.width, out.height, r * 100))
    return made


def preview_pages(pdf_path, out_dir, dpi=110):
    """페이지를 통째로 그려 둔다. Claude 는 이 그림을 보고 crop 좌표를 잡는다 —
    페이지 번호를 짐작으로 적으면 빈 자리를 자르게 된다."""
    fitz = _need_fitz()
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        name = "p%02d.png" % (i + 1)
        pix.save(os.path.join(out_dir, name))
        print("  [페이지] %s  %dx%d" % (name, pix.width, pix.height))
    n = len(doc)
    doc.close()
    print("\n  %d쪽. 이 그림들을 보고 figures.json 의 page·crop 을 적습니다." % n)
    return n


def markdown_block(fig):
    """MD 에 들어갈 꼴. **그림과 설명을 나란히 둔다** —
    이미지를 못 보는 곳(검색·다른 스킬)에서도 뜻이 통해야 한다."""
    lines = ["![%s번 그림](%s)" % (fig["no"], fig["file"])]
    if fig.get("alt"):
        lines += ["", "> **그림** — %s" % fig["alt"]]
    return "\n".join(lines)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    if sys.argv[2] == "--pages":
        print("\n=== 페이지 미리보기 ===")
        preview_pages(sys.argv[1], sys.argv[3])
        return 0

    src, spec_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    spec = json.load(io.open(spec_path, encoding="utf-8"))
    figs = spec.get("figures") or []
    if not figs:
        print("  · 자를 그림이 없습니다")
        return 0

    fig_dir = os.path.join(out_dir, "figs")
    os.makedirs(fig_dir, exist_ok=True)

    print("\n=== 그림 잘라내기 (%d개) ===" % len(figs))
    try:
        if os.path.isdir(src):
            made = crop_from_images(src, figs, fig_dir)
        else:
            made = crop_from_pdf(src, figs, fig_dir, dpi=int(spec.get("dpi", 300)))
    except CropError as e:
        print("\n[중단] %s" % e, file=sys.stderr)
        return 1

    idx = os.path.join(out_dir, "figures.index.json")
    io.open(idx, "w", encoding="utf-8").write(
        json.dumps({"figures": made}, ensure_ascii=False, indent=2))
    print("\n  %d개 완료 · 색인 %s" % (len(made), idx))
    low = [m["no"] for m in made if m.get("figure_quality") == "low"]
    if low:
        print("  [주의] 사진에서 자른 그림 %s — 인쇄 전에 눈으로 확인하세요" % low)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
