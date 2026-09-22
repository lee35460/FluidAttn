#!/bin/bash
# 훅 공용 함수 — 각 훅이 `. "$(dirname "$0")/_lib.sh"` 로 source 한다(단독 실행 안 함).
#   redact          : stdin 의 시크릿 패턴을 [REDACTED] 로 (audit.sh 와 hook-decisions 가 같은 규칙을 쓴다)
#   hook_decision   : deny·block 결정을 reports/hook-decisions.jsonl 에 {ts,hook,decision,reason} 한 줄 append — retro 의 "훅 동작" 집계 원천(P-46)
redact(){ sed -E 's/(SECRET|TOKEN|API_KEY|PASSWORD)[^,}]*/\1=[REDACTED]/g'; }
hook_decision(){
  local root; root=$(git rev-parse --show-toplevel 2>/dev/null || pwd); mkdir -p "$root/reports"
  jq -cn --arg ts "$(date -u +%FT%TZ)" --arg h "$1" --arg d "$2" --arg r "$(printf '%s' "$3" | redact | tr '\n' ' ' | cut -c1-300)" \
    '{ts:$ts,hook:$h,decision:$d,reason:$r}' >> "$root/reports/hook-decisions.jsonl"
}
