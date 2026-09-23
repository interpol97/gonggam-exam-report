#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«아마도» 대기열을 집계하고, 목록에 올릴지 정한다.

    python promote_kind.py                      쌓인 것을 본다
    python promote_kind.py --check <종류>        승격 조건을 잰다
    python promote_kind.py --deny <종류> "이유"   다시 묻지 않게 박는다

── 왜 이게 있나
화이트리스트만 두면 목록이 **영원히 자라지 않는다.** 모르는 종류는 늘 CLEAN 으로
떨어지고, 아무도 그걸 다시 보지 않는다. 그러면 규격은 굳는 게 아니라 **썩는다.**

그래서 «아마도» 를 버리지 않고 쌓는다. 쌓인 것이 기준을 넘으면 **사람이 한 번**
보고, 승격은 **증거로만** 한다.

── 승격 기준 (셋 다 충족)
  ① 같은 종류가 MIN_HITS 건 이상 쌓였다     — 한두 건은 우연이다
  ② 표본 3건으로 figure_spec 을 실제로 만들었다
  ③ 셋 다 figure.py 위상 검사를 통과하고, 원본과 대조해 합격했다

하나라도 «아마도» 면 올리지 않고 **deny 에 박는다.**
박아 두는 이유는 분명하다 — 같은 질문을 여섯 달 뒤에 또 하지 않기 위해서다.
"""

import collections
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
QUEUE = os.path.join(DATA, "figure-candidates.jsonl")
DENY = os.path.join(DATA, "figure-kinds-denied.json")

MIN_HITS = 5          # 이만큼 쌓여야 검토 대상이다
SAMPLES = 3           # 승격 검증에 쓸 표본 수


def load_queue():
    if not os.path.exists(QUEUE):
        return []
    rows = []
    for line in io.open(QUEUE, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_deny():
    if not os.path.exists(DENY):
        return {}
    return json.load(io.open(DENY, encoding="utf-8"))


def save_deny(d):
    os.makedirs(DATA, exist_ok=True)
    io.open(DENY, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def summarize():
    rows = load_queue()
    deny = load_deny()
    if not rows:
        print("  · 대기열이 비어 있습니다")
        return 0

    by_kind = collections.Counter()
    by_reason = collections.Counter()
    for r in rows:
        by_kind[r.get("kind") or "(없음)"] += 1
        by_reason[(r.get("reason") or "").split(":")[0]] += 1

    print("\n=== «아마도» 대기열 (%d건) ===" % len(rows))
    print("  이유별: " + " · ".join("%s %d" % (k, v) for k, v in by_reason.most_common()))
    print()
    for kind, n in by_kind.most_common():
        if kind in deny:
            mark, note = "[박힘]", " — %s" % deny[kind].get("why", "")
        elif n >= MIN_HITS:
            mark, note = "[검토]", "  ← %d건. --check %s 로 재보세요" % (n, kind)
        else:
            mark, note = "[대기]", "  (%d/%d)" % (n, MIN_HITS)
        print("  %s %-18s %3d건%s" % (mark, kind, n, note))

    ready = [k for k, n in by_kind.items() if n >= MIN_HITS and k not in deny]
    print()
    if ready:
        print("  검토 대상 %d종: %s" % (len(ready), " · ".join(ready)))
    else:
        print("  아직 검토 대상이 없습니다 — %d건 이상 쌓여야 봅니다." % MIN_HITS)
    return 0


def check(kind):
    """승격 조건을 잰다. **통과시키지는 않는다** — 증거를 요구하고 절차를 보여 준다."""
    rows = [r for r in load_queue() if (r.get("kind") or "") == kind]
    deny = load_deny()
    print("\n=== 승격 검토: %s ===" % kind)

    if kind in deny:
        print("  [박힘] 이미 거절된 종류입니다 — %s" % deny[kind].get("why", ""))
        print("         새 근거가 있을 때만 data/figure-kinds-denied.json 에서 지웁니다.")
        return 1

    ok1 = len(rows) >= MIN_HITS
    print("  ① 쌓인 건수      %d / %d   %s" % (len(rows), MIN_HITS, "OK" if ok1 else "부족"))
    if not ok1:
        print("\n  아직 이릅니다. 우연히 한두 번 나온 종류로 규격을 바꾸지 않습니다.")
        return 1

    srcs = sorted({r.get("source", "?") for r in rows})
    print("     나온 곳: %s" % " · ".join(srcs[:6]))
    print("  ② 표본 %d건으로 figure_spec 작성        ← 사람이 한다" % SAMPLES)
    print("  ③ 셋 다 figure.py 위상 통과 + 원본 대조  ← 기계가 판정")
    print()
    print("  다음 순서로 진행합니다:")
    print("    1. 이 종류의 그림 %d개를 골라 figure_spec 을 씁니다" % SAMPLES)
    print("    2. figure.py 로 렌더합니다. 위상 위반이 하나라도 나면 여기서 끝입니다")
    print("    3. 렌더 결과를 원본 옆에 두고 **눈으로** 대조합니다")
    print("    4. 셋 다 합격하면 figure_route.py 의 KINDS 에 한 줄 더합니다")
    print("       (references/figure-routing.md 의 표도 같이 고칩니다 — 규격은 한 벌입니다)")
    print()
    print("  하나라도 «아마도» 면 올리지 않고 박습니다:")
    print("    python promote_kind.py --deny %s \"왜 안 되는지\"" % kind)
    return 0


def deny_kind(kind, why):
    d = load_deny()
    d[kind] = {"why": why, "at": __import__("datetime").date.today().isoformat()}
    save_deny(d)
    print("  [박음] %s — %s" % (kind, why))
    print("  이제 이 종류는 대기열에서 «박힘» 으로 표시되고 다시 검토 대상이 되지 않습니다.")
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = sys.argv[1:]
    if not a:
        return summarize()
    if a[0] == "--check" and len(a) > 1:
        return check(a[1])
    if a[0] == "--deny" and len(a) > 2:
        return deny_kind(a[1], a[2])
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
