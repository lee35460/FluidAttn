#!/bin/bash
# PreToolUse[Edit|Write|apply_patch] — references/ 는 읽기 전용 (ADR-019). Claude·Codex 공용.
INPUT=$(cat)
. "$(dirname "$0")/_lib.sh"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')
case "$FILE_PATH" in
  *"/references/"*|references/*)
    hook_decision references-readonly deny "references/ 쓰기: $FILE_PATH"
    jq -cn '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:"references/ 는 읽기 전용. 필요하면 mvp/ 또는 deploy/ 로 복제해서 작업하라."}}';;
esac
exit 0
