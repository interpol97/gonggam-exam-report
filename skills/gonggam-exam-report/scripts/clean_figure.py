#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
잘라낸 그림을 «인쇄해도 되는» 상태로 만든다.

    python clean_figure.py <입력.png> <출력.png> [--kind line|photo] [--h 900]
    python clean_figure.py <폴더> <출력폴더> [--kind ...]        폴더 통째로

── 왜 필요한가
과학의 실험 장치도·회로도, 사회의 지도·사료는 **다시 그릴 수 없다.**
좌표로 환원되지 않는 그림을 파라미터로 재현하려 하면 반드시 틀린다.
그러면 남는 길은 하나다 — **원본을 깨끗하게 만들어 제자리에 꽂는 것.**

사진으로 찍은 시험지에서 잘라낸 그림은 그냥 쓰면 이렇게 나온다:
기울어져 있고, 한쪽이 그늘지고, 종이 결이 얼룩으로 남고, 여백이 제각각이다.
인쇄하면 회색 얼룩이 그대로 찍힌다.

── 무엇을 하나
  ① 기울기 보정   잉크의 최소외접사각형 각도로 바로 세운다
  ② 조명 정규화   크게 흐린 배경으로 나눠 그늘·종이결을 지운다
  ③ 2값화·정리    선그림은 검정/흰색으로. 사진은 명암만 고르게
  ④ 티끌 제거     아주 작은 덩어리를 지운다 (점·먼지)
  ⑤ 여백 트림     잉크 경계에 맞춰 자르고 일정한 여백을 준다
  ⑥ 크기 정규화   높이를 맞춰 리포트에서 나란히 보이게

── kind
  line   도형·그래프·회로도·장치도 — 2값화한다 (기본)
  photo  사진·지도·사료 — 2값화하지 않는다. 뭉개지면 못 읽는다
"""

import os
import sys

MIN_INK = 0.002          # 정리 후 잉크가 이보다 적으면 다 지워버린 것이다
SPECK = 0.00002          # 전체 면적 대비 이보다 작은 덩어리는 티끌
PAD = 18                 # 트림 뒤 남길 여백(px)


class CleanError(Exception):
    pass


def _cv():
    try:
        import cv2
        import numpy as np
        return cv2, np
    except ImportError:
        raise CleanError("opencv-python 과 numpy 가 필요합니다 — pip install opencv-python numpy")


# ── ① 기울기 ────────────────────────────────────────────────
def _sharpness(ink, np):
    """가로 투영의 «날카로움». 똑바로 서 있을수록 줄과 빈칸의 대비가 커진다."""
    prof = ink.sum(axis=1).astype("float64")
    return float(((prof[1:] - prof[:-1]) ** 2).sum())


def deskew(gray, limit=12.0, step=0.25):
    """가로 투영 프로파일이 가장 날카로워지는 각으로 바로 세운다.

    처음에는 잉크의 최소외접사각형 각도를 썼다. **가로로 넓은 그림에서 통째로
    실패한다** — 막대그래프를 4° 기울여 넣었는데 0.0° 로 읽고 그냥 내보냈다.
    구름이 넓으면 외접사각형이 거의 축에 붙어서 각이 안 나온다.

    투영 프로파일은 글줄·눈금선이 가로로 늘어선다는 성질만 쓰므로 그림 모양을 안 탄다.

    한도를 둔다. 도형은 원래 비스듬한 선이 많아서 각을 그대로 믿으면
    **멀쩡한 그림을 눕혀 버린다.** 12°를 넘으면 «원래 그런 그림» 으로 본다."""
    cv2, np = _cv()
    h, w = gray.shape
    small = cv2.resize(gray, (min(w, 700), max(1, int(h * min(w, 700) / w))),
                       interpolation=cv2.INTER_AREA)
    ink0 = (small < 200).astype(np.uint8)
    if ink0.sum() < 50:
        return gray, 0.0

    sh, sw = small.shape
    best, best_a = -1.0, 0.0
    a = -limit
    while a <= limit + 1e-9:
        M = cv2.getRotationMatrix2D((sw / 2, sh / 2), a, 1.0)
        rot = cv2.warpAffine(ink0, M, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        s = _sharpness(rot, np)
        if s > best:
            best, best_a = s, a
        a += step

    if abs(best_a) < 0.3:
        return gray, 0.0
    M = cv2.getRotationMatrix2D((w / 2, h / 2), best_a, 1.0)
    out = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE)
    return out, best_a


# ── ② 조명 ──────────────────────────────────────────────────
def normalize_light(gray):
    """크게 흐린 배경으로 나눈다. 그늘과 종이결이 사라지고 선만 남는다."""
    cv2, np = _cv()
    k = max(31, (min(gray.shape) // 8) | 1)          # 홀수여야 한다
    bg = cv2.GaussianBlur(gray, (k, k), 0)
    bg[bg < 1] = 1
    out = (gray.astype(np.float32) / bg.astype(np.float32)) * 220.0
    return np.clip(out, 0, 255).astype(np.uint8)


# ── ③④ 2값화·티끌 ──────────────────────────────────────────
def binarize(gray):
    cv2, np = _cv()
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return bw


def despeck(bw):
    """아주 작은 덩어리를 지운다. 먼지·스캔 점은 인쇄하면 눈에 띈다."""
    cv2, np = _cv()
    inv = (bw < 128).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, 8)
    area = bw.shape[0] * bw.shape[1]
    out = bw.copy()
    removed = 0
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < max(4, area * SPECK):
            out[lab == i] = 255
            removed += 1
    return out, removed


# ── ⑤ 트림 ──────────────────────────────────────────────────
def trim(img, pad=PAD):
    cv2, np = _cv()
    ink = np.argwhere(img < 200)
    if len(ink) == 0:
        raise CleanError("정리 후 잉크가 하나도 남지 않았습니다 — 원본을 확인하세요")
    y0, x0 = ink.min(0)
    y1, x1 = ink.max(0)
    h, w = img.shape
    y0, x0 = max(0, y0 - pad), max(0, x0 - pad)
    y1, x1 = min(h, y1 + pad + 1), min(w, x1 + pad + 1)
    return img[y0:y1, x0:x1]


# ── ⑥ 크기 ──────────────────────────────────────────────────
def fit_height(img, target):
    cv2, np = _cv()
    h, w = img.shape[:2]
    if not target or h == target:
        return img
    s = float(target) / h
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, (max(1, int(w * s)), target), interpolation=interp)


def ink_ratio(img):
    cv2, np = _cv()
    return float((img < 200).sum()) / float(img.size)


def clean(src, dst, kind="line", height=900):
    """한 장을 정리한다. 결과가 망가졌으면 **저장하지 않고 막는다.**"""
    cv2, np = _cv()
    raw = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
    if raw is None:
        raise CleanError("이미지를 읽지 못했습니다: %s" % src)

    before = ink_ratio(raw)
    img, angle = deskew(raw)
    img = normalize_light(img)

    removed = 0
    if kind == "line":
        img = binarize(img)
        img, removed = despeck(img)
    else:
        # 사진·지도는 2값화하지 않는다 — 뭉개지면 못 읽는다. 대비만 고르게
        img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img)

    img = trim(img)
    img = fit_height(img, height)

    after = ink_ratio(img)
    if after < MIN_INK:
        raise CleanError(
            "정리 결과가 거의 비었습니다 (잉크 %.2f%% → %.2f%%)\n"
            "  --kind photo 로 다시 해보세요. 옅은 그림은 2값화에서 날아갑니다."
            % (before * 100, after * 100))

    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    if not cv2.imwrite(dst, img):
        raise CleanError("저장에 실패했습니다: %s" % dst)

    h, w = img.shape[:2]
    return {"file": dst, "px": [w, h], "angle": round(angle, 2),
            "specks_removed": removed, "ink": round(after, 4), "kind": kind}


# ── 제자리에 꽂기 ────────────────────────────────────────────
def place_in_markdown(md, figures):
    """그림을 «원래 있던 자리»에 넣는다.

    문항 끝에 몰아 붙이면 안 된다 — 「다음 그림과 같이」 다음에 와야 뜻이 통한다.
    HWP 리더가 인라인 컨트롤 자리를 남기는 것과 같은 이유다.

    figures 의 각 항목에 `anchor` (그림 **바로 앞** 본문 조각)를 적어 둔다.
    앵커를 못 찾으면 **문항 끝에 붙이고 그렇게 했다고 알린다** — 조용히 옮기지 않는다.
    """
    misses = []
    for f in figures:
        block = "\n\n![%s번 그림](%s)\n" % (f.get("no", ""), f["file"])
        if f.get("alt"):
            block += "\n> **그림** — %s\n" % f["alt"]
        anchor = (f.get("anchor") or "").strip()
        if anchor and anchor in md:
            i = md.index(anchor) + len(anchor)
            md = md[:i] + block + md[i:]
        else:
            misses.append(f.get("no"))
            md = md.rstrip() + "\n" + block
    return md, misses


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    kind = "line"
    height = 900
    if "--kind" in sys.argv:
        kind = sys.argv[sys.argv.index("--kind") + 1]
    if "--h" in sys.argv:
        height = int(sys.argv[sys.argv.index("--h") + 1])
    if len(args) < 2:
        print(__doc__)
        return 1

    src, dst = args[0], args[1]
    jobs = []
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for f in sorted(os.listdir(src)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                jobs.append((os.path.join(src, f), os.path.join(dst, os.path.splitext(f)[0] + ".png")))
    else:
        jobs.append((src, dst))

    print("\n=== 그림 정리 (%d장 · kind=%s) ===" % (len(jobs), kind))
    bad = 0
    for s, d in jobs:
        try:
            r = clean(s, d, kind=kind, height=height)
            print("  [정리] %-22s %4dx%-4d  기울기 %+.1f°  티끌 %d개  잉크 %.1f%%"
                  % (os.path.basename(d), r["px"][0], r["px"][1],
                     r["angle"], r["specks_removed"], r["ink"] * 100))
        except CleanError as e:
            bad += 1
            print("  [실패] %s — %s" % (os.path.basename(s), e), file=sys.stderr)
    if bad:
        print("\n%d장 실패 — 고치기 전에는 쓰지 않습니다." % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
