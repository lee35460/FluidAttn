#!/bin/bash
# PostToolUse[*] — Detect 층: tool·args(redact)·ok 를 JSONL 로. (Ch05-10 Layer 2). 분당 호출 임계 초과 시 경고.
INPUT=$(cat)
. "$(dirname "$0")/_lib.sh"
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
LOG="$ROOT/reports/audit.jsonl"; mkdir -p "$ROOT/reports"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // "?"')
ARGS=$(echo "$INPUT" | jq -c '.tool_input // {}' | redact | cut -c1-300)
printf '{"ts":"%s","tool":"%s","args":%s}\n' "$(date -u +%FT%TZ)" "$TOOL" "$(printf '%s' "$ARGS" | jq -Rs .)" >> "$LOG"
# 루프 감지: 최근 60초 호출 수
N=$(tail -n 200 "$LOG" | jq -r '.ts' | awk -v now="$(date -u +%s)" '{cmd="date -u -j -f %Y-%m-%dT%H:%M:%SZ "$1" +%s 2>/dev/null || date -u -d "$1" +%s"; cmd|getline t; close(cmd); if (now-t<60) c++} END{print c+0}')
[ "${N:-0}" -gt 60 ] && echo "AUDIT: 분당 tool 호출 ${N}회 — 루프 의심 (Ch05-10 Detect 임계)" >&2
exit 0
