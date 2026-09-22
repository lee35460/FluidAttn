#!/bin/bash
# SessionStart · UserPromptSubmit — Detect·비용 층 (ADR-048, P1 step 6 토큰 폭주). 차단하지 않는다(exit 0), 경고를 컨텍스트에 남긴다.
#   SessionStart     : ① 같이 도는 다른 claude CLI 세션(interactive·`claude -p`)·execute.py·codex exec 수
#                      ② 이 프로젝트 세션 로그(~/.claude/projects/<slug>*/*.jsonl) 최근 15분 토큰 합(requestId 로 중복 제거)
#   UserPromptSubmit : ③ 내 세션의 현재 컨텍스트 크기(마지막 요청의 input+cache_read+cache_write). 요청당 비용 = 컨텍스트 크기이므로
#                      임계 초과면 /compact 또는 새 세션을 권한다(이 세션 fbac8f3c: 컨텍스트 160K × 69요청 = 16분에 cache_read 7.2M).
#   기록: reports/token-guard.jsonl {ts,event,sessions,execute,cache_read_15m,cache_write_15m,output_15m,context,warn}
#   환경: TOKEN_GUARD_MAX_SESSIONS(기본 1) · TOKEN_GUARD_MAX_EXEC(기본 0 — 하네스 안에서 돌 때 process-check 가 올림) · TOKEN_GUARD_MAX_CACHE_READ_15M(기본 5000000) · TOKEN_GUARD_MAX_CONTEXT(기본 150000 — P1 retro 토큰 분석, 넘으면 /compact 또는 새 세션)
#         TOKEN_GUARD_PROJECTS_DIR(테스트용 로그 루트)
INPUT=$(cat)
EVENT=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // "SessionStart"' 2>/dev/null); EVENT=${EVENT:-SessionStart}
SID=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
MAX_SESSIONS=${TOKEN_GUARD_MAX_SESSIONS:-1}
MAX_EXEC=${TOKEN_GUARD_MAX_EXEC:-0}
MAX_CR=${TOKEN_GUARD_MAX_CACHE_READ_15M:-5000000}
MAX_CTX=${TOKEN_GUARD_MAX_CONTEXT:-150000}  # P1 retro: 세션 26개 전부 100K+ 장기 지속이 최대 낭비($1,897 중 context_bloat 추정 $500+). 150K 넘으면 새 세션
SLUG=$(printf '%s' "$ROOT" | sed -E 's#/\.claude/worktrees/.*##' | sed 's#[/.]#-#g')
PDIR=${TOKEN_GUARD_PROJECTS_DIR:-$HOME/.claude/projects}
SESSIONS=0; EXEC=0; CR=0; CW=0; OUT=0; CTX=0; WARN=0; MSG=""

if [ "$EVENT" = "SessionStart" ]; then
  # ① 프로세스 — 내 세션(이 훅의 조상 claude)은 제외
  SELF=$$; ANCESTORS=""
  for _ in 1 2 3 4 5 6; do
    SELF=$(ps -o ppid= -p "$SELF" 2>/dev/null | tr -d ' '); { [ -z "$SELF" ] || [ "$SELF" = "1" ]; } && break
    ANCESTORS="$ANCESTORS $SELF"
  done
  while read -r pid args; do
    case " $ANCESTORS " in *" $pid "*) continue;; esac
    case "$args" in
      claude\ *|claude|*/claude\ *|*/claude) SESSIONS=$((SESSIONS+1));;
      python*execute.py*|*/python*execute.py*|codex\ exec*|*/codex\ exec*) EXEC=$((EXEC+1));;  # 문자열 포함이 아니라 실제 실행 명령만(모니터 셸의 echo 문구 오탐 방지)
    esac
  done < <(ps -axo pid=,args= 2>/dev/null)
  # ② 최근 15분 사용량 — 파일은 tail 3MB 만(20시간 세션 로그 12MB). usage 행은 요청당 여러 번 찍히므로 requestId 로 중복 제거.
  read -r CR CW OUT < <(python3 - "$PDIR" "$SLUG" <<'PY'
import glob, json, os, sys, time
from datetime import datetime
pdir, slug = sys.argv[1], sys.argv[2]
cutoff = time.time() - 15 * 60
seen = {}
for f in glob.glob(f"{pdir}/{slug}*/*.jsonl"):
    try:
        if os.path.getmtime(f) < cutoff:
            continue
        with open(f, "rb") as fh:
            fh.seek(max(0, os.path.getsize(f) - 3_000_000)); data = fh.read().decode("utf-8", "ignore")
    except OSError:
        continue
    for line in data.splitlines():
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message"); u = m.get("usage") if isinstance(m, dict) else None
        ts = d.get("timestamp")
        if not u or not ts:
            continue
        try:
            if datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() < cutoff:
                continue
        except ValueError:
            continue
        seen[d.get("requestId") or d.get("uuid")] = u
print(sum(u.get("cache_read_input_tokens", 0) for u in seen.values()),
      sum(u.get("cache_creation_input_tokens", 0) for u in seen.values()),
      sum(u.get("output_tokens", 0) for u in seen.values()))
PY
  ) || { CR=0; CW=0; OUT=0; }
  [ "$SESSIONS" -gt "$MAX_SESSIONS" ] && WARN=1
  [ "$EXEC" -gt "$MAX_EXEC" ] && WARN=1
  [ "${CR:-0}" -gt "$MAX_CR" ] && WARN=1
  if [ "$WARN" = 1 ]; then
    MSG="⚠ TOKEN-GUARD: 다른 claude 세션 ${SESSIONS}개 · execute.py/codex exec ${EXEC}개 · 최근 15분 cache_read $((CR/1000))K / cache_write $((CW/1000))K / output $((OUT/1000))K. 새 작업 전에 다른 세션을 끝내거나 원인을 확인하라(ADR-048: 한도로 끊긴 step 을 같은 비용으로 재실행하지 않는다). 세션 채점: /improve-token-efficiency"
  else
    MSG="TOKEN-GUARD ok: 다른 세션 ${SESSIONS} · 최근 15분 cache_read $((CR/1000))K"
  fi
else
  # ③ 내 세션 컨텍스트 — 마지막 usage 행의 input+cache_read+cache_write. 파일은 tail 512KB 만.
  F=$(ls "$PDIR"/"$SLUG"*/"$SID".jsonl 2>/dev/null | head -1)
  if [ -n "$F" ]; then
    CTX=$(tail -c 524288 "$F" | grep '"usage"' | tail -1 | jq -r '.message.usage | ((.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0))' 2>/dev/null)
    CTX=${CTX:-0}
  fi
  if [ "${CTX:-0}" -gt "$MAX_CTX" ]; then
    WARN=1
    MSG="⚠ TOKEN-GUARD: 이 세션 컨텍스트 $((CTX/1000))K — 이제부터 tool call 하나가 ${CTX} 토큰을 다시 읽는다. 하던 일을 마무리하고 /compact 하거나 새 세션에서 이어가라(ADR-048). 큰 파일은 전체 Read 대신 grep/sed -n 범위로."
  fi
fi

mkdir -p "$ROOT/reports"
printf '{"ts":"%s","event":"%s","sessions":%s,"execute":%s,"cache_read_15m":%s,"cache_write_15m":%s,"output_15m":%s,"context":%s,"warn":%s}\n' \
  "$(date -u +%FT%TZ)" "$EVENT" "$SESSIONS" "$EXEC" "${CR:-0}" "${CW:-0}" "${OUT:-0}" "${CTX:-0}" "$WARN" >> "$ROOT/reports/token-guard.jsonl"
[ -n "$MSG" ] && echo "$MSG"
exit 0
