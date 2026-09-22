phase 말 회고. 순서:
1. `docs/DEVLOG.md`, `phases/<현재>/index.json` 을 읽는다. `reports/` 에 **이 phase 기간의** readiness·token 리포트가 없으면 먼저 생성한다: `ai-readiness-cartography`(repo 채점) · `improve-token-efficiency`(phase 세션 집계 — step 별 비용·hotspot 도구·캐시 hit). 매 step 이 아니라 phase 말 + 주 1회가 이 두 스킬의 주기다(step 단위 보호는 token-guard 훅).
2. docs-reviser 서브에이전트에게 개정 초안을 맡긴다(같은 원인 error/blocked 2회→ADR · 계획 밖 화면/도구/데이터→PRD · readiness 하락/drift→ARCHITECTURE/CLAUDE.md · 반복 절차 3회→.claude/skills · 반복 실수 3회→.claude/rules · manual_intervention→원인 분류).
3. 결과를 표로 보고(개정 항목 · 근거 · diff 요약)하고 사용자 승인을 기다린다. 승인 전 커밋하지 마라.
4. 승인 후 `docs(revise): <phase> retro` 로 커밋하고 DEVLOG 에 `retro` 행을 append.
