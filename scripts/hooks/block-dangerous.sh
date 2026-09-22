#!/bin/bash
# PreToolUse[Bash] (Claude Code · Codex 공용) — 위험 명령 차단.
# 입력: stdin JSON. Bash 도구의 명령은 .tool_input.command (문자열 또는 argv 배열).
# 위험 패턴이면 permissionDecision=deny 를 stdout JSON으로 반환해 호출을 막는다.
INPUT=$(cat)
. "$(dirname "$0")/_lib.sh"

CMD=$(printf '%s' "$INPUT" | jq -r '
  (.tool_input.command // .tool_input.cmd // "") as $c
  | if ($c | type) == "array" then ($c | join(" ")) else ($c | tostring) end')

if printf '%s' "$CMD" | grep -qE 'rm[[:space:]]+-rf|rm[[:space:]]+-fr|git[[:space:]]+push[[:space:]]+--force|git[[:space:]]+reset[[:space:]]+--hard|DROP[[:space:]]+TABLE|psql[^|]*prod|cat[[:space:]]+[^|]*\.env|id_rsa'; then
  hook_decision block-dangerous deny "위험 명령: $CMD"
  jq -cn '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "BLOCKED: 위험한 명령어가 감지되었습니다 (되돌릴 수 없음·민감 데이터·프로덕션·references/ 쓰기)."
    }
  }'
  exit 0
fi

# references/ 는 읽기 전용: 리다이렉션·tee·rm·sed -i·chmod·touch·mkdir, 또는 cp/mv/rsync 의 목적지(마지막 인자)로 쓰일 때만 차단. cat/ls/grep/diff 등 읽기는 허용.
if printf '%s' "$CMD" | grep -qE '(>>?|\btee\b)[[:space:]]*[^|;&]*references/' \
   || printf '%s' "$CMD" | grep -qE '\b(rm|sed[[:space:]]+-i|chmod|chown|touch|mkdir|ln)\b[^|;&]*references/' \
   || printf '%s' "$CMD" | grep -qE '\b(cp|mv|rsync)\b[^|;&]*[[:space:]][^[:space:]]*references/[^[:space:]]*[[:space:]]*($|[;&|])'; then
  hook_decision block-dangerous deny "references/ 쓰기: $CMD"
  jq -cn '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:"BLOCKED: references/ 는 읽기 전용 — 복제해서 mvp/ 또는 deploy/ 에서 작업하라 (ADR-019)."}}'
fi
exit 0
