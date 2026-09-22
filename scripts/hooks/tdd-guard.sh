#!/bin/bash
# TDD Guard Hook — PreToolUse[Edit|Write]
# 구현 코드를 작성하려 할 때, 해당 모듈의 테스트 파일이 먼저 존재하는지 체크. 없으면 차단.
# (Claude .claude/settings.json 과 codex .codex/hooks.json 양쪽에서 공유하는 스크립트)

INPUT=$(cat)
. "$(dirname "$0")/_lib.sh"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE_PATH" ] && exit 0

# 프로젝트가 아직 스캐폴딩되지 않았으면(pyproject.toml 없음) TDD 가드를 건너뛴다.
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -f "$ROOT/pyproject.toml" ] || exit 0

# Python 소스만 대상. 테스트·인프라·패키지 마커·스크립트·벤치마크는 허용.
case "$FILE_PATH" in
  *.py) ;;
  *) exit 0 ;;
esac
case "$FILE_PATH" in
  */tests/*|*/test_*.py|*_test.py|*/conftest.py|*/__init__.py|*/setup.py|*/.claude/*|*/scripts/*|*/benchmarks/*|*/examples/*|*/docs/*|*/reports/*|*/evals/*)
    exit 0 ;;
esac

BASENAME=$(basename "$FILE_PATH" .py)
DIR=$(dirname "$FILE_PATH")
TEST_FOUND=false
# 같은 폴더 · 폴더 안 tests/ · 루트 tests/(하위 폴더 포함)
for c in "$DIR/test_${BASENAME}.py" "$DIR/tests/test_${BASENAME}.py"; do
  [ -f "$c" ] && { TEST_FOUND=true; break; }
done
if [ "$TEST_FOUND" = false ] && [ -d "$ROOT/tests" ]; then
  [ -n "$(find "$ROOT/tests" -name "test_${BASENAME}.py" -print -quit)" ] && TEST_FOUND=true
fi

if [ "$TEST_FOUND" = false ]; then
  hook_decision tdd-guard deny "테스트 없음: $FILE_PATH"
  cat << EOT
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "TDD GUARD: '${BASENAME}'에 대한 테스트 파일이 존재하지 않습니다. 구현 코드를 작성하기 전에 테스트를 먼저 작성하세요. (테스트 파일 예: tests/test_${BASENAME}.py)"
  }
}
EOT
fi
exit 0
