#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
리포트에 실제로 쓰인 글자만 남긴 woff2 를 만든다.

한글 전체를 담으면 woff2 한 벌이 2MB 다. 두 굵기면 4MB 고, base64 로 박으면 5.5MB 가
된다 — 메일에 못 붙인다. 그렇다고 «자주 쓰는 2350자» 같은 고정 집합으로 자르면
지문에 그 밖의 글자가 하나만 나와도 네모(두부)가 찍힌다. 그 사고는 인쇄한 뒤에 발견된다.

그래서 **그 리포트의 글자만** 남긴다. 리포트마다 쓰는 글자가 다르니 리포트마다 만든다.
덤으로 «이 글자가 원본 폰트에 없다» 를 렌더 전에 잡아낸다.

fontTools 나 brotli 가 없으면 **원본을 그대로 쓴다** — 크기가 클 뿐 결과는 옳다.
조용히 글자를 빠뜨리는 쪽으로는 물러서지 않는다.
"""

import io
import os

# 본문에 안 보여도 폰트에 있어야 하는 것들 (숫자·문장부호·여백)
ALWAYS = set(
    " \t\n0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    ".,:;!?'\"()[]{}<>/\\|-–—_=+*&%#@~^`$"
    "·…「」『』《》〈〉‘’“”→←↑↓⟨⟩±×÷≤≥≠°※★☆✔①②③④⑤⑥⑦⑧⑨⑩"
    "가나다라마바사아자차카타파하"          # 흔한 라벨
)


class FontError(Exception):
    pass


def available():
    try:
        import brotli  # noqa: F401
        from fontTools import subset  # noqa: F401
        from fontTools.ttLib import TTFont  # noqa: F401
        return True
    except ImportError:
        return False


def chars_of(html):
    """HTML 에서 «실제로 쓰인» 글자만 뽑는다. 태그·CSS 까지 포함해도 손해가 없다 —
    라틴 글자 몇 개가 더 들어갈 뿐이고, 빠뜨리는 쪽이 훨씬 비싸다.

    ALWAYS 는 여기 섞지 않는다. 둘은 성격이 다르다 —
    쓰인 글자가 폰트에 없으면 **사고**고, 예비 글자가 없는 것은 그냥 안 넣으면 된다."""
    return set(html)


def missing_in_font(src_path, chars):
    """원본 폰트에 아예 없는 글자를 돌려준다. 있으면 두부가 찍힌다."""
    from fontTools.ttLib import TTFont

    font = TTFont(src_path)
    have = set()
    for table in font["cmap"].tables:
        have |= set(table.cmap.keys())
    font.close()
    bad = sorted(c for c in chars if ord(c) not in have and c not in "\t\n\r")
    return bad


def subset_woff2(src_path, chars):
    """필요한 글자만 남긴 woff2 바이트를 돌려준다."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(src_path)
    opts = subset.Options()
    opts.layout_features = ["*"]      # 자간·합자는 남긴다
    opts.name_IDs = ["*"]
    opts.notdef_outline = True        # 빠진 글자는 네모로 «보이게» 둔다
    opts.drop_tables = []
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=[ord(c) for c in chars])
    sub.subset(font)

    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    font.close()
    return buf.getvalue()


def build(src_path, chars):
    """(bytes, 설명) — 서브셋이 되면 서브셋, 안 되면 원본."""
    if not os.path.exists(src_path):
        raise FontError("폰트가 없습니다: %s" % src_path)
    full = os.path.getsize(src_path)

    if not available():
        with open(src_path, "rb") as f:
            return f.read(), "원본 %.1fMB (fontTools·brotli 없음 — 서브셋 건너뜀)" % (full / 1e6)

    # 쓰인 글자가 폰트에 없으면 막는다 — 인쇄한 뒤에 두부를 발견하면 늦다
    bad = missing_in_font(src_path, chars)
    if bad:
        raise FontError(
            "원본 폰트에 없는 글자가 %d 개 있습니다: %s\n"
            "  그대로 인쇄하면 네모(두부)로 찍힙니다. 글자를 바꾸거나 폰트를 바꾸세요."
            % (len(bad), " ".join(bad[:30]))
        )

    # 예비 글자(ALWAYS)는 폰트에 있는 것만 넣는다. 없다고 막을 이유가 없다
    spare = set(ALWAYS) - set(missing_in_font(src_path, ALWAYS))
    data = subset_woff2(src_path, set(chars) | spare)
    return data, "%.0fKB (원본 %.1fMB → %.1f%%)" % (
        len(data) / 1e3, full / 1e6, len(data) / full * 100)


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 3:
        print("사용: python subset_font.py <폰트.woff2> <글자가 든 파일>")
        sys.exit(1)
    text = io.open(sys.argv[2], encoding="utf-8").read()
    data, note = build(sys.argv[1], chars_of(text))
    print("글자 %d 종 · %s" % (len(chars_of(text)), note))
