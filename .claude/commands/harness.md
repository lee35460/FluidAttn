이 프로젝트는 Harness 프레임워크를 사용한다. 아래 워크플로우에 따라 작업을 진행하라.

---

## 워크플로우

### A. 탐색

`/docs/` 하위 문서(PRD, ARCHITECTURE, ADR 등)를 읽고 프로젝트의 기획·아키텍처·설계 의도를 파악한다. 필요시 Explore 에이전트를 병렬로 사용한다.

### B. 논의

구현을 위해 구체화하거나 기술적으로 결정해야 할 사항이 있으면 사용자에게 제시하고 논의한다.

### C. Step 설계

사용자가 구현 계획 작성을 지시하면 여러 step으로 나뉜 초안을 작성해 피드백을 요청한다.

설계 원칙:

1. **Scope 최소화** — 하나의 step에서 하나의 레이어 또는 모듈만 다룬다. 여러 모듈을 동시에 수정해야 하면 step을 쪼갠다.
2. **자기완결성** — 각 step 파일은 독립된 Claude 세션에서 실행된다. "이전 대화에서 논의한 바와 같이" 같은 외부 참조는 금지한다. 필요한 정보는 전부 파일 안에 적는다.
3. **사전 준비 강제** — 관련 문서 경로와 이전 step에서 생성/수정된 파일 경로를 명시한다. 세션이 코드를 읽고 맥락을 파악한 뒤 작업하도록 유도한다.
4. **시그니처 수준 지시** — 함수/클래스의 인터페이스만 제시하고 내부 구현은 에이전트 재량에 맡긴다. 단, 설계 의도에서 벗어나면 안 되는 핵심 규칙(멱등성, 보안, 데이터 무결성 등)은 반드시 명시한다.
5. **AC는 실행 가능한 커맨드** — "~가 동작해야 한다" 같은 추상적 서술이 아닌 `python3 -m ruff check . && python3 -m pytest -q` 같은 실제 실행 가능한 검증 커맨드를 포함한다. AC 스크립트가 소스를 grep 할 때는 **파일 단위·문맥 한정**으로 쓴다(전체 src 를 이어붙여 `re.S` 로 `a.*b` 검색 금지 — P1 step 4 에서 `plaintext.*insert` 오탐이 실행기의 식별자 이스케이프 우회를 유도했다). AC 블록 안에 `## ` 로 시작하는 문자열을 넣지 마라(lint_phase 섹션 파서가 잘라낸다).
6. **주의사항은 구체적으로** — "조심해라" 대신 "X를 하지 마라. 이유: Y" 형식으로 적는다.
7. **네이밍** — step name은 kebab-case slug로, 해당 step의 핵심 모듈/작업을 한두 단어로 표현한다 (예: `project-setup`, `api-layer`, `auth-flow`).

### D. 파일 생성

사용자가 승인하면 아래 파일들을 생성한다. 생성 후 `python3 scripts/lint_phase.py {task-name}` 으로 검증한다(runner 명시 · kebab-case · 필수 섹션 5 · AC 실행 커맨드 · 자기완결 · 마지막 step 은 `retro`(runner claude)). 통과 전에는 E 로 넘어가지 않는다.

#### D-1. `phases/index.json` (전체 현황)

여러 task를 관리하는 top-level 인덱스. 이미 존재하면 `phases` 배열에 새 항목을 추가한다.

```json
{
  "phases": [
    {
      "dir": "0-mvp",
      "status": "pending"
    }
  ]
}
```

- `dir`: task 디렉토리명.
- `status`: `"pending"` | `"completed"` | `"error"` | `"blocked"`. execute.py가 실행 중 자동으로 업데이트한다.
- 타임스탬프(`completed_at`, `failed_at`, `blocked_at`)는 execute.py가 상태 변경 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-2. `phases/{task-name}/index.json` (task 상세)

```json
{
  "project": "<프로젝트명>",
  "phase": "<task-name>",
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending", "runner": "codex" },
    { "step": 1, "name": "core-types", "status": "pending", "runner": "codex" },
    { "step": 2, "name": "api-layer", "status": "pending", "runner": "codex" },
    { "step": 3, "name": "retro", "status": "pending", "runner": "claude" }
  ]
}
```

필드 규칙:

- `project`: 프로젝트명 (CLAUDE.md 참조).
- `phase`: task 이름. 디렉토리명과 일치시킨다.
- `steps[].step`: 0부터 시작하는 순번.
- `steps[].name`: kebab-case slug.
- `steps[].status`: 초기값은 모두 `"pending"`.
- `steps[].runner`(선택): `"claude"` | `"codex"`. 없으면 `execute.py --runner` 기본값(codex). **역할 분담(강의 Part2 Ch01 #17)**: 설계·기획·문서·리뷰·판단 step → `claude`, 코드 구현·보일러플레이트·테스트 작성·자동 절차 step → `codex`. step 설계 시 각 step 에 runner 를 명시하라.
- `steps[].timeout`(선택, 초): 없으면 기본 1800. 게이트·리뷰 step(대용량 diff·e2e·Lighthouse·OWASP 를 한 step 안에서 처리)은 3600 이상을 명시하라(ADR-050 — step 10·18·19·20·22 가 전부 1800s 로 부족했다).

상태 전이와 자동 기록 필드:

| 전이 | 기록되는 필드 | 기록 주체 |
|------|-------------|----------|
| → `completed` | `completed_at`, `summary` | Claude 세션 (summary), execute.py (timestamp) |
| → `error` | `failed_at`, `error_message` | Claude 세션 (message), execute.py (timestamp) |
| → `blocked` | `blocked_at`, `blocked_reason` | Claude 세션 (reason), execute.py (timestamp) |

`summary`는 step 완료 시 산출물을 한 줄로 요약한 것으로, execute.py가 다음 step 프롬프트에 컨텍스트로 누적 전달한다. 따라서 다음 step에 유용한 정보(생성된 파일, 핵심 결정 등)를 담아야 한다.

`created_at`은 execute.py가 최초 실행 시 task 레벨에 한 번만 기록한다. step 레벨의 `started_at`도 execute.py가 각 step 시작 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-3. `phases/{task-name}/step{N}.md` (각 step마다 1개)

````markdown
# Step {N}: {이름}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- {이전 step에서 생성/수정된 파일 경로}

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

{구체적인 구현 지시. 파일 경로, 클래스/함수 시그니처, 로직 설명을 포함.
코드 스니펫은 인터페이스/시그니처 수준만 제시하고, 구현체는 에이전트에게 맡겨라.
단, 설계 의도에서 벗어나면 안 되는 핵심 규칙은 명확히 박아넣어라.}

## Acceptance Criteria

```bash
python3 -m ruff check .   # lint 통과
python3 -m pytest -q      # 테스트 통과
```
````

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md 디렉토리 구조를 따르는가?
   - ADR 기술 스택을 벗어나지 않았는가?
   - CLAUDE.md CRITICAL 규칙을 위반하지 않았는가?
3. 결과에 따라 `phases/{task-name}/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- {이 step에서 하지 말아야 할 것. "X를 하지 마라. 이유: Y" 형식}
- 기존 테스트를 깨뜨리지 마라

````

### E. 실행

```bash
python3 scripts/execute.py {task-name}        # 순차 실행
python3 scripts/execute.py {task-name} --push  # 실행 후 push
python3 scripts/execute.py {task-name} --runner claude   # 기본 실행기 변경 (기본 codex; step.runner 가 우선)
python3 scripts/execute.py {task-name} --report-mcp      # M1 모드: step 결과를 phases/<phase>/report.jsonl + (AX_MCP_URL·AX_TOKEN 있으면) 플랫폼 run_report 로 보고
````

execute.py가 자동으로 처리하는 것:

- `feat-{task-name}` 브랜치 생성/checkout
- 가드레일 주입 — (runner=codex 면 AGENTS.md, claude 면 CLAUDE.md) + `docs/README.md`(문서 지도) 본문 + 나머지 `docs/*.md` 는 **경로 목록만**. 무엇을 읽을지는 step.md 의 "읽어야 할 문서" 가 정한다(전부 inline 하면 step 당 ~150K chars 프리앰블 — ADR-048)
- runner 디스패치 — step.runner 또는 --runner 에 따라 `codex exec` / `claude -p --output-format stream-json` 으로 위임(`json` 은 종료 시에만 출력해 timeout 이면 stdout 0 — ADR-050). 실행기가 만든 결과는 **다른 실행기**가 `/review-code` 로 교차 검토(Part2 Ch01 #37)
- **삼권 (ADR-053)** — Claude=판단·문서, Codex=구현, Cursor=대조(`/fix-review` 설계 고정 · 사칭 검사). **`cursor` 를 step.runner 에 쓰지 마라.** claude 구독 한도면 같은 step 을 cursor 로 넘기지 않고 blocked(ADR-048). 훅은 `.cursor/hooks.json` 이 같은 `scripts/hooks/*.sh` 로 잇는다(P-59). P1.5 의 ADR-052 폴백 산출은 유산으로 인정하고 재수행하지 않는다.
- 컨텍스트 누적 — 완료된 step의 summary를 다음 step 프롬프트에 전달
- 자가 교정 — step 이 `error` 를 보고하면 최대 3회 재시도하며, 이전 에러 메시지를 프롬프트에 피드백. **status 를 아예 안 쓰고 끝나면**(세션 한도·중단) 재시도 없이 `blocked` 로 사람에게(ADR-048)
- **리뷰·retro step 은 반드시 하네스(새 `claude -p` 세션)로 실행한다** — 같은 세션이 일하고 판정하면 리뷰 독립성이 깨진다(P1 step 23·24 를 작업 세션이 직접 수행한 것이 위반 사례). timeout 이 부족하면 우회하지 말고 step 의 `timeout` 필드(초, index.json)를 올려라: 리뷰 `/review-code` step 7200 · 게이트 e2e 5400 권장. `lint_phase` 가 리뷰·게이트 step 의 timeout 누락을 경고한다.
- **D5 blocked 해소는 `/fix-review <step> [rN]`** — 수정 프롬프트 규칙(ADR-049)·재리뷰 규모·기록 스크립트(`scripts/review/render-review.py`)가 들어 있다.
- **PRD 미결 선확정** — `lint_phase` 가 PRD 미결 중 "step N 전" 항목이 미확정이면 실패한다(P1 step 19·20 D2 즉시 blocked 예방). phase 시작 전 해당 미결을 grill 로 확정하라.
- **timeout 시 완료·미커밋 감지** — step 이 timeout 으로 끊기면 `git status --porcelain` 을 확인한다. 변경이 있으면(작업은 끝났고 커밋·status 갱신만 못 한 것) "작업 완료·미커밋"으로 `blocked_reason` 에 남기고 재시도하지 않는다 — 사람이 diff 를 확인하고 커밋 여부를 정한다(ADR-050). 변경이 없으면 실제 미완료이므로 error 경로로 재시도한다.
- **게이트 경계** — step AC 의 verify-gate(ruff·pytest) 통과까지가 게이트다. GPU 벤치마크·긴 학습 실행은 step 안에서 돌리지 않는다 — retro 나 사람이 별도로 수행한다(step 10·18·19·20 timeout 이 전부 "작업 완료 후 부가 검증"에서 발생, ADR-050). 작업·검증이 끝난 뒤 남은 시간이 step timeout 의 20% 미만이면 부가 검증 대신 커밋을 우선한다.
- 2단계 커밋 — 코드 변경(`feat`)과 메타데이터(`chore`)를 분리 커밋
- 타임스탬프 — started_at, completed_at, failed_at, blocked_at 자동 기록

에러 복구:

- **재실행 전 공통 (ADR-048)**: ① `phases/{task-name}/report.jsonl` 에서 같은 step 의 마지막 error/blocked 행들을 읽는다 — **같은 원인이 2회 이상이면 재실행하지 않는다**. 원인을 고치거나(코드·step.md·execute.py) DEVLOG 에 기록하고 ADR 로 올린 뒤 사람이 결정한다. "토큰 부족으로 중단됐으니 이어서" 는 재실행 사유가 아니다(P1 step 6 이 같은 이유로 4라운드 · `claude -p` 11회). ② `echo '{"hook_event_name":"SessionStart"}' | bash scripts/hooks/token-guard.sh` 가 `⚠` 면 다른 세션을 먼저 끝낸다.
- **error 발생 시**: `phases/{task-name}/index.json`에서 해당 step의 `status`를 `"pending"`으로 바꾸고 `error_message`를 삭제한 뒤 재실행한다.
- **blocked 발생 시**: `blocked_reason`에 적힌 사유를 해결한 뒤, `status`를 `"pending"`으로 바꾸고 `blocked_reason`을 삭제한 뒤 재실행한다. 사유가 "status 를 갱신하지 않고 종료"(세션 한도·중단)면 리뷰 step 은 실행기 밖 `/review-code` 로 대신하고 결과를 summary 에 적어 수동 `completed` 한다.
