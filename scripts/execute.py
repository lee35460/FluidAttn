#!/usr/bin/env python3
"""
Harness Step Executor — phase 내 step을 순차 실행하고 자가 교정한다.

Usage:
    python3 scripts/execute.py <phase-dir> [--push]
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def progress_indicator(label: str):
    """터미널 진행 표시기. with 문으로 사용하며 .elapsed 로 경과 시간을 읽는다."""
    frames = "◐◓◑◒"
    stop = threading.Event()
    t0 = time.monotonic()

    def _animate():
        idx = 0
        while not stop.wait(0.12):
            sec = int(time.monotonic() - t0)
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {label} [{sec}s]")
            sys.stderr.flush()
            idx += 1
        sys.stderr.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stderr.flush()

    th = threading.Thread(target=_animate, daemon=True)
    th.start()
    info = types.SimpleNamespace(elapsed=0.0)
    try:
        yield info
    finally:
        stop.set()
        th.join()
        info.elapsed = time.monotonic() - t0


class StepExecutor:
    """Phase 디렉토리 안의 step들을 순차 실행하는 하네스."""

    MAX_RETRIES = 3
    # step 당 실행기 상한(초). 프로토타입·컴포넌트처럼 긴 step 은 HARNESS_STEP_TIMEOUT 로 늘린다(호출 시점에 읽음).
    STEP_TIMEOUT = 1800
    FEAT_MSG = "feat({phase}): step {num} — {name}"
    CHORE_MSG = "chore({phase}): step {num} output"
    TZ = timezone(timedelta(hours=9))

    RUNNERS = {
        # 강의 Part2 Ch01 #17 역할 분담: Claude = 설계·기획·리뷰·하네스 운영 / Codex = 구현·반복·병렬·격리.
        # step 의 "runner" 필드(index.json)가 우선, 없으면 --runner 기본값. codex 는 AGENTS.md 를 먼저 읽는다(finsight 패턴).
        # claude 는 stream-json: `json` 은 종료 시에만 출력해 timeout 이면 stdout 0 으로 흔적이 없었다(P1 step 22, ADR-050).
        "claude": ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"],
        "codex": ["codex", "exec", "--json", "--dangerously-bypass-approvals-and-sandbox"],
    }

    def __init__(self, phase_dir_name: str, *, auto_push: bool = False,
                 runner: str = "codex", report_mcp: bool = False):
        self._runner_default = runner
        self._report_mcp = report_mcp
        self._root = str(ROOT)
        self._phases_dir = ROOT / "phases"
        self._phase_dir = self._phases_dir / phase_dir_name
        self._phase_dir_name = phase_dir_name
        self._top_index_file = self._phases_dir / "index.json"
        self._auto_push = auto_push

        if not self._phase_dir.is_dir():
            print(f"ERROR: {self._phase_dir} not found")
            sys.exit(1)

        self._index_file = self._phase_dir / "index.json"
        if not self._index_file.exists():
            print(f"ERROR: {self._index_file} not found")
            sys.exit(1)

        idx = self._read_json(self._index_file)
        self._project = idx.get("project", "project")
        self._phase_name = idx.get("phase", phase_dir_name)
        self._total = len(idx["steps"])

    def run(self):
        self._print_header()
        self._lint_phase()
        self._check_blockers()
        self._checkout_branch()
        guardrails = self._load_guardrails()
        self._ensure_created_at()
        self._execute_all_steps(guardrails)
        self._finalize()

    def _lint_phase(self):
        """execute 전 step 7원칙 검사 (scripts/lint_phase.py). 실패 시 즉시 중단 — 잘못 설계된 step 을 실행하지 않는다."""
        lint = ROOT / "scripts" / "lint_phase.py"
        if not lint.exists():
            return
        r = subprocess.run([sys.executable, str(lint), self._phase_dir_name], cwd=self._root, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout.strip() or r.stderr.strip())
            sys.exit(1)

    # --- timestamps ---

    def _stamp(self) -> str:
        return datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- JSON I/O ---

    @staticmethod
    def _read_json(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(p: Path, data: dict):
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- git ---

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        cmd = ["git"] + list(args)
        return subprocess.run(cmd, cwd=self._root, capture_output=True, text=True)

    def _checkout_branch(self):
        branch = f"feat-{self._phase_name}"

        r = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            print(f"  ERROR: git을 사용할 수 없거나 git repo가 아닙니다.")
            print(f"  {r.stderr.strip()}")
            sys.exit(1)

        if r.stdout.strip() == branch:
            return

        r = self._run_git("rev-parse", "--verify", branch)
        r = self._run_git("checkout", branch) if r.returncode == 0 else self._run_git("checkout", "-b", branch)

        if r.returncode != 0:
            print(f"  ERROR: 브랜치 '{branch}' checkout 실패.")
            print(f"  {r.stderr.strip()}")
            print(f"  Hint: 변경사항을 stash하거나 commit한 후 다시 시도하세요.")
            sys.exit(1)

        print(f"  Branch: {branch}")

    def _commit_step(self, step_num: int, step_name: str):
        output_rel = f"phases/{self._phase_dir_name}/step{step_num}-output.json"
        index_rel = f"phases/{self._phase_dir_name}/index.json"

        self._run_git("add", "-A")
        self._run_git("reset", "HEAD", "--", output_rel)
        self._run_git("reset", "HEAD", "--", index_rel)

        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.FEAT_MSG.format(phase=self._phase_name, num=step_num, name=step_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")
            else:
                print(f"  WARN: 코드 커밋 실패: {r.stderr.strip()}")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.CHORE_MSG.format(phase=self._phase_name, num=step_num)
            r = self._run_git("commit", "-m", msg)
            if r.returncode != 0:
                print(f"  WARN: housekeeping 커밋 실패: {r.stderr.strip()}")

    # --- top-level index ---

    def _update_top_index(self, status: str):
        if not self._top_index_file.exists():
            return
        top = self._read_json(self._top_index_file)
        ts = self._stamp()
        for phase in top.get("phases", []):
            if phase.get("dir") == self._phase_dir_name:
                phase["status"] = status
                ts_key = {"completed": "completed_at", "error": "failed_at", "blocked": "blocked_at", "running": "started_at"}.get(status)
                if ts_key:
                    phase[ts_key] = ts
                break
        self._write_json(self._top_index_file, top)

    # --- guardrails & context ---

    def _load_guardrails(self) -> str:
        sections = []
        # codex 는 AGENTS.md 를 우선 읽고, claude 는 CLAUDE.md. 없으면 서로 폴백.
        order = ("AGENTS.md", "CLAUDE.md") if getattr(self, "_runner_default", "codex") == "codex" else ("CLAUDE.md", "AGENTS.md")
        guide = next((ROOT / n for n in order if (ROOT / n).exists()), None)
        if guide is not None:
            sections.append(f"## 프로젝트 규칙 ({guide.name})\n\n{guide.read_text()}")
        docs_dir = ROOT / "docs"
        if docs_dir.is_dir():
            # 문서 지도(README.md)만 inline, 나머지는 경로 목록. docs/*.md 전부 inline 은 step 당 ~150K chars 의
            # 고정 프리앰블이 되어 매 turn 다시 읽혔다(P1 step 6, ADR-048). 무엇을 읽을지는 step.md 의 "읽어야 할 문서" 가 정한다.
            readme = docs_dir / "README.md"
            if readme.exists():
                sections.append(f"## 문서 지도 (docs/README.md)\n\n{readme.read_text()}")
            others = [d for d in sorted(docs_dir.glob("*.md")) if d.name != "README.md"]
            if others:
                sections.append("## 문서 (step 의 '읽어야 할 문서' 만 읽어라)\n\n"
                                + "\n".join(f"- docs/{d.name}" for d in others))
        return "\n\n---\n\n".join(sections) if sections else ""

    @staticmethod
    def _build_step_context(index: dict) -> str:
        lines = [
            f"- Step {s['step']} ({s['name']}): {s['summary']}"
            for s in index["steps"]
            if s["status"] == "completed" and s.get("summary")
        ]
        if not lines:
            return ""
        return "## 이전 Step 산출물\n\n" + "\n".join(lines) + "\n\n"

    def _build_preamble(self, guardrails: str, step_context: str,
                        prev_error: Optional[str] = None) -> str:
        commit_example = self.FEAT_MSG.format(
            phase=self._phase_name, num="N", name="<step-name>"
        )
        retry_section = ""
        if prev_error:
            retry_section = (
                f"\n## ⚠ 이전 시도 실패 — 아래 에러를 반드시 참고하여 수정하라\n\n"
                f"{prev_error}\n\n---\n\n"
            )
        return (
            f"당신은 {self._project} 프로젝트의 개발자입니다. 아래 step을 수행하세요.\n\n"
            f"{guardrails}\n\n---\n\n"
            f"{step_context}{retry_section}"
            f"## 작업 규칙\n\n"
            f"1. 이전 step에서 작성된 코드를 확인하고 일관성을 유지하라.\n"
            f"2. 이 step에 명시된 작업만 수행하라. 추가 기능이나 파일을 만들지 마라.\n"
            f"3. 기존 테스트를 깨뜨리지 마라.\n"
            f"4. AC(Acceptance Criteria) 검증을 직접 실행하라.\n"
            f"5. /phases/{self._phase_dir_name}/index.json의 해당 step status를 업데이트하라:\n"
            f"   - AC 통과 → \"completed\" + \"summary\" 필드에 이 step의 산출물을 한 줄로 요약\n"
            f"   - {self.MAX_RETRIES}회 수정 시도 후에도 실패 → \"error\" + \"error_message\" 기록\n"
            f"   - 사용자 개입이 필요한 경우 (API 키, 인증, 수동 설정 등) → \"blocked\" + \"blocked_reason\" 기록 후 즉시 중단\n"
            f"6. 모든 변경사항을 커밋하라:\n"
            f"   {commit_example}\n"
            f"7. 게이트 경계(ADR-050): step 의 게이트는 AC + verify-gate(lint·build·test) 까지다. "
            f"GPU 벤치마크·긴 학습 실행 같은 부가 검증은 돌리지 마라(P1 step 20 timeout 원인).\n"
            f"8. 검증 도구의 환경 오탐(도구 부재·다른 세션 감지 등)은 디버깅하지 말고 summary/사유에 한 줄 적고 넘어가라(P1 step 18·19 timeout 원인).\n"
            f"9. timeout 예산의 마지막 20% 는 커밋·status 갱신에 써라. 작업이 끝났으면 부가 검증보다 커밋이 먼저다.\n"
            f"10. 리뷰 수정 step(ADR-049): 회귀 테스트에 인자를 추가해 통과시키지 마라 — 계약이 바뀌면 summary 에 명시. "
            f"CRITICAL 규칙(AGENTS.md)에 닿는 수정은 규칙 원문을 먼저 인용하고 설계를 고정한 뒤 고쳐라. "
            f"서비스 테스트는 최소 1 케이스를 실제 협력 서비스로 결선하라(memory 대역만으로 통과 금지).\n"
            f"11. 이 세션은 비대화형이다(`codex exec`/`claude -p`). 설계·진행 여부를 묻는 질문으로 턴을 끝내지 마라 — 답할 사람이 없다. "
            f"판단이 필요하면 step.md 의 규칙 안에서 스스로 정하고 summary 에 적어라(P1.5 step 3 이 \"이 설계대로 진행해도 될까요?\" 로 끝나 blocked).\n\n---\n\n"
        )

    def _dirty_worktree_hint(self) -> str:
        """timeout 시 워킹트리 상태 — P1 step 18·19·20·22 는 전부 '작업 완료 후 부가 검증 중' timeout 이었다(ADR-050).
        미커밋 파일이 있으면 같은 비용으로 재실행하지 말고 AC 를 직접 돌려 통과 시 커밋·completed 로 마무리하라는 힌트를 사유에 남긴다."""
        try:
            r = subprocess.run(["git", "status", "--porcelain"], cwd=self._root, capture_output=True, text=True, timeout=30)
            files = [l[3:] for l in r.stdout.splitlines() if l.strip() and not l[3:].startswith("phases/")]
        except Exception:
            return "워킹트리 잔여 작업을 검증 후 커밋하거나 되돌리고 재개"
        if not files:
            return "워킹트리 깨끗 — 실행기가 커밋까지 마쳤는지 git log 확인 후 status 만 갱신하거나 되돌리고 재개"
        shown = ", ".join(files[:5]) + (" …" if len(files) > 5 else "")
        return (f"미커밋 {len(files)} 파일({shown}) — 작업 완료 후 검증 단계에서 끊긴 형태일 가능성이 큼. "
                f"AC 를 직접 실행해 통과하면 커밋 + completed 로 마무리하고, **같은 비용으로 재실행하지 마라**(ADR-048/050)")

    # --- 세션 한도 ---

    @staticmethod
    def _runner_result_text(output: dict) -> str:
        """실행기 stdout 에서 최종 result 문구. `--output-format json`(객체 하나) 과 stream-json(줄마다 객체, 마지막 type=result) 둘 다."""
        stdout = output.get("stdout") or ""
        parsed = None
        try:
            parsed = json.loads(stdout or "{}")
        except (json.JSONDecodeError, TypeError):
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("type") == "result":
                    parsed = obj
                    break
        if not isinstance(parsed, dict):
            return ""
        return str(parsed.get("result") or "") if parsed.get("is_error") else ""

    @staticmethod
    def limit_hit(text: str) -> Optional[str]:
        """실행기 최종 문구가 구독 한도면 그 종류("weekly" | "session"), 아니면 None."""
        import re
        m = re.search(r"\b(weekly|session)\s+limit\b", text, re.I)
        return m.group(1).lower() if m else None

    @classmethod
    def session_limit_wait(cls, text: str, now: "datetime") -> Optional[int]:
        """'You've hit your session limit · resets 7:10am (Asia/Seoul)' → 리셋까지 남은 초(+60). 해당 없으면 None."""
        import re
        m = re.search(r"session limit.*?resets\s+(\d{1,2}):(\d{2})\s*(am|pm)", text, re.I)
        if not m:
            return None
        hour, minute, ampm = int(m.group(1)) % 12, int(m.group(2)), m.group(3).lower()
        if ampm == "pm":
            hour += 12
        reset = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if reset <= now:
            reset += timedelta(days=1)
        return int((reset - now).total_seconds()) + 60

    # --- 에이전트 호출 (runner 디스패치: claude | codex) ---

    def _runner_for(self, step: dict) -> str:
        r = step.get("runner") or self._runner_default
        if r not in self.RUNNERS:
            print(f"  ERROR: unknown runner '{r}' ({'|'.join(self.RUNNERS)})")
            sys.exit(1)
        return r

    def _invoke_agent(self, step: dict, preamble: str, attempt: int = 1) -> dict:
        step_num, step_name = step["step"], step["name"]
        step_file = self._phase_dir / f"step{step_num}.md"

        if not step_file.exists():
            print(f"  ERROR: {step_file} not found")
            sys.exit(1)

        runner = self._runner_for(step)
        prompt = preamble + step_file.read_text()
        # 우선순위: step.timeout(index.json, 설계 시점 — 게이트·리뷰 step 은 1800s 로 부족) > HARNESS_STEP_TIMEOUT(호출 시점) > 기본값
        timeout = int(step.get("timeout") or os.environ.get("HARNESS_STEP_TIMEOUT", self.STEP_TIMEOUT))
        timed_out = False
        try:
            # claude -p 는 백그라운드 작업(리뷰 Workflow·서브에이전트)을 600s 만 기다리고 종료한다 — step timeout 이 상한이 되도록 무제한(P2 step 14 review-core 가 status 미갱신 blocked).
            env = {**os.environ, "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "0"}
            result = subprocess.run(
                self.RUNNERS[runner] + [prompt],
                cwd=self._root, capture_output=True, text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as e:
            # timeout 은 기록이 가장 필요한 순간이다 — 부분 stdout 을 버리지 말고 output 파일에 남긴다(P1 step 10, ADR-048).
            timed_out = True
            returncode = None
            stdout = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            print(f"\n  WARN: {runner} 가 {timeout}s timeout 으로 강제 종료됨 — 부분 출력 {len(stdout)} chars 보존")

        if not timed_out and returncode != 0:
            print(f"\n  WARN: {runner} 가 비정상 종료됨 (code {returncode})")
            if stderr:
                print(f"  stderr: {stderr[:500]}")

        output = {
            "step": step_num, "name": step_name, "runner": runner, "attempt": attempt,
            "exitCode": returncode, "timedOut": timed_out, "timeoutSec": timeout,
            "stdout": stdout, "stderr": stderr,
        }
        # attempt 별로 남긴다 — blocked 재개·재시도가 이전 회차의 turns·비용을 덮어쓰지 않게. step<N>-output.json 은 최신 복사본.
        suffix = f"{attempt}"
        text = json.dumps(output, indent=2, ensure_ascii=False)
        (self._phase_dir / f"step{step_num}-output.{suffix}.json").write_text(text, encoding="utf-8")
        (self._phase_dir / f"step{step_num}-output.json").write_text(text, encoding="utf-8")

        return output

    # --- 플랫폼 보고 (M1: run_report) ---

    def _report(self, step: dict, status: str, extra: dict):
        """--report-mcp: step 결과를 AX 플랫폼 run_report 로 보고. P1 에서 HTTP MCP 클라이언트로 구현.
        지금은 phases/<phase>/report.jsonl 에 append 하고, AX_MCP_URL 이 있으면 POST 를 시도한다."""
        if not self._report_mcp:
            return
        rec = {"ts": self._stamp(), "phase": self._phase_name, "step": step["step"], "name": step["name"],
               "status": status, **extra}
        if os.environ.get("AX_RUN_ID"):
            rec["run_id"] = os.environ["AX_RUN_ID"]
        with open(self._phase_dir / "report.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        url, token = os.environ.get("AX_MCP_URL"), os.environ.get("AX_TOKEN")
        if url and token:
            try:
                import urllib.request
                req = urllib.request.Request(url.rstrip("/") + "/run_report", data=json.dumps(rec).encode(),
                                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10)
            except Exception as e:  # 보고 실패는 실행을 막지 않는다 (X12: 로컬 정본 우선)
                print(f"  WARN: run_report 실패 — {e}")

    # --- 헤더 & 검증 ---

    def _print_header(self):
        print(f"\n{'='*60}")
        print(f"  Harness Step Executor")
        print(f"  Phase: {self._phase_name} | Steps: {self._total}")
        if self._auto_push:
            print(f"  Auto-push: enabled")
        print(f"{'='*60}")

    def _check_blockers(self):
        index = self._read_json(self._index_file)
        for s in reversed(index["steps"]):
            if s["status"] == "error":
                print(f"\n  ✗ Step {s['step']} ({s['name']}) failed.")
                print(f"  Error: {s.get('error_message', 'unknown')}")
                print(f"  Fix and reset status to 'pending' to retry.")
                sys.exit(1)
            if s["status"] == "blocked":
                print(f"\n  ⏸ Step {s['step']} ({s['name']}) blocked.")
                print(f"  Reason: {s.get('blocked_reason', 'unknown')}")
                print(f"  Resolve and reset status to 'pending' to retry.")
                sys.exit(2)
            if s["status"] != "pending":
                break

    def _ensure_created_at(self):
        index = self._read_json(self._index_file)
        if "created_at" not in index:
            index["created_at"] = self._stamp()
            self._write_json(self._index_file, index)

    # --- 실행 루프 ---

    def _execute_single_step(self, step: dict, guardrails: str) -> bool:
        """단일 step 실행 (재시도 포함). 완료되면 True, 실패/차단이면 False."""
        step_num, step_name = step["step"], step["name"]
        done = sum(1 for s in self._read_json(self._index_file)["steps"] if s["status"] == "completed")
        prev_error = None
        waited_for_limit = False

        attempt = 0
        while attempt < self.MAX_RETRIES:
            attempt += 1
            index = self._read_json(self._index_file)
            step_context = self._build_step_context(index)
            preamble = self._build_preamble(guardrails, step_context, prev_error)

            tag = f"Step {step_num}/{self._total - 1} ({done} done): {step_name}"
            if attempt > 1:
                tag += f" [retry {attempt}/{self.MAX_RETRIES}]"

            with progress_indicator(tag) as pi:
                output = self._invoke_agent(step, preamble, attempt=attempt)
            elapsed = int(pi.elapsed)  # .elapsed 는 with 종료(finally) 후에만 채워진다

            # 세션 한도: 재시도를 태우지 않고 리셋 시각까지 기다린 뒤 같은 attempt 로 재실행 (한 attempt 당 최대 1회 대기).
            # 주간 한도는 리셋이 멀어 대기하지 않고 ADR-048 blocked 로 간다. cursor 폴백은 없다(ADR-053).
            wait = self.session_limit_wait(self._runner_result_text(output), datetime.now(self.TZ))
            if wait is not None and not waited_for_limit:
                waited_for_limit = True
                print(f"  ⏳ Step {step_num}: 세션 한도 — {wait // 60}분 대기 후 재실행 (attempt {attempt} 유지)")
                time.sleep(wait)
                attempt -= 1
                continue
            waited_for_limit = False

            index = self._read_json(self._index_file)
            status = next((s.get("status", "pending") for s in index["steps"] if s["step"] == step_num), "pending")
            ts = self._stamp()

            if status == "completed":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["completed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                summary = next((s.get("summary", "") for s in index["steps"] if s["step"] == step_num), "")
                self._report(step, "completed", {"summary": summary, "elapsed": elapsed})
                print(f"  ✓ Step {step_num}: {step_name} [{elapsed}s]")
                return True

            if status == "pending":
                # 실행기가 status 를 전혀 쓰지 않고 끝난 것은 코드 결함이 아니라 세션 한도·중단·timeout 이 대부분이다
                # (P1 step 6 에서 3라운드 × 3회 같은 비용으로 반복). 재시도 대신 사람에게 넘긴다(ADR-048).
                if output.get("timedOut"):
                    reason = (f"실행기({self._runner_for(step)})가 {output.get('timeoutSec')}s timeout 으로 강제 종료 — "
                              f"부분 출력은 step{step_num}-output.{attempt}.json. {self._dirty_worktree_hint()}")
                else:
                    reason = (f"실행기({self._runner_for(step)})가 status 를 갱신하지 않고 종료 — "
                              f"세션 한도·중단 의심. 원인 확인 후 pending 으로 되돌려 재개")
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "blocked"
                        s["blocked_reason"] = reason
                status = "blocked"

            if status == "blocked":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["blocked_at"] = ts
                self._write_json(self._index_file, index)
                reason = next((s.get("blocked_reason", "") for s in index["steps"] if s["step"] == step_num), "")
                self._report(step, "blocked", {"blocked_reason": reason, "elapsed": elapsed})
                print(f"  ⏸ Step {step_num}: {step_name} blocked [{elapsed}s]")
                print(f"    Reason: {reason}")
                self._update_top_index("blocked")
                sys.exit(2)

            err_msg = next(
                (s.get("error_message", "Step did not update status") for s in index["steps"] if s["step"] == step_num),
                "Step did not update status",
            )

            if attempt < self.MAX_RETRIES:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "pending"
                        s.pop("error_message", None)
                self._write_json(self._index_file, index)
                prev_error = err_msg
                print(f"  ↻ Step {step_num}: retry {attempt}/{self.MAX_RETRIES} — {err_msg}")
            else:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "error"
                        s["error_message"] = f"[{self.MAX_RETRIES}회 시도 후 실패] {err_msg}"
                        s["failed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                self._report(step, "error", {"error_message": err_msg, "attempts": self.MAX_RETRIES, "elapsed": elapsed})
                print(f"  ✗ Step {step_num}: {step_name} failed after {self.MAX_RETRIES} attempts [{elapsed}s]")
                print(f"    Error: {err_msg}")
                self._update_top_index("error")
                sys.exit(1)

        return False  # unreachable

    def _execute_all_steps(self, guardrails: str):
        self._update_top_index("running")  # blocked/error 에서 재개해도 상위 index 가 이전 상태로 남지 않게
        while True:
            index = self._read_json(self._index_file)
            pending = next((s for s in index["steps"] if s["status"] == "pending"), None)
            if pending is None:
                print("\n  All steps completed!")
                return

            step_num = pending["step"]
            for s in index["steps"]:
                if s["step"] == step_num and "started_at" not in s:
                    s["started_at"] = self._stamp()
                    self._write_json(self._index_file, index)
                    break

            self._execute_single_step(pending, guardrails)

    def _finalize(self):
        index = self._read_json(self._index_file)
        index["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._update_top_index("completed")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = f"chore({self._phase_name}): mark phase completed"
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  ✓ {msg}")

        if self._auto_push:
            branch = f"feat-{self._phase_name}"
            r = self._run_git("push", "-u", "origin", branch)
            if r.returncode != 0:
                print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  ✓ Pushed to origin/{branch}")

        print(f"\n{'='*60}")
        print(f"  Phase '{self._phase_name}' completed!")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Harness Step Executor")
    parser.add_argument("phase_dir", help="Phase directory name (e.g. 0-mvp)")
    parser.add_argument("--push", action="store_true", help="Push branch after completion")
    parser.add_argument("--runner", choices=["claude", "codex"], default="codex",
                        help="기본 실행기. step index.json 의 'runner' 필드가 우선. 구현=codex, 문서/판단=claude (기본 codex)")
    parser.add_argument("--report-mcp", action="store_true",
                        help="M1 모드: step 결과를 플랫폼 run_report 로 보고 (AX_MCP_URL·AX_TOKEN env)")
    args = parser.parse_args()

    StepExecutor(args.phase_dir, auto_push=args.push, runner=args.runner, report_mcp=args.report_mcp).run()


if __name__ == "__main__":
    main()
