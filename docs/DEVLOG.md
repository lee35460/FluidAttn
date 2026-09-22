# DEVLOG — 기록 → 문서 개정 루프의 원천

> step 단위로 append. 원천 = `phases/*/index.json` 의 summary/error_message/blocked_reason · `/review`·`/review-code` 결과 · Stop hook(devlog-append) 변경 요약.
> 각 phase 마지막 step = `retro`: 이 파일을 읽고 `docs(revise):` 초안 + 다음 phase step 수정안.

| date | phase | kind | 내용 | 후속 |
|---|---|---|---|---|
| 2026-09-22 | setup | note | Dagyeom/mvp 하네스 코어 복제(execute.py · lint_phase.py · hooks 13 · commands 5 · agents 4 · Codex 패리티) · ax MCP(Claude·Codex) 연결 · ax-team-plugin 설치 · 플랫폼 `project_init fluidattn` | 스택 Python(PyTorch/CUDA) 확정 → verify-gate(ruff·pytest)·tdd-guard(tests/test_<m>.py)·format(ruff format)·precommit·rules/testing·ci.yml 을 Python 규칙으로 재작성. Dagyeom 전용(process-check·rules ui/wiki/masking·ux-critic) 미복제 |
| 2026-09-22 | setup | session | 변경: .claude/ .codex/ .githooks/ .github/ .gitignore AGENTS.md CLAUDE.md docs/  | — |
