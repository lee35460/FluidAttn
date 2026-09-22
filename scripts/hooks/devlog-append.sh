#!/bin/bash
# Stop — 세션 종료 시 DEVLOG 에 변경 요약 한 줄 append (Ch01 Stop "git diff > daily.log", §17 기록→개정 루프 원천).
INPUT=$(cat)
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd); cd "$ROOT"
FILES=$(git status --porcelain 2>/dev/null | awk '{print $2}' | head -8 | tr '\n' ' ')
[ -z "$FILES" ] && exit 0
# 활성 phase = phases/index.json 에서 status 가 completed 가 아닌 첫 항목(`ls | tail -1` 은 다음 phase 폴더가 미리 있으면 오인 — P-29)
PHASE=$(jq -r '[.phases[] | select(.status != "completed")][0].dir // empty' phases/index.json 2>/dev/null); PHASE=${PHASE:-setup}
tail -1 docs/DEVLOG.md 2>/dev/null | grep -qF "변경: $FILES" && exit 0   # 같은 변경 목록이면 중복 행 생략
printf '| %s | %s | session | 변경: %s | — |\n' "$(date +%F)" "$PHASE" "$FILES" >> docs/DEVLOG.md
exit 0
