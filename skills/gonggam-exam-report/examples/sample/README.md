# 표본의 출처 — 여기서 `examples/*.sample.json` 을 다시 뽑는다

`examples/` 의 표본 셋은 **손으로 쓴 파일이 아니다.** 이 폴더를 빌더에 태워 나온 것이다.
표본이 규격과 갈라지면 고치는 자리는 표본이 아니라 **여기**이고, 고친 뒤 아래 세 줄을 다시 돌린다.

> **규격 시연용이다.** 명지고 2026-1학기 중간고사는 실제 회차지만 지문·선지·해설은
> 판형을 재려고 새로 썼다. 학부모에게 나가는 자료가 아니다 — 배포하지 않는다.

## 다시 뽑기

`skills/gonggam-exam-report/` 에서 돈다. 크롬은 필요 없다.

```bash
python scripts/report_build.py examples/sample/exam.json              examples/sample/md examples/report.sample.json              --detail
python scripts/report_build.py examples/sample/exam.json              examples/sample/md examples/summary.sample.json             --summary
python scripts/report_build.py examples/sample/exam.seosulhyeong.json examples/sample/md examples/summary.seosulhyeong.sample.json --summary
```

## 무엇이 무엇을 내는가

| 소스 | 표본 | 무엇을 보이려고 |
|---|---|---|
| `exam.json` + `md/` | `report.sample.json` | 상세본 — 10섹션 8쪽. 킬러 4개가 모두 3단 카드 |
| `exam.json` + `md/` | `summary.sample.json` | 요약본 — 대표 문항이 **객관식**(11번) |
| `exam.seosulhyeong.json` + `md/` | `summary.seosulhyeong.sample.json` | 요약본 — 대표 문항이 **서술형**(25번). 〈조건〉 상자와 모범답안이 선다 |

`exam.seosulhyeong.json` 은 `exam.json` 에서 `killer_override` 차례와 학습 계획·가정 안내·
`next_action` 넷만 다르다. 문항 25개·배점·정답은 **같은 회차 그대로**다.

## 손댈 때 알아야 할 것 셋

- **MD 의 `meta` 에 `flags:["killer"]` 를 적지 않는다.** 표본 셋이 한 MD 를 나눠 쓰는데
  고르는 킬러가 서로 다르다(상세본 4개 · 요약본 1개). 적으면 「고른 것과 다르다」로 빌드가 막힌다.
  게이트가 「킬러문항 표시 없음」 주의를 내는 것은 이 때문이고, 그대로 둔다
- **원문 줄을 `①` 로 시작하지 않는다.** 줄머리의 `①` 은 선지로 읽힌다(`md-contract.md` § 4).
  어법 문항은 `Rarely ① does …` 처럼 표시를 줄 안쪽에 둔다 — 줄머리에 두었더니 지문 두 줄이
  선지로 빨려 들어가 킬러 카드의 발췌가 잘렸다
- **「푸는 순서」의 `★` 는 한 줄에만.** `→` 는 줄 끝 결론을 가르고, 단계가 **정확히 셋**일 때만
  3단 카드가 된다 (`md-contract.md` § 3-2)
