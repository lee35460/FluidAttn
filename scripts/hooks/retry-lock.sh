#!/bin/bash
# Stop — TDD hook 카탈로그 2번: 자기수정 루프 잠금. 같은 테스트 실패가 N회(기본 3) 연속이면 사람 개입 요청.
INPUT=$(cat)
. "$(dirname "$0")/_lib.sh"
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd); STATE="$ROOT/reports/.retry-lock"; mkdir -p "$ROOT/reports"
[ -f "$ROOT/package.json" ] || { echo '{"continue":true}'; exit 0; }
LAST_V="$ROOT/reports/.verify-last"
# mtime: GNU(stat -c) 먼저 — GNU 에서 'stat -f %m' 은 파일시스템 정보를 exit 0 으로 출력해 폴백이 작동하지 않는다(CI 러너 P-21 실패, 2026-09-18).
if [ -f "$LAST_V" ] && [ $(( $(date +%s) - $(stat -c %Y "$LAST_V" 2>/dev/null || stat -f %m "$LAST_V") )) -lt 120 ]; then
  OUT=$(cat "$LAST_V"); [ "$OUT" = "ok" ] && OUT=""   # verify-gate 가 방금 돌린 결과 재사용 (테스트 2회 실행 방지)
else
  OUT=$(cd "$ROOT" && npm run test 2>&1 | tail -n 5 | tr -d '\n' | cut -c1-200)
fi
LAST=$(cat "$STATE" 2>/dev/null | head -1); CNT=$(cat "$STATE" 2>/dev/null | tail -1); CNT=${CNT:-0}
if echo "$OUT" | grep -qiE 'fail|error'; then
  if [ "$OUT" = "$LAST" ]; then CNT=$((CNT+1)); else CNT=1; fi
  printf '%s\n%s\n' "$OUT" "$CNT" > "$STATE"
  if [ "$CNT" -ge "${MAX_SAME_FAIL:-3}" ]; then
    hook_decision retry-lock block "같은 실패 ${CNT}회: $OUT"
    jq -cn --arg r "같은 테스트 실패가 ${CNT}회 연속. 자동 재시도를 멈추고 사람 개입(D4)을 요청한다: $OUT" '{decision:"block",reason:$r}'
    rm -f "$STATE"; exit 0
  fi
else rm -f "$STATE"; fi
echo '{"continue":true}'; exit 0
