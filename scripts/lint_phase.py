#!/usr/bin/env python3
"""phase 사전 검증 — /harness 가 만든 phases/<phase>/ 가 step 7원칙과 우리 규칙을 지키는지 execute 전에 검사한다.

검사 항목:
  1. index.json: steps 순번 0..N 연속, status 초기값, 각 step 에 runner(claude|codex) 명시
  2. 마지막 step 이름은 'retro' (phase 말 회고 — PRD §17)
  3. step*.md 필수 섹션: '## 읽어야 할 파일' '## 작업' '## Acceptance Criteria' '## 검증 절차' '## 금지사항'
  4. AC 블록에 실행 가능한 커맨드(npm/python3/bash/pytest/lhci 등)가 최소 1개
  5. '이전 대화' 같은 외부 참조 금지(자기완결성)
  6. PRD 미결 중 "step N 전" 으로 못박힌 항목이 아직 미확정이면 실패 — P1 step 19·20 이 D2 로 즉시 blocked(59s·71s) 된 회귀
  7. step.timeout(초) 은 정수 · 리뷰(review*)·게이트(gate*) step 은 timeout 명시 권장(경고) — 1800s 로는 부족(P1 step 22·23, ADR-050)
사용: python3 scripts/lint_phase.py <phase-dir>   (exit 0 = 통과)
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["## 읽어야 할 파일", "## 작업", "## Acceptance Criteria", "## 검증 절차", "## 금지사항"]
CMD_RE = re.compile(r"^\s*(npm|npx|pnpm|python3|pytest|bash|sh|node|lhci|docker|curl)\b", re.M)
EXTERNAL_REF = re.compile(r"이전 대화|앞서 논의|위에서 말한|as discussed")

def lint(phase: str) -> list[str]:
    errs = []
    d = ROOT / "phases" / phase
    idx_p = d / "index.json"
    if not idx_p.exists():
        return [f"{idx_p} 없음"]
    idx = json.loads(idx_p.read_text())
    steps = idx.get("steps", [])
    if not steps:
        return ["steps 비어 있음"]
    for i, s in enumerate(steps):
        if s.get("step") != i:
            errs.append(f"step 순번 불연속: index {i} 에 step={s.get('step')}")
        if s.get("runner") not in ("claude", "codex"):
            errs.append(f"step{i} '{s.get('name')}': runner 미명시 (claude|codex)")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(s.get("name", ""))):
            errs.append(f"step{i}: name 은 kebab-case 여야 함 ({s.get('name')})")
        f = d / f"step{i}.md"
        if not f.exists():
            errs.append(f"{f.name} 없음"); continue
        t = f.read_text()
        for sec in REQUIRED:
            if sec not in t:
                errs.append(f"{f.name}: 섹션 누락 {sec}")
        ac = t.split("## Acceptance Criteria", 1)[1].split("## ", 1)[0] if "## Acceptance Criteria" in t else ""
        if not CMD_RE.search(ac):
            errs.append(f"{f.name}: AC 에 실행 가능한 커맨드 없음")
        if EXTERNAL_REF.search(t):
            errs.append(f"{f.name}: 외부 참조('이전 대화' 등) — 자기완결 위반")
    if steps[-1].get("name") != "retro":
        errs.append("마지막 step 은 'retro' 여야 함 (PRD §17)")
    if steps[-1].get("runner") == "codex" and steps[-1].get("name") == "retro":
        errs.append("retro step 의 runner 는 claude (문서·판단)")
    for s in steps:
        t = s.get("timeout")
        if t is not None and (not isinstance(t, int) or t <= 0):
            errs.append(f"step{s.get('step')}: timeout 은 양의 정수(초)")
        name = str(s.get("name", ""))
        if t is None and s.get("status") == "pending" and re.match(r"(review|gate)", name):
            print(f"  WARN step{s.get('step')} '{name}': 리뷰·게이트 step 은 timeout 명시 권장(기본 1800s 로 부족 — ADR-050)")
    errs += lint_prd_open_items(steps)
    return errs

def lint_prd_open_items(steps: list) -> list[str]:
    """PRD '## 미결' 중 '<step N> 전' 으로 못박힌 항목이 미확정이면, 그 step 이 pending 일 때 실패(D2 즉시 blocked 예방)."""
    prd = ROOT / "docs" / "PRD.md"
    if not prd.exists():
        return []
    text = prd.read_text()
    m = re.search(r"^## 미결.*?(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return []
    pending = {s["step"] for s in steps if s.get("status") == "pending"}
    errs = []
    for line in m.group(0).splitlines():
        if not re.match(r"^\d+\.", line) or "확정" in line:
            continue
        for n in re.findall(r"step (\d+) 전", line):
            if int(n) in pending:
                errs.append(f"PRD 미결 '{line[:40]}…' 은 step {n} 전에 확정해야 함 — 확정 없이 실행하면 D2 로 즉시 blocked")
    return errs

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(2)
    e = lint(sys.argv[1])
    if e:
        print("phase lint FAILED:"); [print("  -", x) for x in e]; sys.exit(1)
    print(f"phase lint OK: {sys.argv[1]}")
