# report.json 스키마 (정본)

`render_report.py` 가 읽는 유일한 입력이다. HTML 은 쓰지 않는다.

**이 파일을 손으로 쓰지 않는다.** Claude 가 쓰는 것은 `exam.json` 과 MD 2종이고,
`report_build.py` 가 그 둘을 읽어 이 파일을 짓는다 (`md-contract.md`). 그래서 아래 표에는
«사람이 exam.json 에 적는 칸» 과 «빌더가 계산해 넣는 칸» 이 섞여 있다 — 어느 쪽인지
칸마다 적어 두었다. 빌더가 넣는 칸을 exam.json 에 적어도 덮어쓴다.

표본: `examples/report.sample.json` (명지고 고1 2026-1학기 중간 영어 25문항).
스키마를 고치면 표본도 같이 고치고 렌더를 다시 돌린다. 둘이 갈라지면 규격이 죽는다.

> ⚠ 2026-09-23 현재 표본이 갈라져 있다. `render_report.py examples/report.sample.json out/`
> 은 «REPEAT 대상이 report.json 에 없습니다: steps_flow» 로 실패한다 — 표본에 `steps_flow` ·
> `em` · `key` · `num` · `unit` · `source` 가 없다. 표본을 다시 빌드해야 한다.

---

## 최상위

| 키 | 필수 | 누가 | 뜻 |
|---|---|---|---|
| `brand` | ✔ | 사람 | 학원명·로고·테마 |
| `meta` | ✔ | 사람 + 빌더 | 학교·학년·학기·과목·범위. `total_items` · `total_points` 는 **빌더가 세서 덮어쓴다** |
| `cover` | ✔ | 사람 | `subtitle` · `tags` 둘 다 없으면 빌드가 막힌다 (요약본 판형은 안 쓰지만 **검사는 공통**이다) |
| `sections` | ✔ | 빌더 | 실을 섹션 목록 (**순서는 템플릿이 정한다**) |
| `items` | ✔ | 사람 + 빌더 | 문항 배열 |
| `types` `chapters` `radar` `difficulty.detail` `issues` `killer` `killer_selection` `fill_blocks` | | **빌더** | 아래 § 빌더가 채우는 칸 |
| `types_note` `chapters_note` `emphasis` `killer_override` `next_action` | | **사람** | exam.json 최상위에 적는다 |
| 나머지 | 섹션에 따라 | 사람 | 고른 섹션이 쓰는 것만 있으면 된다 |

`sections` 는 exam.json 에 적어 고를 수도 있다 — 상세본은 `sections`, **요약본은 `sections_summary`**.
안 적으면 기본값이 쓰인다. 빌더가 아는 섹션은 닫힌 목록이고, 밖의 이름을 적으면 막는다:

```
overview · items · type-chart · chapter-ratio · difficulty · killer
issues · grade-cut · study-plan · parent-note · summary
```

`issues` 는 적지 않아도 된다 — 이슈가 있으면 빌더가 `killer` 뒤에 넣고, 없으면 뺀다.

> 요약본 판형에는 `<!-- SECTION:radar -->` 자리가 하나 더 있는데 **위 목록에 없어 지금은
> 켤 수 없다.** `sections_summary` 에 `radar` 를 적으면 빌더가 「템플릿에 없는 섹션」으로
> 막는다. 레이다 좌표(`radar`)는 그래도 언제나 계산해 둔다.

### 계산하지 않는다

아래는 **렌더러가 만든다.** report.json 에 적지 않는다 — 적어도 덮어쓴다.

- 막대 너비 (`types[].width`, `chapters[].width`)
- 난이도 5칸 (`difficulty.bins`) — `items[].difficulty` 를 직접 센다
- 킬러 카드의 «있을 때만» 상자 (`excerpt_box` · `choice_box` · `given_box` · `cond_box` ·
  `wrong_box` · `answer_box` · `answer_block_box` · `answer_label`) — 템플릿 지시자에
  «만약» 이 없어서, 조건부 상자를 **한 칸짜리 목록**으로 바꿔 둔다
- 섹션 번호 · 쪽번호 · 총페이지

---

## brand

```json
{"academy":"공감에듀","theme":"clean","logo_path":"logo.png","logo_bg":"light"}
```

| 키 | 값 |
|---|---|
| `academy` | 표지·꼬리말에 찍히는 이름 |
| `theme` | **정본은 `assets/themes/*.css` 폴더다.** 지금 있는 것 여섯 — `clean` · `gonggam` · `gonggam-navy` · `mono` · `nelt` · `warm`. `python scripts/render_report.py --list-themes` 가 세어서 말한다 |
| `logo_path` | 없으면 `null` → 학원명 텍스트로 대체 |
| `logo_bg` | `light` = 흰 박스로 감싼다 · `dark` = 그대로 |

## meta

```json
{"school":"명지고등학교","grade":"H1","grade_label":"고1","term":"2026-1학기 중간고사",
 "subject":"영어","year":"2026","total_items":25,"total_points":100,"scope":"교과서 1~3과 …"}
```

`total_items` · `total_points` 는 **게이트가 `items` 와 대조한다.** 어긋나면 차단된다.

## sections

상세본 기본값 (아홉) — `items` · `chapter-ratio` · `study-plan` · `parent-note` 가 여기 있다.

```json
["overview","items","type-chart","chapter-ratio","difficulty",
 "killer","study-plan","parent-note","summary"]
```

요약본 기본값 (다섯).

```json
["overview","type-chart","difficulty","killer","summary"]
```

여기 없는 섹션은 HTML 에서 **통째로 사라진다.** 번호는 남은 것에 1부터 다시 매겨진다.
빌더가 모르는 이름을 적으면 **빌드가** 막히고, 템플릿에 없는 이름이 여기까지 오면
**렌더가** 실패한다 — 조용히 무시하지 않는다. `grade-cut` 은 켤 때 직접 적는다.

## items

```json
{"no":11,"type":"빈칸추론","points":5,"difficulty":"상","source":"교과서 3과",
 "answer":"2","basis":"binkan:원칙2 후반 위치 → 난도 상","confidence":"high"}
```

| 키 | 필수 | 비고 |
|---|---|---|
| `no` `type` `points` `source` `answer` | ✔ | |
| `difficulty` | ✔ | **`상·중상·중·중하·하` 다섯 중 하나.** 다른 값이면 차단 |
| `basis` | ✔ | 유형 판정 근거 한 줄. **없으면 차단** (§ SKILL.md 4-1) |
| `confidence` | ✔ | `high` · `low`. `low` 가 있으면 확인 기록이 있어야 통과 |
| `answer_source` | | `추론` 이면 주의로 잡힌다 |
| `note` | | 내부 메모 |

`basis` · `confidence` · `answer_source` · `note` 는 **배포본에서 자동으로 빠진다.**
`--internal` 로 렌더하면 남는다.

`items[].answer` 는 **exam.json 의 값 그대로가 아니다.** 문항표에 찍을 «보여 주는 값» 이라,
서술형이거나 「본문참조」 같은 빈 답이면 **«서술형»** 한 낱말로 바뀐다 (`md-contract.md` § 8).
`points` 는 소수 그대로 간다 — 3.4 를 3 으로 깎지 않는다.
`stem` · `choices` 는 exam.json 에 적어도 report.json 에 실리지 않는다. 발문과 선지는
`기출문제.md` 에서 읽어 킬러 카드에만 담는다.

## 섹션별 데이터

| 섹션 | 쓰는 키 |
|---|---|
| `overview` | `overview.desc` · `.highlight` · `.cards[{label,value,num,unit,key}]` · `meta.scope` |
| `items` | `items` |
| `type-chart` | `types[{name,count,points,em}]` · `types_note` |
| `chapter-ratio` | `chapters[{name,count,points,em}]` · `chapters_note` · `chapter_desc` |
| `difficulty` | `difficulty.summary` · `.discriminator` (`.bins` 는 렌더러가, `.detail` 은 빌더가) |
| `killer` | `killer[{no,kind,title,source,answer,excerpt,givens,choices,conditions,why,wrong_reasons,steps_flow,concepts,selection}]` — 상세본 **3~5개**, 요약본 **1개** |
| `issues` | `issues[{no,kind,reason,excerpt}]` — **요구하는 데이터가 없다.** 빈 목록이면 빌더가 섹션째 뺀다 |
| `grade-cut` | `grade_cut{enabled,basis,disclaimer,cuts[{grade,score,desc}]}` |
| `study-plan` | `study_plan[{week,focus,todo}]` · `study_plan_desc` |
| `parent-note` | `parent_note[]` |
| `summary` | `summary{quote,desc}` · `disclaimer` |

요약본 판형이 더 쓰는 것 — `next_action`(학원이 할 일 한 줄) · `killer.0.no` · `killer.0.kind` ·
`chapters.0.name` · `chapters.0.points`. 채움 자리(`fill-plan` · `fill-home` · `fill-difficulty`)는
`study_plan` · `parent_note` · `difficulty.detail` 을 **최상위에서 곧바로** 읽는다.

## grade_cut — 기본은 끈다

```json
{"enabled":false}
```

켤 때는 `basis`(산출 근거)와 `disclaimer`(예상치 고지)가 **둘 다** 있어야 게이트를 통과한다.
근거 없는 숫자가 학원 이름으로 나가는 것을 막는 장치다.

---

## 빌더가 채우는 칸 (2026-09-23)

지면 문법은 `references/layout-grammar.md` 가 정본이다. **데이터 쪽 계약만** 여기 적는다.

> **참/거짓이 아니라 문자열이다.** `em` · `key` 는 `class="{{em}}"` 자리에 그대로 꽂힌다.
> 템플릿 지시자에는 «만약» 이 없으므로 참/거짓을 받아 갈라 그릴 길이 없고, 값이 빠진 줄이
> 하나라도 있으면 `{{em}}` 이 남아 렌더가 막힌다. 그래서 **빈 값이라도 모든 줄에 온다.**
> (`layout-grammar.md` § 6 은 아직 `emphasis: true` 라 적혀 있다 — 그 줄은 낡았다.)

### 강조 — 칠할 자리는 사람이 지목한다

| 칸 | 어디에 | 누가 넣나 | 값 |
|---|---|---|---|
| `emphasis` | **exam.json** 최상위 | **사람(분석자)** | `{"types":"어법","chapters":"시험범위 밖 지문"}` — 칠할 막대를 이름으로 지목 |
| `em` | `types[]` · `chapters[]` · `radar.axes[]` 의 **모든 줄** | 빌더 | `""` 또는 `"em"` |
| `num` · `unit` | `overview.cards[]` 의 **모든 카드** | 빌더 | `"38문항"` → `num:"38"` · `unit:"문항"` |
| `key` | `overview.cards[]` 의 **모든 카드** | 빌더 | `""` 또는 `"key"` |

`key:"key"` 가 붙는 카드는 **값이 숫자로 시작하지 않는 카드**다 — 국어 목업의
「이번 시험의 갈림길 / `<보기>` 조합 선지」가 그것이다. 그런 카드가 하나도 없어도 된다
(영어·수학 목업이 그렇다). 둘 이상이면 막는다.

**1위를 자동으로 칠하지 않는다.** 본본은 1위(분사 10개)를 두고 4위(접속사·관계사 4개)를 칠했다 —
1위는 스스로 교정한 것이라 문제가 아니었고, 4위는 한 지문에 몰려 전부 놓친 것이라 문제였다.
개수가 아니라 뜻이 강조를 정한다. 그래서 **사람이 지목하고, 지목이 없으면 아무 것도 칠하지 않는다.**

막는 자리 둘 —

- 없는 줄을 지목하면 **막고 있는 줄을 늘어놓는다.** 조용히 안 칠하고 넘어가지 않는다
- «말» 카드가 둘 이상이면 **막는다.** 넷 중 둘을 칠하면 둘 다 안 보인다

요약본은 유형 상위 3줄만 싣는다. 지목한 유형이 그 밖이면 **자르기 전 목록에서 확인**하고
「요약본에는 안 칠해집니다」를 알림으로 낸다 — 이름이 틀린 것과 순위에 밀린 것은 다른 일이다.

### 막대 아래 한 문장 — `types_note` · `chapters_note`

exam.json 최상위에 **사람이** 적는다. 숫자만 두면 읽는 사람이 결론을 못 낸다 —
「칠한 줄이 왜 그 줄인가」를 한 문장으로 적는 자리다. 빌더는 마크다운 표시만 벗겨 옮기고
**지어내지 않는다.** 안 적으면 빈 문자열로 가고 그 줄은 종이에서 비어 보인다.

```json
"types_note": "칠한 줄은 배점이 가장 많은 추론이 아니라 문제해결입니다. 네 갈래 가운데 문항이 다섯으로 가장 적은데 그 가운데 셋이 상입니다."
```

### `difficulty.detail` — 난이도 5단을 펼친 것

세는 일이라 사람이 쓸 것이 없다. **문항이 하나도 없는 칸은 빼고** 담는다.

```json
"detail": [{"label":"상","count":5,"points":27.6,"nos":"19·20·23·24·25번"}]
```

요약본 채움 자리 `fill-difficulty` 가 이것을 읽는다. 상세본 판형은 아직 안 읽는다.

### `radar` — 유형별 배점을 레이다 좌표로

유형 막대와 **같은 데이터를 다른 꼴로** 본다. 판형은 계산을 못 하므로 좌표를 여기서 낸다.
viewBox `0 0 200 200` · 중심 (100,100) · 반지름 72 · 12시에서 시계 방향.

```json
"radar": {"ok":"1", "points":"100.0,28.0 …", "top":"31.6",
          "rings":[{"points":"…"}],  "spokes":[{"x2":"…","y2":"…"}],
          "axes":[{"name":"문학","value":"31.6","count":9,
                   "lx":"100.0","ly":"18.8","anchor":"middle","em":""}]}
```

- `ok` 는 참/거짓이 아니라 `"1"` 또는 `""` 다 — 판형이 `data-ok` 에 그대로 꽂는다
- **축이 셋 미만이면 그리지 않는다.** `ok` 를 비우고 나머지를 빈 목록으로 보낸다.
  둘로는 삼각형도 안 된다
- 요약본은 `types` 를 상위 3개로 자른 **뒤** 편다. 그래서 요약본 레이다는 늘 삼각형이고,
  상세본과 축 개수가 다르다
- 축 이름은 고리 **밖**(1.17배)에 두고, 왼쪽 반원이면 `anchor:"end"` 로 붙인다

### `fill_blocks` — 요약본에서 남는 자리에 넣을 것

`--summary` 일 때만 나간다. **우선순위 순서**로 담기고, 높이를 재서 켜는 것은 렌더러다.

```json
{"key":"study-plan", "title":"다음 학습 전략", "section":"fill-plan",
 "rows":[{"week":"1~2주","focus":"서술형","todo":"…"}]}
```

| 칸 | 뜻 |
|---|---|
| `key` | **상세본 섹션 이름.** 「이미 섹션으로 실렸나」를 이 이름으로 본다 |
| `section` | **요약본 판형의 자리 이름** (`fill-plan` · `fill-home` · `fill-difficulty`). `key` 와 **다르다** |
| `title` | 사람이 읽을 이름. 렌더 기록에 남는다 |
| `rows` | 우선순위를 정할 때 쓴 줄. **판형은 이것을 읽지 않는다** — 최상위 `study_plan` · `parent_note` · `difficulty.detail` 을 곧바로 읽는다. 그래서 `rows` 를 앞 2주로 줄여도 종이에는 4주가 다 나간다 (`md-contract.md` § 7) |

`key` 하나로 자리를 찾던 때가 있었고, 그때 셋 다 「켤 자리 없음」으로 빠져 요약본 아래가
53mm 비어도 아무 것도 안 켜졌다 (수학 목업에서 드러났다 — 영어는 이슈 문항이 그 자리를
채워 안 보였다). **그래서 자리 이름을 따로 받는다.**

최소 높이는 `summary-spec.md` § 4-1 의 실측표가 정본이고, 없으면 블록의 `min_mm` 을 쓴다.
둘 다 없으면 그 블록은 뺀다 — 높이를 짐작해서 골랐다가 한 장을 넘기면 안 넣은 것만 못하다.

### 킬러 카드 — `kind` · `source` · `steps_flow` · `selection`

| 칸 | 값 |
|---|---|
| `kind` | `객관식` · `서술형`. 판형이 두 꼴을 갈라 그린다 (`subject-axes.md` § 0-1) |
| `source` | 문항의 `source` 를 그대로 옮긴 것 — § 4 카드 머리띠 오른쪽 «어디서 온 것인가» 자리. **지금 판형은 아직 안 읽는다** |
| `answer` | 객관식은 정답 번호, 서술형은 «모범답안 한 줄» |
| `steps_flow` | 「푸는 순서」 한 줄을 «하는 일 → 결론» 으로 가른 것 (아래) |
| `steps` | 가르기 전 원문 줄. 판형은 안 읽는다 — 옛 판형이 쓰던 자리를 남겨 둔 것이다 |
| `selection` | `기계 선정` · `수동 선정`. 카드마다 남는다 |

```json
"steps_flow": [{"text":"인수정리로 a 를 구한다", "conclusion":"P(3)=0 으로 옮긴다",
                "em":"", "value":"인수정리로 a 를 구한다 → P(3)=0 으로 옮긴다"}]
```

- 네 칸이 **모든 줄에** 온다. 화살표가 없으면 `conclusion` 은 빈 문자열이다 — 지어내지 않는다
- `em` 은 `""` 또는 `"em"`. MD 의 `★` 가 찍힌 줄에 붙는다 — **하나뿐이어야 하는데
  둘 이상을 막는 검사가 지금은 새고 있다** (`md-contract.md` § 3-2)
- `value` 는 가르기 전 줄 그대로. 옛 판형의 `{{value}}` 를 살려 둔 것이다

MD 쪽 표기는 `md-contract.md` § 3-2 가 정본이다.

### `killer_selection` — 누가 어떤 규칙으로 골랐나

```json
{"mode":"수동 선정", "nos":[36,34,16,25,31],
 "rule":"exam.json 의 killer_override", "machine_nos":[36,37,38,34,16]}
```

수동이면 고지 줄(`disclaimer`)에 한 문장이 덧붙는다. 반년 뒤에 «왜 이 문항이 킬러였지» 를
여기서 읽는다 (`md-contract.md` § 6-1).

---

## 템플릿 지시자 (템플릿을 고칠 때만 본다)

| 지시자 | 하는 일 |
|---|---|
| `<!-- SECTION:key -->…<!-- /SECTION:key -->` | `sections` 에 없으면 제거 |
| `<!-- REPEAT:path -->…<!-- /REPEAT:path -->` | 목록 되풀이. 중첩 가능 (`killer` 안의 `steps_flow`) |
| `{{a.b}}` | 치환. **못 채우면 렌더 실패** |
| `{{#SEC}}` | 섹션 번호 자동 |
| `{{PAGE_NUM}}` `{{TOTAL_PAGES}}` | 쪽번호 자동 |
| `{{@n}}` `{{@index}}` | REPEAT 안에서 1부터 / 0부터 |
| `{{value}}` | 문자열 목록(`parent_note` 등)의 각 항목 |

**템플릿은 둘이다** — 상세본 `assets/template.html`, 요약본 `assets/template_summary.html`.
둘 다 같은 지시자 계약을 쓴다. `--summary` 가 어느 쪽을 쓸지 고른다.
요약본 규격은 `references/summary-spec.md` 가 정본이다.

**학원이 늘어도 템플릿은 안 늘린다. 테마 css 만 늘린다.**
