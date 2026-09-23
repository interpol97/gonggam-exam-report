# report.json 스키마 (정본)

`render_report.py` 가 읽는 유일한 입력이다. **Claude 가 만드는 것은 이 파일 하나뿐이다.**
HTML 은 쓰지 않는다.

표본: `examples/report.sample.json` (명지고 고1 2026-1학기 중간 영어 25문항).
스키마를 고치면 표본도 같이 고치고 렌더를 다시 돌린다. 둘이 갈라지면 규격이 죽는다.

---

## 최상위

| 키 | 필수 | 뜻 |
|---|---|---|
| `brand` | ✔ | 학원명·로고·테마 |
| `meta` | ✔ | 학교·학년·학기·과목·문항수·총점·범위 |
| `cover` | ✔ | 표지 부제·태그 |
| `sections` | ✔ | 실을 섹션 목록 (**순서는 템플릿이 정한다**) |
| `items` | ✔ | 문항 배열 |
| 나머지 | 섹션에 따라 | 고른 섹션이 쓰는 것만 있으면 된다 |

### 계산하지 않는다

아래는 **렌더러가 만든다.** report.json 에 적지 않는다 — 적어도 덮어쓴다.

- 막대 너비 (`types[].width`, `chapters[].width`)
- 난이도 5칸 (`difficulty.bins`) — `items[].difficulty` 를 직접 센다
- 섹션 번호 · 쪽번호 · 총페이지

---

## brand

```json
{"academy":"공감에듀","theme":"clean","logo_path":"logo.png","logo_bg":"light"}
```

| 키 | 값 |
|---|---|
| `academy` | 표지·꼬리말에 찍히는 이름 |
| `theme` | `clean` · `gonggam` · `mono` · `warm` (`assets/themes/*.css`) |
| `logo_path` | 없으면 `null` → 학원명 텍스트로 대체 |
| `logo_bg` | `light` = 흰 박스로 감싼다 · `dark` = 그대로 |

## meta

```json
{"school":"명지고등학교","grade":"H1","grade_label":"고1","term":"2026-1학기 중간고사",
 "subject":"영어","year":"2026","total_items":25,"total_points":100,"scope":"교과서 1~3과 …"}
```

`total_items` · `total_points` 는 **게이트가 `items` 와 대조한다.** 어긋나면 차단된다.

## sections

```json
["overview","items","type-chart","chapter-ratio","difficulty",
 "killer","grade-cut","study-plan","parent-note","summary"]
```

여기 없는 섹션은 HTML 에서 **통째로 사라진다.** 번호는 남은 것에 1부터 다시 매겨진다.
템플릿에 없는 키를 적으면 렌더가 실패한다 — 조용히 무시하지 않는다.

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

## 섹션별 데이터

| 섹션 | 쓰는 키 |
|---|---|
| `overview` | `overview.desc` · `.highlight` · `.cards[{label,value}]` · `meta.scope` |
| `items` | `items` |
| `type-chart` | `types[{name,count,points}]` |
| `chapter-ratio` | `chapters[{name,count,points}]` · `chapter_desc` |
| `difficulty` | `difficulty.summary` · `.discriminator` |
| `killer` | `killer[{no,title,why,steps[],concepts[]}]` — **3~5개** |
| `grade-cut` | `grade_cut{enabled,basis,disclaimer,cuts[{grade,score,desc}]}` |
| `study-plan` | `study_plan[{week,focus,todo}]` · `study_plan_desc` |
| `parent-note` | `parent_note[]` |
| `summary` | `summary{quote,desc}` · `disclaimer` |

### grade_cut — 기본은 끈다

```json
{"enabled":false}
```

켤 때는 `basis`(산출 근거)와 `disclaimer`(예상치 고지)가 **둘 다** 있어야 게이트를 통과한다.
근거 없는 숫자가 학원 이름으로 나가는 것을 막는 장치다.

---

## 템플릿 지시자 (템플릿을 고칠 때만 본다)

| 지시자 | 하는 일 |
|---|---|
| `<!-- SECTION:key -->…<!-- /SECTION:key -->` | `sections` 에 없으면 제거 |
| `<!-- REPEAT:path -->…<!-- /REPEAT:path -->` | 목록 되풀이. 중첩 가능 (`killer` 안의 `steps`) |
| `{{a.b}}` | 치환. **못 채우면 렌더 실패** |
| `{{#SEC}}` | 섹션 번호 자동 |
| `{{PAGE_NUM}}` `{{TOTAL_PAGES}}` | 쪽번호 자동 |
| `{{@n}}` `{{@index}}` | REPEAT 안에서 1부터 / 0부터 |
| `{{value}}` | 문자열 목록(`parent_note` 등)의 각 항목 |

**템플릿은 둘이다** — 상세본 `assets/template.html`, 요약본 `assets/template_summary.html`.
둘 다 같은 지시자 계약을 쓴다. `--summary` 가 어느 쪽을 쓸지 고른다.
요약본 규격은 `references/summary-spec.md` 가 정본이다.

**학원이 늘어도 템플릿은 안 늘린다. 테마 css 만 늘린다.**
