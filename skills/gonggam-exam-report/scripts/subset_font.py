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

없는 글자를 만나면 — **막고, 어디인지 말한다**
    막는 것 자체는 옳다. 두부로 인쇄되는 것보다 낫다. 다만 옛 메시지는 «없는 글자가
    N개 있습니다» 까지만 말해서, 판형 주석의 ⛔ 하나 때문에 렌더가 죽어도 그것이 어느
    파일 몇 번째 줄에 있는지 아무도 몰랐다. 그래서 지금은 이렇게 말한다 —

      · 어느 글자인가 (글자 + U+XXXX)
      · 어디에 있는가 (판형 / 테마 / 데이터, 파일:줄, 그 줄의 본문)
      · 주석인가 본문인가 (주석이면 그냥 지우면 된다)
      · 무엇으로 바꾸면 되는가 (references/glyphs.md 의 대체표)

    **자동으로 바꾸지는 않는다.** 조용히 고치면 원장님이 쓴 ✗ 가 × 로 둔갑해 나간다.
    막고 알려 주는 데서 멈춘다.
"""

import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
GLYPHS_MD = os.path.join(SKILL, "references", "glyphs.md")

# 본문에 안 보여도 폰트에 있어야 하는 것들 (숫자·문장부호·여백)
# ✔(U+2714)·⟨⟩(U+27E8·9) 는 **동봉 폰트에 없다.** 여기 적어 둬도 아래에서 걸러지지만,
# 보는 사람이 «✔ 는 되는구나» 로 읽으면 안 되므로 애초에 있는 것만 적는다
# (✓ U+2713 · 〈〉 U+3008·9). 재 보는 법은 references/glyphs.md.
ALWAYS = set(
    " \t\n0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    ".,:;!?'\"()[]{}<>/\\|-–—_=+*&%#@~^`$"
    "·…「」『』《》〈〉«»‘’“”→←↑↓±×÷≤≥≠°※★☆✓①②③④⑤⑥⑦⑧⑨⑩"
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

    **주석도 읽는다.** set(html) 은 눈에 보이는 글자와 안 보이는 글자를 가리지 않는다.
    판형 주석에 적어 둔 기호 하나가 렌더를 죽이는 까닭이 이것이다 (references/glyphs.md).

    ALWAYS 는 여기 섞지 않는다. 둘은 성격이 다르다 —
    쓰인 글자가 폰트에 없으면 **사고**고, 예비 글자가 없는 것은 그냥 안 넣으면 된다."""
    return set(html)


def font_chars(src_path):
    """그 폰트가 가진 코드포인트 집합."""
    from fontTools.ttLib import TTFont

    font = TTFont(src_path)
    have = set()
    for table in font["cmap"].tables:
        have |= set(table.cmap.keys())
    font.close()
    return have


def missing_in_font(src_path, chars):
    """원본 폰트에 아예 없는 글자를 돌려준다. 있으면 두부가 찍힌다."""
    have = font_chars(src_path)
    return sorted(c for c in chars if ord(c) not in have and c not in "\t\n\r")


# ------------------------------------------------------------------ 대체표
# 정본은 references/glyphs.md 다. 여기에 사본을 두지 않는다 — 두 벌이 되면 갈라진다.
_ROW = re.compile(r"^\|([^|]*)\|\s*U\+([0-9A-Fa-f]{4,6})\s*\|([^|]*)\|")


def substitutions(path=GLYPHS_MD):
    """glyphs.md 의 대체표를 읽는다 → {없는 글자: '대신 쓸 것(사람이 읽는 문구)'}.

    표 꼴:  | ✗ | U+2717 | `×` (U+00D7) | 비고 |
    첫 칸의 글자와 둘째 칸의 코드가 서로 맞는 줄만 받는다 —
    표 머리도 구분선도 저절로 빠지고, 오타가 난 줄은 조용히 무시되는 대신
    «대체표에 없음» 으로 드러난다."""
    table = {}
    if not os.path.exists(path):
        return table
    try:
        text = io.open(path, encoding="utf-8").read()
    except OSError:
        return table
    for line in text.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        want = m.group(1).strip().strip("`").strip()
        if len(want) != 1 or ord(want) != int(m.group(2), 16):
            continue
        table[want] = m.group(3).strip()
    return table


# ------------------------------------------------------------------ 자리 찾기
def source(role, path, text=None, kind=None, fallback=False):
    """글자를 찾아볼 곳 한 군데. role 은 «판형·테마·데이터» 처럼 사람이 읽는 이름."""
    if text is None:
        text = io.open(path, encoding="utf-8").read()
    if kind is None:
        kind = os.path.splitext(path)[1].lower().lstrip(".") or "text"
    return {"role": role, "path": path, "text": text, "kind": kind, "fallback": fallback}


def _mark(mask, a, b):
    for k in range(max(a, 0), min(b, len(mask))):
        mask[k] = 1


def _pairs(text, mask, opener, closer, lo=0, hi=None):
    hi = len(text) if hi is None else hi
    i = lo
    while True:
        a = text.find(opener, i, hi)
        if a < 0:
            return
        b = text.find(closer, a + len(opener), hi)
        end = hi if b < 0 else b + len(closer)      # 안 닫혔으면 끝까지 주석으로 본다
        _mark(mask, a, end)
        i = end


_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)


def comment_mask(text, kind):
    """그 글자가 «주석 안» 인지 가리는 자 — 1 이면 주석.

    HTML 은 <!-- --> 와, <style> 안의 /* */ 를 주석으로 본다.
    CSS 는 /* */. JSON 은 주석 문법이 없으니 전부 본문이다."""
    mask = bytearray(len(text))
    if kind in ("html", "htm"):
        _pairs(text, mask, "<!--", "-->")
        for m in _STYLE.finditer(text):
            _pairs(text, mask, "/*", "*/", m.start(1), m.end(1))
    elif kind in ("css", "scss"):
        _pairs(text, mask, "/*", "*/")
    return mask


def _excerpt(line, col, width=96):
    line = line.replace("\t", " ").rstrip()
    if len(line) <= width:
        return line.strip()
    lo = max(0, col - width // 2)
    hi = min(len(line), lo + width)
    return ("…" if lo else "") + line[lo:hi].strip() + ("…" if hi < len(line) else "")


def locate(bad, sources, per_source=2):
    """없는 글자마다 «어디에 있나» 를 찾는다 → {글자: [자리, ...]}.

    자리 = {role, path, line, text, comment}
    fallback 자리(조판 결과 HTML)는 **앞의 진짜 파일에서 못 찾았을 때만** 쓴다 —
    조판 결과에는 판형·테마·데이터가 전부 녹아 있어서, 그것만 말하면 원인을 못 짚는다."""
    if not sources:
        return dict((c, []) for c in bad)
    prepared = []
    for s in sources:
        needed = any(ch in s["text"] for ch in bad)
        prepared.append((s, comment_mask(s["text"], s["kind"]) if needed else None))

    found = {}
    for ch in bad:
        hits = []
        for s, mask in prepared:
            if s.get("fallback") and hits:
                continue
            text = s["text"]
            if ch not in text:
                continue
            take, start = 0, 0
            while take < per_source:
                i = text.find(ch, start)
                if i < 0:
                    break
                bol = text.rfind("\n", 0, i) + 1
                eol = text.find("\n", i)
                eol = len(text) if eol < 0 else eol
                hits.append({
                    "role": s["role"],
                    "path": s["path"],
                    "line": text.count("\n", 0, i) + 1,
                    "text": _excerpt(text[bol:eol], i - bol),
                    "comment": bool(mask and mask[i]),
                })
                take += 1
                start = i + 1
        found[ch] = hits
    return found


def _rel(path):
    try:
        r = os.path.relpath(path, SKILL)
    except ValueError:
        return path
    return path if r.startswith("..") else r.replace("\\", "/")


def describe_missing(src_path, bad, sources=None, limit=12):
    """사람이 읽고 **바로 고칠 수 있는** 실패 메시지를 만든다."""
    where = locate(bad, sources or [])
    subs = substitutions()
    out = [
        "동봉 폰트에 없는 글자가 %d 개 있습니다 — 그대로 두면 네모(두부)로 인쇄됩니다." % len(bad),
        "  폰트: %s" % _rel(src_path),
        "",
    ]
    for n, ch in enumerate(bad[:limit], 1):
        hits = where.get(ch) or []
        only_comment = bool(hits) and all(h["comment"] for h in hits)
        tag = "주석" if only_comment else ("본문" if hits else "자리 못 찾음")
        out.append("%d) %s  U+%04X   [%s]" % (n, ch, ord(ch), tag))
        for h in hits:
            out.append("     %s  %s:%d%s" % (h["role"], _rel(h["path"]), h["line"],
                                             "  (주석)" if h["comment"] else ""))
            if h["text"]:
                out.append("       %s" % h["text"])
        if not hits:
            out.append("     어느 파일인지 못 찾았습니다 — 데이터(report.json)에 "
                       "\\uXXXX 로 적혀 있을 수 있습니다.")
        if only_comment:
            out.append("     → 주석입니다. **그냥 지우세요.** 서브세터는 주석까지 읽습니다 "
                       "(안 보이는 글자도 폰트에 있어야 합니다).")
        elif ch in subs:
            out.append("     → %s 로 바꾸세요." % subs[ch])
        else:
            out.append("     → 대체표에 없는 글자입니다. references/glyphs.md 를 보고 "
                       "쓸 수 있는 글자로 바꾸거나, 표에 한 줄 더하세요.")
        out.append("")
    if len(bad) > limit:
        out.append("… 그 밖 %d 개: %s" % (len(bad) - limit, " ".join(bad[limit:])))
        out.append("")
    out.append("자동으로 바꾸지 않습니다 — 원장님이 쓴 ✗ 가 말없이 × 로 둔갑해 나가면 안 됩니다.")
    out.append("규격: references/glyphs.md   ·   한 글자만 재보기: "
               "python scripts/subset_font.py --check \"기호들\"")
    return "\n".join(out)


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


def build(src_path, chars, sources=None):
    """(bytes, 설명) — 서브셋이 되면 서브셋, 안 되면 원본.

    sources 를 주면 실패 메시지가 «어느 파일 몇 번째 줄» 까지 말한다.
    안 줘도 동작은 같다 — 자리를 못 짚을 뿐이다."""
    if not os.path.exists(src_path):
        raise FontError("폰트가 없습니다: %s" % src_path)
    full = os.path.getsize(src_path)

    if not available():
        with open(src_path, "rb") as f:
            return f.read(), "원본 %.1fMB (fontTools·brotli 없음 — 서브셋 건너뜀)" % (full / 1e6)

    # 쓰인 글자가 폰트에 없으면 막는다 — 인쇄한 뒤에 두부를 발견하면 늦다
    bad = missing_in_font(src_path, chars)
    if bad:
        raise FontError(describe_missing(src_path, bad, sources))

    # 예비 글자(ALWAYS)는 폰트에 있는 것만 넣는다. 없다고 막을 이유가 없다
    spare = set(ALWAYS) - set(missing_in_font(src_path, ALWAYS))
    data = subset_woff2(src_path, set(chars) | spare)
    return data, "%.0fKB (원본 %.1fMB → %.1f%%)" % (
        len(data) / 1e3, full / 1e6, len(data) / full * 100)


# ------------------------------------------------------------------ 손으로 재기
DEFAULT_FONT = os.path.join(SKILL, "assets", "fonts", "NotoSansKR-400.woff2")


def check(chars, src_path=DEFAULT_FONT):
    """«이 기호 써도 되나» 를 한 줄로 재 준다. 추측하지 말고 이걸로 재라."""
    have = font_chars(src_path)
    subs = substitutions()
    seen, rows = set(), []
    for c in chars:
        if c in seen or c in " \t\n\r":
            continue
        seen.add(c)
        ok = ord(c) in have
        rows.append("  %s  U+%04X  %s%s" % (
            c, ord(c), "있음" if ok else "없음",
            "" if ok else "  → %s" % subs.get(c, "대체표에 없음 (glyphs.md 에 한 줄 더하세요)")))
    return "폰트: %s\n%s" % (_rel(src_path), "\n".join(rows))


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    argv = sys.argv[1:]
    if argv and argv[0] == "--check":
        if len(argv) < 2:
            print("사용: python subset_font.py --check \"기호들\" [폰트.woff2]")
            sys.exit(1)
        print(check(argv[1], argv[2] if len(argv) > 2 else DEFAULT_FONT))
        sys.exit(0)
    if len(argv) < 2:
        print("사용: python subset_font.py <폰트.woff2> <글자가 든 파일>")
        print("      python subset_font.py --check \"기호들\"      ← 기호 하나하나 재 보기")
        sys.exit(1)
    text = io.open(argv[1], encoding="utf-8").read()
    try:
        data, note = build(argv[0], chars_of(text), [source("입력", argv[1], text)])
    except FontError as e:
        print("\n[폰트 실패] %s" % e)
        sys.exit(1)
    print("글자 %d 종 · %s" % (len(chars_of(text)), note))
