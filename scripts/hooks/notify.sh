#!/bin/bash
# Notification — 사용자 응답 대기 시 macOS 알림 (Ch01 Hooks 4이벤트). terminal-notifier 없으면 osascript.
MSG=$(cat | jq -r '.message // "Claude 가 입력을 기다립니다"' | cut -c1-120)
if command -v terminal-notifier >/dev/null; then terminal-notifier -title "AX mvp" -message "$MSG" -sound Ping >/dev/null 2>&1
else osascript -e "display notification \"$MSG\" with title \"AX mvp\"" >/dev/null 2>&1 || true; fi
exit 0
