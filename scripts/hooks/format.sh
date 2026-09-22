#!/bin/bash
# PostToolUse[Edit|Write] — 수정 파일 자동 포맷. ruff 없으면 조용히 통과.
# md(정본 문서)·json(phases/ 상태 파일)은 대상 아님(P-53).
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE_PATH" ] && exit 0
case "$FILE_PATH" in
  *.py) python3 -m ruff format "$FILE_PATH" >/dev/null 2>&1 || true ;;
esac
exit 0
