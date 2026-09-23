# 공감에듀 기출 분석 리포트 (gonggam-exam-report)

학교 기출 시험지를 받아 **여섯 개 파일**을 낸다. 리포트 한 장으로 끝내지 않는다.

```
시험지 (PDF · 사진 · 스캔)
   ↓
① 기출문제.md   ② 기출정답해설.md
③ 분석_유형별.md ④ 분석_출제별.md ⑤ 분석_난이도별.md
⑥ 리포트 HTML + PDF  (배포본 · 내부본)
```

영어 · 수학 · 국어 · 과학 전과목. Claude Opus 사용을 전제로 짜여 있다.

---

## 설계의 한 줄

> **판단은 Opus 가, 조판과 검증은 기계가.**

| 일 | 누가 |
|---|---|
| 시험지 판독 (사진 포함) · 유형 분류 · 난이도 판정 | Opus |
| 번호 · 쪽수 · 조판 · 치환 | `render_report.py` |
| 발행 가부 | `gate_check.py` (통과 못 하면 차단) |

**Claude 는 HTML 을 쓰지 않는다.** 파이썬 문자열로 HTML 을 조립하면
`\frac` 이 폼피드가 되고 `\angle` 이 벨 문자가 된다. 조립을 안 하면 깨질 경로가 없다.

---

## 구조

```
gonggam-exam-report/
└── skills/gonggam-exam-report/
    ├── SKILL.md                    ← Claude 가 읽는 지침
    ├── references/
    │   ├── subject-axes.md         ← 과목별 분석축 (영·수·국·과) 정본
    │   ├── report-schema.md        ← report.json 계약
    │   ├── md-outputs.md           ← MD 5종 규격
    │   └── ocr-intake.md           ← 사진·스캔 판독 규약
    ├── assets/
    │   ├── template.html           ← 템플릿 하나
    │   ├── themes/{clean,gonggam,mono,warm}.css
    │   └── fonts/NotoSansKR-{400,700}.woff2   ← 동봉
    ├── scripts/
    │   ├── render_report.py        ← report.json → HTML
    │   ├── render_pdf.py           ← HTML → PDF (Win·Linux·mac)
    │   ├── gate_check.py           ← 완료 게이트
    │   └── outname.py              ← 파일명 생성·검사
    └── examples/report.sample.json ← 검증용 표본 (명지고 고1 영어 25문항)
```

## 돌려보기

```bash
cd skills/gonggam-exam-report
python scripts/render_report.py examples/report.sample.json out/
python scripts/render_report.py examples/report.sample.json out/ --internal
python scripts/render_pdf.py out/*배포본.html out/배포본.pdf
python scripts/outname.py out/
python scripts/gate_check.py out/ examples/report.sample.json
```

표본으로 확인된 것 — 9섹션 10페이지, 섹션 번호 연속, 총페이지 일치, 외부 의존 0,
배포본에서 판정 근거 제거(내부본 3건 → 배포본 0건), 파일명 4/4 규격, 게이트 전항 통과.

## 테마

템플릿은 하나, 테마는 여럿이다. 새 학원 브랜드는 **css 파일 하나를 더 만드는 것으로 끝난다.**

| 테마 | 언제 |
|---|---|
| `clean` | 기본. 학부모 배포 |
| `gonggam` | 공감에듀테크 자체 발행 |
| `mono` | 흑백 복사를 거치는 문서 |
| `warm` | 초등·중등 학부모 |

## 게이트가 막는 것

빈 플레이스홀더 · 섹션 번호 결번 · 총페이지 불일치 · 폰트 누락 · 외부 CDN ·
금지 문구(100% · 무조건 · 보장 · 1위 · 적중률) · 문항 수/배점 합 불일치 ·
난이도 규격 밖 · 유형 판정 근거 누락 · 저신뢰 판독 미확인 · PDF 0페이지.

**경고하지 않는다. 막는다.**

## 환경

```
Python 3.8+    (표준 라이브러리만 — 외부 패키지 없음)
Chrome / Edge  (PDF 변환. 없으면 GONGGAM_CHROME 환경변수로 경로 지정)
```

폰트 재생성이 필요하면 `fontTools` + `brotli` 로 Noto Sans KR 가변폰트에서 400·700 을 뽑는다.

## 함께 쓰는 것

`gonggam-solving-logic` (영어 판정) · `gonggam-math-engine` (수학 대조) ·
`gonggam-material-studio` (출제·조판 규격) · `academy-marketing:academy-compliance` (법적 검수)
