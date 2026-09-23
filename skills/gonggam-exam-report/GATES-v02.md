# Gates: 기출분석 리포트 스킬 v0.2 (2패스 쪽나눔 · MD 연동 · 요약본 · 게이트 확장)

Scope: 네 갈래 병렬 작업의 결과를 **하나로 묶어** 잰다.
① 쪽 나눔에서 추측 상수를 없애고 ② MD 가 리포트의 원천이 되게 하고
③ A4 한 장 요약본을 더하고 ④ 게이트를 조판·대조까지 넓혔다.

체커 — `python C:/dev/apps/gonggam-claude-plugins/plugins/gonggam-gates/scripts/gate.py GATES-v02.md`
(스킬 폴더 뿌리에서 돌린다. 먼저 `--print` 로 명령을 다 읽는다.)

원칙 — **ALL MET 이 아니면 완료 보고를 쓰지 않는다.**
그리고 통과만 보고 믿지 않는다. 양성 대조(G7·G8·G10·G15)가 ✕ 를 내는 것을 함께 본다.

---

- [x] G1: 상세본이 렌더된다 (배포본)
  EVIDENCE: 2026-09-21T19:48:04 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=51ca00fbe6ad bytes=1312 27.5s
  CHECK: python scripts/render_report.py examples/report.sample.json .gatework/detail
  EXPECT: 섹션 9개

- [x] G2: 내부본이 렌더된다 — 열이 둘 더 많아 행이 높다
  EVIDENCE: 2026-09-21T19:48:04 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=82878859b002 bytes=1318 27.8s
  CHECK: python scripts/render_report.py examples/report.sample.json .gatework/internal --internal
  EXPECT: 테마 clean · 내부본

- [x] G3: 상세본 PDF 가 나온다
  EVIDENCE: 2026-09-21T19:48:04 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=3c496ce386d6 bytes=120 27.6s
  CHECK: python gates/checks.py topdf .gatework/detail
  EXPECT: pdf ok

- [x] G4: 상세본이 게이트 전항을 통과한다
  EVIDENCE: 2026-09-21T20:40:23 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=fdf907aedc88 bytes=4569 0.3s
  NOTE: 이 한 줄에 쪽수 일치·채움률 40%·조판(제목만 있는 장·표 머리글·본문 살아남음)·
        빈 자리·폰트·금지 문구·데이터 정합이 전부 딸려 온다.
        빌더 게이트가 보는 것을 원장에 두 번 적지 않는다.
  CHECK: python scripts/gate_check.py .gatework/detail examples/report.sample.json
  EXPECT: 게이트 통과

- [x] G5: MD 에서 report.json 이 지어진다 (연동의 입구)
  EVIDENCE: 2026-09-21T21:23:11 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=17255943bc6f bytes=416 0.1s
  CHECK: python scripts/report_build.py examples/samsung_h1_en/exam.json examples/samsung_h1_en .gatework/md.json --detail
  EXPECT: 삼성고등학교 · 20문항 100점 · 상세본

- [x] G6: **MD 를 고치면 리포트가 바뀐다** — 연동이 말이 아니라 사실인가
  EVIDENCE: 2026-09-21T21:23:11 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=35ee39429245 bytes=395 135.0s
  NOTE: 해설 MD 의 문장이 렌더된 HTML 안에 그대로 있는지 본다.
        이게 이 회차의 핵심이다. 같은 내용을 두 번 쓰지 않게 되었는가.
  CHECK: python gates/checks.py mdlink
  EXPECT: md link ok

- [x] G7: **양성 대조** — MD 대조가 정말 막는가 (다섯 갈래)
  EVIDENCE: 2026-09-21T20:40:23 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=12ffda727198 bytes=363 0.5s
  NOTE: 제목 줄 정답·meta 정답·문항 누락·이슈 이유 없음·모르는 갈래.
        일부러 어긋나게 만들어 ✕ 가 나오는 것을 본다. 통과만 보고 검사기를 믿지 않는다.
  CHECK: python gates/negative.py md
  EXPECT: negative control ok

- [x] G8: **양성 대조** — 긴 내용에서 쪽수가 어긋나지 않는다 (회귀 잠금)
  EVIDENCE: 2026-09-21T19:48:04 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=32f3554cde04 bytes=127 53.6s
  NOTE: 옛 방식이 실제로 깨지던 자리다. «한 장에 20행» 상수가 내용 길이를 못 따라가
        표기 12쪽 / 실제 13쪽이 나왔다. 2026-09-21 확인.
        어긋나면 게이트가 막는 것까지 함께 본다.
  CHECK: python gates/negative.py stress
  EXPECT: negative control ok

- [x] G9: 요약본이 A4 한 장으로 나온다
  EVIDENCE: 2026-09-21T21:35:22 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=974edac550d9 bytes=39 63.4s
  CHECK: python gates/checks.py summary
  EXPECT: summary one page ok

- [x] G10: **양성 대조** — 발췌가 길면 요약본이 막힌다
  EVIDENCE: 2026-09-21T21:35:22 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=b8bc0151588d bytes=116 57.4s
  NOTE: 한 장이 규격이다. 넘치면 알아서 2장이 되는 게 아니라 막고 알려야 한다.
  CHECK: python gates/negative.py summary
  EXPECT: negative control ok

- [x] G11: 산출 파일 이름이 공용 규격이다
  EVIDENCE: 2026-09-21T19:48:04 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=8dff193d936a bytes=31 0.1s
  NOTE: 규격 정본은 gonggam-material-studio/assets/filename_check.py 한 곳이다.
        이 스킬은 규격을 따로 갖지 않는다 — 위임한다.
  CHECK: python scripts/outname.py .gatework/detail
  EXPECT: 규격 밖 0개

- [x] G12: 옛 결함이 되살아나지 않았다 (회귀)
  EVIDENCE: 2026-09-21T19:48:04 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=aabec3f67313 bytes=204 26.6s
  NOTE: 세 가지를 한 번에 — 국어 «<보기>» 가 태그로 먹히지 않는가(HTML escape),
        같은 섹션이 두 번호를 쓰지 않는가, 동봉 폰트가 박혔는가.
        셋 다 이 저장소에서 실제로 났던 사고다.
  CHECK: python gates/checks.py regress
  EXPECT: regress ok

- [x] G13: (수동) 지면이 읽을 만한가
  NOTE: 명령으로 못 재는 것을 잰다고 쓰지 않는다.
        상세본 표지·문항표·킬러문항과 요약본 한 장을 PNG 로 떠서 **사람이 본다.**
        볼 것 — 잘린 글자, 어색한 줄바꿈, 표가 페이지 경계에서 반쪽 난 자리,
        요약본이 40초 안에 읽히는가.
        CHECK 를 두지 않는다. 「예쁘게 나왔다」를 실행 게이트로 위장하지 않는다.
  EVIDENCE: 2026-09-21 · 150dpi PNG 로 떠서 직접 봄. 표본 = examples/samsung_h1_en (MD 연동, 20문항 100점).
        상세본 7쪽 — p02 「1.시험 개요 + 2.문항별 분석표」(표 15행이 온전히 들어가고 다음 장에서
        머리글이 다시 찍힌다), p05 「9번 킬러 카드」(영어 지문 6줄 + 선지 5 + 왜 어려웠나 +
        오답 근거 노란 상자 4줄 + 푸는 순서 4 + 개념 칩이 한 카드에, 쪼개짐 없음),
        p06 「10번 어법 카드 + 7.출제에 문제가 있었던 문항」(이슈는 왼쪽 빨강 선 + 분홍 배지로
        킬러 카드와 갈린다. 「학생의 실수와 구분해서 보셔야 합니다」 한 줄이 제 몫을 한다).
        요약본 1쪽 — 머리글·숫자 4·난이도 5단·유형 상위 3·대표 문항(19번 서술형: 발문/〈조건〉 3/
        모범답안/왜 갈렸나)·복수정답 이슈·갈린 곳·총평+다음 행동·출처와 추정 고지.
        총평 상자는 내용 높이에 맞고 그 아래는 흰 여백 — 빈 파란 상자가 아니다.
        ✔ 잘린 글자 없음 · 어색한 줄바꿈 없음 · 표나 카드가 경계에서 반쪽 난 자리 없음
        ✔ 백틱·`**` 등 마크다운 잔재 0 · 「본문참조」 0 · 쪽 표시 장마다 일치
        ✔ 요약본은 40초 안에 읽힌다 — 숫자 → 대표 문항 → 다음 행동 순으로 눈이 흐른다
        NOTE 수동 검수에서 결함 둘을 찾아 고친 뒤 다시 봤다 —
             ① 이슈 섹션이 상세본에 안 실리던 것(자동 게이트 12개는 전부 통과했다)
             ② 요약본 총평 상자가 내용보다 훨씬 커서 «빈 파란 상자» 로 보이던 것
             둘 다 눈으로만 보이는 것이었다. 이 게이트를 둔 까닭이 그것이다.

- [x] G14: 빌더가 채우는 칸 여섯이 규격대로 채워진다
  EVIDENCE: 2026-09-23T19:51:52 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=43e6b5be5bbf bytes=185 0.4s
  NOTE: em · num/unit/key · 강조 지목 · 레이다 · 푸는 순서 · 채움 자리.
        렌더러의 치환자에는 「만약」이 없다 — 한 줄이라도 칸이 빠지면 «{{em}}» 이 글자로
        남아 **렌더가 통째로 실패한다.** 지금까지는 렌더가 죽고 나서야 알았다.
        표본은 examples/report.sample.json 이 아니라 examples/samsung_h1_en 에서 갓 짓는다.
        표본 json 둘에는 새 칸이 없어 아직 렌더조차 되지 않는다 (HANDOFF § 5-2).
        **잰 개수를 함께 찍는다** — 0개를 재고 통과하면 회귀 잠금이 아니다.
        크롬을 쓰지 않는다. 여섯 다 report.json 과 판형 글자만 잰다.
  CHECK: python gates/checks.py fields
  EXPECT: fields ok

- [x] G15: **양성 대조** — 새 칸이 어긋나면 정말 막는가 (열아홉 갈래)
  EVIDENCE: 2026-09-23T19:51:52 exit=0 match=yes cwd=C:\dev\apps\gonggam-claude-plugins\plugins\gonggam-exam-report\skills\gonggam-exam-report shell=cmd.exe sha256=5bdf866d6542 bytes=1528 2.0s
  NOTE: 칸을 빼고 · 참/거짓을 넣고 · 지목을 지우고 · 축을 둘로 줄이고 · ★ 를 둘 찍고 ·
        자리 이름에 key 를 적어 본다. 막히는 것만 보지 않고 **그 검사가 막았는지**
        차단 줄의 이름까지 본다 — 엉뚱한 검사가 막아도 「OK」 가 찍히면 지으려던 검사는
        죽은 채로 남는다.
        멀쩡한 표본 셋(상세본·요약본·강조를 지목한 상세본)이 **통과하는 것도 함께** 본다.
        잡는 것과 안 잡는 것을 둘 다 확인한다.
  CHECK: python gates/negative.py fields
  EXPECT: negative control ok
