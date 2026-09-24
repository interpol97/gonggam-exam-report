# 이어서 작업하기 — 기출 분석 리포트 스킬

다른 컴퓨터에서 이 스킬을 이어 만들 때 **이 문서부터** 읽는다.
마지막 갱신 2026-09-23.

---

## 0. 받아 오기

```bash
git clone https://github.com/interpol97/gonggam-claude-plugins.git C:/dev/apps/gonggam-claude-plugins
cd C:/dev/apps/gonggam-claude-plugins && git pull
```

이미 받아 둔 컴퓨터라면 `git pull` 하나면 된다.

클로드 코드에서 스킬로 쓰려면 —

```
/plugin marketplace add interpol97/gonggam-claude-plugins
/plugin install gonggam-exam-report@gonggam-edutech
```

이미 깔려 있으면 `/plugin marketplace update` 로 최신을 당긴다.

### 필요한 것

| | |
|---|---|
| Python | PyMuPDF(`fitz`) · Pillow · fonttools |
| 크롬 | 헤드리스로 PDF 를 굽는다. 찾는 자리는 `render_pdf.py` 에 있고 `GONGGAM_CHROME` 으로 덮어쓸 수 있다 |
| 글꼴 | `assets/fonts/` 에 동봉돼 있다. 따로 깔 것 없다 |

---

## 1. 이 스킬이 서 있는 자리 (위계)

```
plugins/gonggam-exam-report/
├─ HANDOFF.md                  ← 지금 읽는 문서
├─ .claude-plugin/plugin.json
└─ skills/gonggam-exam-report/
   ├─ SKILL.md                 ★ 본체. 일하는 순서가 여기 있다
   ├─ references/              ★ 규격 정본. 코드보다 이쪽이 먼저다
   │   ├─ layout-grammar.md      지면 문법 11개 절 — 무엇을 어디에 놓는가
   │   ├─ report-schema.md       report.json 계약
   │   ├─ md-contract.md         MD 2종이 기계에 주는 약속 (★ · → 포함)
   │   ├─ md-outputs.md          MD 5종 규격
   │   ├─ summary-spec.md        요약본 A4 한 장 규격 (§4-1 채움 실측표)
   │   ├─ asking.md              문진 일곱 — Q3 테마 선택지
   │   ├─ subject-axes.md        과목별 분석축 (영·수·국·과)
   │   ├─ figures.md             그림 세 층
   │   ├─ figure-routing.md      다시 그릴지 원본을 쓸지 — 닫힌 목록
   │   ├─ ocr-intake.md          사진·스캔 판독 규약
   │   ├─ glyphs.md              동봉 폰트에 있는 글자 / 없는 글자
   │   └─ gates.md               게이트 목록
   ├─ scripts/
   │   ├─ report_build.py        exam.json + MD → report.json
   │   ├─ render_report.py       report.json → HTML + PDF (쪽수 2패스 실측)
   │   ├─ render_pdf.py          헤드리스 크롬 · 쪽번호 도장
   │   ├─ preview.py           ★ HTML 만 뽑는다 (0.2초). 디자인 고를 때
   │   ├─ gate_check.py          검사 60여 개
   │   ├─ subset_font.py         회차마다 글꼴 서브셋
   │   ├─ crop_figures.py · clean_figure.py · figure_route.py · promote_kind.py
   │   └─ outname.py             파일 이름 규격 (자료제작소와 공용)
   ├─ assets/
   │   ├─ template.html          상세본 판형
   │   ├─ template_summary.html  요약본 판형 (A4 한 장)
   │   ├─ themes/                clean · gonggam · gonggam-navy · mono · nelt · warm
   │   └─ fonts/                 NotoSansKR 400 · 700 · 900
   ├─ gates/                     negative.py · checks.py (양성 대조)
   └─ examples/                  표본 json
```

**고칠 때 순서** — 규격(`references/`) → 코드(`scripts/`) → 판형(`assets/`) → 게이트(`gates/`).
규격을 안 고치고 코드만 고치면 다음 사람이 규격을 믿고 되돌린다.

---

## 2. 한 벌 돌리기

```bash
SK=plugins/gonggam-exam-report/skills/gonggam-exam-report

python $SK/scripts/report_build.py  exam.json md report.json  --detail
python $SK/scripts/report_build.py  exam.json md summary.json --summary
python $SK/scripts/render_report.py report.json  out/
python $SK/scripts/render_report.py summary.json out/ --summary
python $SK/scripts/gate_check.py    out/ report.json --exam exam.json --md md
```

**디자인만 볼 때는 굽지 않는다** — 한 벌에 57초다.

```bash
python $SK/scripts/preview.py report.json out.html --theme=nelt
python $SK/scripts/render_report.py --list-themes
```

`preview.py` 는 쪽수·채움·쪽번호·글꼴 서브셋이 **전부 빠져 있다.**
모양을 고르는 데만 쓰고, 고른 뒤에는 반드시 위 다섯 줄을 태운다.

---

## 3. 지금까지 확인한 것

| 과목 | 회차 | 결과 |
|---|---|---|
| 영어 | 명지고2 2026-1학기 기말 (**실물**) | 상세본 9쪽 · 요약본 1쪽 · 게이트 통과 |
| 수학 | 예시고1 중간 (목업) | 상세본 8쪽 · 요약본 1쪽 · 게이트 통과 |
| 국어 | 목업고2 기말 (목업) | 상세본 9쪽 · 요약본 1쪽 · 게이트 통과 |
| 과학 | — | **아직 한 벌도 안 태웠다** |

목업 작업방은 스크래치패드에 있고 깃에 안 들어간다. 다시 만들려면
`mockmath/convert.py` 꼴을 본보기로 삼는다(HANDOFF 밖이라 없으면 새로 쓴다).

---

## 4. 오늘 배운 것 — 되풀이하지 말 것

### 주석은 안전한 자리가 아니다 ★

렌더러·서브세터·게이트 **셋 다 주석을 본문과 구별하지 않는다.** 오늘 네 번 당했다.

| 어디 | 무엇이 샜나 |
|---|---|
| 판형 주석의 `⛔` | 서브세터가 「폰트에 없는 글자」로 잡아 렌더 실패 |
| 테마 주석의 `✗` | 같음 |
| 판형 주석의 `{{FONT_CSS}}` | 렌더러가 주석 안까지 치환 → 글꼴 237KB 가 주석에 들어가 파일이 두 배 |
| 게이트가 `<style>`·주석을 본문으로 셈 | `.bar-row.em{…}` 이라는 **선언**을 「강조된 막대」로 세어 멀쩡한 리포트를 차단 |

주석에 **치환자도 특수 기호도 적지 않는다.** 설명이 필요하면 말로 푼다.

### 「영어에서 됐으니 됐다」가 안 통하는 자리

- **서술형 판정** — 유형 이름으로만 보면 수학(「문제해결」)·국어(「문법」)의 서답형이 객관식이 된다.
  지금은 «유형이 말해 주거나, 모범답안이 있고 선지가 없으면» 서술형이다
- **`<보기>`** — 영어는 `ⓐ~ⓩ`, 국어는 `ㄱ·ㄴ·ㄷ·ㄹ`. 둘 다 읽는다

### 검사를 지으면 반드시 양성 대조

오늘 이것도 두 번 틀렸다.

- 「가로로 넘쳤나」 검사를 짓고 양성 대조가 **통과**했다 — flex 가 넘치는 대신
  옆 칸을 짓눌러 버텨서 x 좌표가 그대로였다. 「짓눌림」을 재는 검사로 바꿨다
- 그 짓눌림 검사가 선지 번호 `①②③④` 를 짓눌림으로 오인해 **멀쩡한 영어 리포트를 막았다.**
  한글 음절만 세도록 좁혀 해결

**잡는 것과 안 잡는 것을 둘 다 확인한다.**

### 강조는 한 곳만, 그리고 1위를 자동으로 칠하지 않는다

원장님 보고서는 1위(분사 10개)를 두고 4위(접속사·관계사 4개)를 칠했다.
1위는 스스로 교정한 것이라 문제가 아니었고, 4위는 한 지문에 몰려 전부 놓친 것이라 문제였다.
**칠할 줄은 사람이 `exam.json` 의 `emphasis` 로 지목한다.** 지목이 없으면 아무 것도 안 칠한다.

---

## 5. 다음에 할 일

우선순위 순.

1. **과학 한 벌을 태운다** — 전과목이라 말하려면 남은 한 과목이다. 그림 경로에서 터질 것이다
2. **`examples/report.sample.json` 이 더는 렌더되지 않는다** —
   `steps_flow`·`em`·`key`·`num`·`unit`·`source` 가 표본에 없다. 소스에서 다시 빌드해야 한다
3. **게이트가 새 칸을 안 잰다** — `em`·`key`·`radar`·`steps_flow`·`fill_blocks` 에 회귀 잠금이 없다
4. **`fill_blocks[].rows` 의 「앞 2주만」이 종이까지 못 간다** —
   판형이 최상위 `study_plan` 을 돌아서 4줄이 다 나간다
5. **`summary-spec.md` §3·§4·§5 가 새 판형과 어긋난다** (§4-1 만 갱신됐다)
6. **`killer[].source`** 를 상세본 판형이 아직 안 읽는다 (§4 카드 머리띠 오른쪽)
7. **`✗`(U+2717) 가 동봉 폰트에 없다** — `✓` 는 있다. `glyphs.md` 참조

---

## 5.5 배포 — 이 플러그인만 따로 내보낸다

공감 플러그인 저장소에는 자료제작소·문제풀이 논리가 함께 있다. 통째로 주지 않는다.
`git subtree` 로 **이 폴더만** 밀어낸다. 원본은 하나로 둔다.

```bash
cd C:/dev/apps/gonggam-claude-plugins

# ① 공용 파일명 규격을 다시 복사한다 — 이걸 빼먹으면 배포판이 옛 규격을 들고 나간다
cp plugins/gonggam-material-studio/assets/filename_check.py \
   plugins/gonggam-exam-report/skills/gonggam-exam-report/assets/filename_check.vendored.py

# ② 이 폴더만 잘라 ③ 배포 저장소로
git subtree split --prefix=plugins/gonggam-exam-report -b dist/exam-report -f
git push https://github.com/interpol97/gonggam-exam-report.git dist/exam-report:main -f
```

**①을 건너뛰지 않는다.** `outname.py` 는 옆에 자료제작소가 있으면 그 정본을 쓰고,
없으면 동봉본을 쓴다. 배포판을 받은 사람에게는 **동봉본이 유일한 규격**이라,
복사를 빼먹으면 그 사람만 옛 규칙으로 이름을 짓는다. 두 벌이 갈라지는 자리가 여기다.

확인 — 배포판이 **혼자서도 도는가**:

```bash
# 자료제작소가 없는 자리를 흉내 내서 돌려 본다
python -c "import sys; sys.path.insert(0,'scripts'); import outname; print(outname._shared().__file__)"
```

`filename_check.vendored.py` 가 나오면 맞다. 원본 자리에서는 `filename_check.py`(정본)가 나와야 한다.

배포 저장소: `interpol97/gonggam-exam-report` (공개).
받는 쪽은 `/plugin marketplace add interpol97/gonggam-exam-report` 한 줄이면 된다.

---

## 6. 손대면 안 되는 자리

- **`.page-mark` 의 «N / M 페이지»** — 두 검사기가 이 한 줄을 **글자 그대로** 읽는다.
  태그로 가르면 그 순간 둘이 나란히 눈을 감는다. 쪽번호 굵기는 `render_pdf.py` 의 도장에서 가른다
- **`dbox` · `card` 같은 class 이름** — 게이트가 이 이름으로 개수를 센다
- **`d-상` 은 두 곳에서 뜻이 다르다** — 상세본은 배지(`.badge.d-상`), 요약본은 칸 전체(`.dbox.d-상`).
  테마에서 색을 줄 때 반드시 `.badge` 로 좁힌다
- **한 장에 몇 줄이 들어가는지 추측하지 않는다.** 쪽 나눔은 브라우저가 하고 쪽번호는 PDF 를 재서 넣는다
