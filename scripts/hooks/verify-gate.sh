#!/bin/bash
# Stop (Claude·Codex 공용) — lint/test 게이트. 결과 요약을 reports/.verify-last 에 남겨 retry-lock 이 재사용한다.
# 통과하면 정상 stop, 실패하면 decision:block 으로 1회 자가교정(.stop_hook_active 로 루프 방지).
#
# 범위 규칙(Dagyeom/mvp verify-gate 와 동일 원칙, Python 스택):
#   변경 파일 = HEAD 대비 미커밋 + 미추적 + 직전 커밋
#   - tests/** · conftest.py 만 변경                      → pytest
#   - *.py · *.cu · *.cpp · *.h · pyproject.toml · setup.* 변경 → ruff check && pytest
#   - 그 외(docs/ phases/ reports/ scripts/ 등)만          → 게이트 생략(.verify-last 에 ok 기록)
#   VERIFY_GATE_DRY=1 이면 범위만 출력하고 끝낸다.
INPUT=$(cat)
. "$(dirname "$0")/_lib.sh"
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
ALLOW='{"continue": true}'

ACTIVE=$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false')
[ "$ACTIVE" = "true" ] && { printf '%s\n' "$ALLOW"; exit 0; }

# 아직 Python 프로젝트가 없으면(스캐폴딩 전) 게이트를 건너뛴다.
if [ ! -f "$ROOT/pyproject.toml" ]; then
  printf '%s\n' "$ALLOW"
  exit 0
fi

cd "$ROOT" || { printf '%s\n' "$ALLOW"; exit 0; }
mkdir -p "$ROOT/reports"

CHANGED=$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; git diff --name-only HEAD~1 HEAD 2>/dev/null; } | sort -u )
TESTS=$(printf '%s\n' "$CHANGED" | grep -E '^tests/|(^|/)conftest\.py$' | head -1)
CODE=$(printf '%s\n' "$CHANGED" | grep -vE '^tests/|(^|/)conftest\.py$|^scripts/' | grep -E '\.(py|cu|cuh|cpp|cc|h|hpp)$|^pyproject\.toml$|^setup\.(py|cfg)$|^CMakeLists\.txt$' | head -1)

if [ -n "$CODE" ]; then
  CMD="python3 -m ruff check . 2>&1 && python3 -m pytest -q 2>&1"
elif [ -n "$TESTS" ]; then
  CMD="python3 -m pytest -q 2>&1"
else
  printf 'ok\n' > "$ROOT/reports/.verify-last"
  printf '%s\n' "$ALLOW"
  exit 0
fi
[ -n "$VERIFY_GATE_DRY" ] && { echo "scope: $CMD"; printf '%s\n' "$ALLOW"; exit 0; }

if OUT=$(bash -c "$CMD"); then
  printf 'ok\n' > "$ROOT/reports/.verify-last"
  printf '%s\n' "$ALLOW"
else
  printf '%s' "$OUT" | tail -n 5 | tr -d '\n' | cut -c1-200 > "$ROOT/reports/.verify-last"
  hook_decision verify-gate block "$CMD 실패: $(printf '%s' "$OUT" | tail -n 3)"
  jq -cn --arg r "lint/test가 실패했습니다(검사 범위: $CMD). green이 될 때까지 고치세요.

$(printf '%s' "$OUT" | tail -n 40)" '{decision: "block", reason: $r}'
fi

exit 0
