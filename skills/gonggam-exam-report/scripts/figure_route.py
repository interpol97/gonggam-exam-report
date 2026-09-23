#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
그림을 어느 길로 보낼지 **기계가 정한다.**

    python figure_route.py <figures.json>

「다시 그리기 힘든가」는 열린 질문이다. 열린 질문은 물을 때마다 답이 달라진다.
그래서 묻지 않는다 — **닫힌 목록으로 바꾼다.**

    재드로잉은 «허용 목록에 있을 때만» 한다. 목록에 없으면 원본을 정리한다.

「힘든 것」을 정의하려 하면 끝이 없지만 「쉬운 것」은 셀 수 있다.
그리고 안전한 쪽(원본 정리)이 기본값이다 — 판정이 애매하면 저절로 안전해진다.

── 길 셋
  CLEAN    원본을 깨끗이 만들어 제자리에 꽂는다  (clean_figure.py)
  REDRAW   파라미터에서 다시 그린다             (math-engine/figure.py)
  TABLE    그림이 아니라 표다 — 마크다운 표로 옮긴다
"""

import datetime
import io
import json
import os
import sys

# ── 그림 종류 — 닫힌 목록. 여기 없는 kind 는 전부 CLEAN 이다 ──────────────
# REDRAW 가 되는 것은 «좌표로 환원되는» 그림뿐이다.
# figure.py 가 아는 어휘가 여덟뿐이라 그 밖은 그릴 수가 없다:
#   축 · 곡선 · 선분/꺾은선 · 원 · 채움 · 눈금/직각표시 · 점 · 라벨
KINDS = {
    # kind            : (길,        왜)
    "coord-graph":     ("REDRAW", "좌표평면·함수 그래프 — 식으로 환원된다"),
    "plane-geometry":  ("REDRAW", "평면도형(원·삼각형·다각형) — 점 좌표로 환원된다"),
    "number-line":     ("REDRAW", "수직선 — 점과 눈금뿐이다"),
    "stat-chart":      ("REDRAW", "막대·꺾은선·원그래프 — 수치에서 나온다"),

    "solid-geometry":  ("CLEAN",  "입체도형 — 투영각이 원본과 달라지면 다른 그림이 된다"),
    "apparatus":       ("CLEAN",  "실험 장치도 — 좌표로 환원되지 않는다"),
    "circuit":         ("CLEAN",  "회로도 — 기호 배치가 규약이다"),
    "map":             ("CLEAN",  "지도 — 지형을 다시 그릴 수 없다"),
    "photo":           ("CLEAN",  "사진·사료·유물 — 재현 대상이 아니다"),
    "diagram":         ("CLEAN",  "개념도·흐름도 — 배치가 곧 내용이다"),
    "handwriting":     ("CLEAN",  "손글씨·필기 — 원본이 곧 자료다"),
    "mixed":           ("CLEAN",  "여러 종류가 섞였다 — 섞이면 원본이 안전하다"),

    "table-image":     ("TABLE",  "그림으로 들어간 표 — 마크다운 표로 옮긴다"),
}

# ── 차단 조건 — 하나라도 걸리면 kind 와 무관하게 CLEAN ────────────────────
# 전부 «보면 아는» 사실이다. 판단이 아니라 관찰이다.
BLOCKERS = [
    ("purpose_is_original", "문제 원문을 옮기는 중이다 — 원문은 **언제나** 원본을 쓴다"),
    ("has_photo_texture",   "사진·음영·질감이 있다 — 선으로 환원되지 않는다"),
    ("has_handwriting",     "손글씨가 있다"),
    ("copyrighted_art",     "출판사 삽화·저작물이다 — 재현이 곧 2차 저작이다"),
    ("labels_over_8",       "라벨이 8개를 넘는다 — 배치가 어긋나기 시작한다"),
    ("no_invariants",       "위상 조건을 하나도 적을 수 없다 — 붕괴를 못 잡는다"),
    ("no_spec",             "figure_spec 이 없다 — 다시 그릴 근거가 없다"),
]


def route(fig):
    """한 그림의 길을 정한다. (길, 이유, 걸린 차단조건들)"""
    kind = (fig.get("kind") or "").strip()
    reasons = []

    # 모르는 kind 는 CLEAN. 목록에 없다고 추측하지 않는다.
    if kind not in KINDS:
        return "CLEAN", "모르는 종류 «%s» — 목록에 없으면 원본을 쓴다" % (kind or "(없음)"), []

    path, why = KINDS[kind]
    if path != "REDRAW":
        return path, why, []

    # REDRAW 후보만 차단 조건을 본다
    hits = [msg for key, msg in BLOCKERS if fig.get(key)]
    if hits:
        return "CLEAN", "재드로잉 후보였으나 차단됨", hits

    return "REDRAW", why, []


def decide(figs):
    out = []
    for f in figs:
        path, why, hits = route(f)
        out.append({"no": f.get("no"), "kind": f.get("kind"),
                    "route": path, "why": why, "blockers": hits,
                    "queued": queue_reason(f, path, hits)})
    return out


# ── 「아마도」 대기열 ──────────────────────────────────────────────────────
# 화이트리스트만 두면 목록이 **영원히 자라지 않는다.** 모르는 종류는 늘 CLEAN 으로
# 떨어지고, 그걸 본 사람이 없으니 아무도 목록에 올리지 않는다.
#
# 그래서 «아마도» 를 버리지 않고 **적어 둔다.** 적는 것은 결정이 아니다 —
# 이번 작업은 그대로 CLEAN 으로 가고, 기록만 남는다. 막히는 일이 없다.
#
# ★ 「아마도」를 사람이 선언하지 않는다. 판정기가 자동으로 넣는다.
#   AI 가 «이건 아마도 될 것 같은데» 라고 말할 자리를 만들지 않는다.
QUEUE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "data", "figure-candidates.jsonl")

# 대기열에 넣지 않는 차단 조건 — 「더 볼 것이 없는」 것들이다.
# 원문 작업·저작물은 규격이 바뀌어도 답이 같다. 쌓아 봐야 검토 대상이 아니다.
SETTLED = {"purpose_is_original", "copyrighted_art"}


def queue_reason(fig, path, hits):
    """이 그림을 대기열에 넣어야 하나. 넣을 이유(문자열) 또는 None."""
    kind = (fig.get("kind") or "").strip()
    if kind and kind not in KINDS:
        return "unknown-kind:%s" % kind
    if path == "CLEAN" and hits:
        keys = [k for k, _m in BLOCKERS if fig.get(k) and k not in SETTLED]
        if keys:
            return "blocked:%s:%s" % (kind, ",".join(keys))
    return None


def write_queue(rows, src):
    """대기열에 덧붙인다. 지우지 않는다 — 몇 번 나왔는지가 승격의 근거다."""
    items = [r for r in rows if r.get("queued")]
    if not items:
        return 0
    path = os.path.normpath(QUEUE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "a", encoding="utf-8") as f:
        for r in items:
            f.write(json.dumps({"kind": r["kind"], "no": r["no"],
                                "reason": r["queued"], "source": src,
                                "at": datetime.date.today().isoformat()},
                               ensure_ascii=False) + "\n")
    return len(items)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        print("  아는 종류: " + " · ".join(sorted(KINDS)))
        return 1

    spec = json.load(io.open(sys.argv[1], encoding="utf-8"))
    figs = spec.get("figures") or []
    if not figs:
        print("  · 그림이 없습니다")
        return 0

    rows = decide(figs)
    print("\n=== 그림 경로 판정 (%d개) ===" % len(rows))
    for r in rows:
        print("  %-3s  %-16s → %-6s  %s" %
              (r["no"], r["kind"] or "(없음)", r["route"], r["why"]))
        for b in r["blockers"]:
            print("            · %s" % b)

    n = {}
    for r in rows:
        n[r["route"]] = n.get(r["route"], 0) + 1
    print("\n  " + " · ".join("%s %d개" % (k, v) for k, v in sorted(n.items())))

    q = write_queue(rows, os.path.basename(sys.argv[1]))
    if q:
        print("  «아마도» %d건을 대기열에 적었습니다 — 이번 작업은 그대로 진행됩니다." % q)
        print("  쌓인 것을 보려면: python scripts/promote_kind.py")
    if n.get("REDRAW"):
        print("  REDRAW 는 figure.py 가 위상 검사를 통과해야 최종 확정됩니다 —"
              " 실패하면 자동으로 CLEAN 으로 내려갑니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
