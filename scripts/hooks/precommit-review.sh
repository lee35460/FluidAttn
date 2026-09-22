#!/bin/bash
# pre-commit (git core.hooksPath=.githooks) — TDD 1단계(P-40).
# staged 에 Python 구현 파일이 있으면 tests/**/test_<base>.py 가 staged 또는 워킹 트리에 있어야 한다.
# tdd-guard(PreToolUse) 는 에디터 경로만 막고, 셸로 만든 파일은 못 본다 — 커밋 시점에 한 번 더 확인한다.
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd); cd "$ROOT"
[ -f pyproject.toml ] || exit 0
STAGED=$(git diff --cached --name-only --diff-filter=ACMR)
MISSING=""
for f in $(printf '%s\n' "$STAGED" | grep -E '\.py$' | grep -vE '^(tests|scripts|benchmarks|examples|docs)/|(^|/)(test_[^/]*|[^/]*_test|conftest|__init__|setup)\.py$'); do
  base=$(basename "$f" .py)
  { printf '%s\n' "$STAGED" | grep -qE "(^|/)test_${base}\.py$" || [ -n "$(find tests -name "test_${base}.py" -print -quit 2>/dev/null)" ]; } || MISSING+="$f "
done
if [ -n "$MISSING" ]; then
  echo "pre-commit: 테스트 없는 구현 파일 — tests/test_<name>.py 를 먼저 stage 하라(AGENTS.md: 소스는 TDD): $MISSING" >&2
  exit 1
fi
exit 0
