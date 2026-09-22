# AGENTS.md — FluidAttn (Codex·Claude 공용 규칙, `CLAUDE.md` 는 이 파일을 include)

> 문서 지도는 `docs/README.md` 부터. 하네스 정본은 Dagyeom/mvp `docs/DEV_ENV.md`(복제 원본, 2026-09-22).

## 프로젝트
FluidAttn — attention 연구 프로젝트. 스택: Python 3.11 · PyTorch/CUDA · ruff · pytest. 소스 `src/` 또는 `fluidattn/`, 테스트 `tests/`.

## AX Platform
- 프로젝트 `fluidattn` (domain `dev`). 세션 시작 시 `get_context(repo="fluidattn", domain="dev", intent=…)` 로 운영규칙(shared → dev → fluidattn)을 받는다.
- 질문은 `wiki_search` 먼저. 세션 끝에 task-log(Claude Code 는 플러그인 Stop hook 자동, Codex 는 `wiki_write(type=task-log)`).
- 모든 MCP 도구 호출에 `intent` 한 줄.

## CRITICAL
1. 소스 모듈은 테스트 먼저(tdd-guard · pre-commit 강제). `tests/test_<module>.py`.
2. CPU 만으로 `ruff check . && pytest -q` 가 green — GPU 테스트는 skipif 격리.
3. 되돌릴 수 없는 명령(강제 push · hard reset · 재귀 삭제) · .env/id_rsa 접근 금지(block-dangerous 가 deny).
4. 시크릿은 코드·wiki·로그에 남기지 않는다.
5. step 에 명시된 작업만. 추가 파일·기능 금지.

## 훅 (`.claude/settings.json` · `.codex/hooks.json`, 스크립트 공유 `scripts/hooks/`)
| 이벤트 | 스크립트 | 역할 |
|---|---|---|
| PreToolUse[Bash] | `block-dangerous.sh` · `todo-guard.sh` | Prevent: 위험 명령 · staged TODO |
| PreToolUse[Edit\|Write\|apply_patch] | `references-readonly.sh` · `tdd-guard.sh`(codex 는 `codex-tdd-guard.sh` 경유) | references 읽기 전용 · test-first |
| PostToolUse | `format.sh`(ruff format) · `audit.sh` | 포맷 · JSONL 감사 |
| SessionStart · UserPromptSubmit | `token-guard.sh` | 토큰 폭주 경고 |
| Stop | `verify-gate.sh` → `retry-lock.sh` → `devlog-append.sh` | 변경 범위만 ruff·pytest(실패 시 block 1회 자가교정) · 3회 동일 실패 잠금 · DEVLOG |
| git pre-commit (`.githooks/`, `core.hooksPath`) | `precommit-review.sh` | staged 구현 파일에 테스트 없으면 커밋 거부 |

`pyproject.toml` 이 생기기 전에는 verify-gate·tdd-guard·pre-commit 이 자동 skip 된다.

## 절차
`/harness` → `phases/<phase>/step*.md`(runner 명시, 마지막 step = retro) → `python3 scripts/lint_phase.py <phase>` → `python3 scripts/execute.py <phase>`. AC 는 실행 가능한 커맨드(`python3 -m pytest -q tests/test_x.py`).

## 크로스 리뷰
Claude 가 만든 step 은 Codex 가 `/review` 로, Codex 가 만든 step 은 Claude `/review-code` 로(다른 모델·다른 세션).
