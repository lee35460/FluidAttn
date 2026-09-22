#!/bin/bash
# 원격 GPU PC(company2) 의 Claude/Codex 에 작업 위임. 로컬 main push → 원격 pull → 실행기 호출 → 원격 커밋 push → 로컬 pull.
#   scripts/remote.sh claude "<prompt>"      claude -p (bypassPermissions, 하네스 훅 적용)
#   scripts/remote.sh codex  "<prompt>"      codex exec (full-auto)
#   scripts/remote.sh phase  <phase-dir>     원격에서 python3 scripts/execute.py <phase> (runner 는 step.md 의 runner)
#   scripts/remote.sh sh     "<command>"     원격 repo 루트에서 셸 명령
set -euo pipefail
HOST=${REMOTE_HOST:-company2}
DIR=${REMOTE_DIR:-'~/workspacce_jwon_lee/FluidAttn'}
MODE=$1; shift; ARG=${1:-}
[ -z "$ARG" ] && { sed -n 2,7p "$0"; exit 2; }
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git fetch -q origin "$BRANCH" && git merge -q --ff-only FETCH_HEAD && git push -q origin "$BRANCH"
case "$MODE" in
  claude) RUN="claude -p --permission-mode bypassPermissions --output-format text $(printf %q "$ARG")" ;;
  codex)  RUN="codex exec --dangerously-bypass-approvals-and-sandbox $(printf %q "$ARG") </dev/null" ;;  # stdin 열려 있으면 codex 가 대기(execute.py 와 동일)
  phase)  RUN="python3 scripts/execute.py $(printf %q "$ARG")" ;;
  sh)     RUN="$ARG" ;;
  *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac
ssh "$HOST" "export PATH=\$HOME/.local/bin:\$PATH; cd $DIR && git fetch -q origin $BRANCH && git merge -q --ff-only FETCH_HEAD && source .venv/bin/activate && $RUN; git push -q origin $BRANCH 2>/dev/null || true"
git fetch -q origin "$BRANCH" && git merge -q --ff-only FETCH_HEAD
