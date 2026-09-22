D5 리뷰 blocked 를 해소하는 **수정 프롬프트**를 만들어 codex 로 실행하고, 재리뷰까지 잇는다. P1 에서 step 12·17·23 에 같은 절차를 6번 손으로 썼다(3번의 법칙). 규칙은 ADR-049. 주체는 ADR-053: **§1·§2 Cursor(대조)** · **§3 Codex(구현)** · **§4 Claude(본심판)**. 재리뷰에서 "수정이 만든 결함·사칭" 한 줄 대조는 다시 Cursor.

인자(`$ARGUMENTS`): `<step> [r<N>]` — 예 `17`, `23 r2`. 리뷰 파일은 `phases/<phase>/reviews/step<step>-review[-r<N>].md`.

## 1. 발견 정리 (직접 수행)
1. 리뷰 파일의 확정 발견을 읽고 **같은 위치가 여러 차원에서 중복 보고된 것은 하나로 합친다**(고유 N건: critical·major·minor·nit).
2. 두 차원의 Fix 가 다르면 **설계를 하나로 못박는다**(예: step 17 r2 "promote 의 root 병합은 `GitWriteJob.mergeBranch` 로 git.write 안에서"). 리뷰어 제안을 그대로 넘기지 마라 — 1회차 지시가 애매하면 2회차에 "수정이 만든 결함"으로 돌아온다(step 17·23 모두 재현).
3. 발견이 CLAUDE.md CRITICAL 에 닿으면 **규칙 원문을 프롬프트 최상단에 인용**한다(step 17 single-writer 재위반은 원문 없이 지시해서 났다).

## 2. 프롬프트 (reports/step<step>-fix[-r<N>]-prompt.md 로 저장)
```
당신은 AX Platform 프로젝트의 개발자입니다. AGENTS.md 의 규칙을 따르세요.

## 작업
`<리뷰 파일>` 의 확정 발견 고유 N건(critical a · major b · minor c)을 수정하라. 아래 지침이 리뷰 Fix 와 다르면 아래 우선.
[CRITICAL 원문 인용 — 해당 시]
### critical / major / minor  ← 항목별 파일:줄 · 설계 고정 · 회귀 테스트가 재현할 실패 형태

## 규칙
1. 위 N건 외 리팩토링·기능 추가·파일 이동 금지. "미검증" 항목은 건드리지 않는다.
2. 수정마다 회귀 테스트 먼저(TDD). 서비스 테스트 ≥1 은 실제 협력 서비스(memory repo + 실제 서비스) 결선.
   **회귀 테스트에 인자를 추가해 통과시키지 마라** — 계약이 바뀌면 요약에 명시.
3. `python3 -m ruff check . && python3 -m pytest -q` green. **GPU 벤치마크·전체 pytest 재실행 같은 부가 검증은 돌리지 마라**(step 게이트 아님).
4. `phases/<phase>/index.json` 수정 금지.
5. 커밋: `fix(<phase>): step <step> <N>회차 리뷰 — critical a(<요약>)·major b(<요약>)·minor c` 하나. deploy 변경은 `../deploy/` 에서 별도 커밋.
6. `reports/step<step>-fix[-r<N>]-summary.md` 에 항목별 표(파일:줄 · 원인 · 수정 · 테스트) + 잔여 위험·이월 목록.
```

## 3. 실행
```bash
nohup codex exec --json --dangerously-bypass-approvals-and-sandbox "$(cat reports/step<step>-fix-prompt.md)" > reports/step<step>-fix-codex.log 2>&1 &
```
종료 후 `git log -1`·summary 표·lint/build/test 를 **직접** 재실행해 확인한다(codex 보고를 그대로 믿지 않는다).

## 4. 재리뷰 규모 (ADR-049)
- 수정 diff 가 CRITICAL 경로(git 쓰기·마스킹·RBAC·상태 머신·배포 경계)를 건드리면 → `/review-code HEAD~1` (수정이 만든 결함을 본다 — step 17·23 은 2회차에서 major 5·2 가 전부 수정 부작용)
- 그 외 diff ≤ 200줄 → `/review HEAD~1` 경량
- 결과는 `python3 scripts/review/render-review.py phases/<phase>/reviews/step<step>-review-r<N>.md "<제목>" "<범위>" <result.json>` 으로 기록. critical 0 / major 0 이면 step completed, 아니면 2 로.

## 5. 기록
`docs/DEVLOG.md` 에 D5 해소 행(라운드 수·고유 발견·"수정이 만든 결함" 여부·비용). 같은 원인 2회면 ADR 후보.
