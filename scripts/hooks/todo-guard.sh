#!/bin/bash
# PreToolUse[Bash: git commit] — TDD hook 카탈로그 3번: 변경 파일에 TODO/FIXME 남은 채 커밋 차단 (soft: 경고만 하려면 SOFT=1).
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
echo "$CMD" | grep -qE '^\s*git\s+commit' || exit 0
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd); cd "$ROOT"
HITS=$(git diff --cached -U0 | grep -E '^\+' | grep -E 'TODO|FIXME' | head -5)
if [ -n "$HITS" ]; then
  if [ "${SOFT:-0}" = "1" ]; then echo "TODO-GUARD(warn): $HITS" >&2; exit 0; fi
  jq -cn --arg h "$HITS" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:("TODO/FIXME 가 남은 채 커밋할 수 없다:\n"+$h)}}'
fi
exit 0
