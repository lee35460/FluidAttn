export const meta = {
  name: 'review-code',
  description: '차원별 병렬 서브에이전트로 변경분을 리뷰하고 각 발견을 adversarial 검증',
  phases: [
    { title: 'Review', detail: '차원별(correctness·security·conventions) 병렬 리뷰' },
    { title: 'Verify', detail: '각 발견을 3명 skeptic이 반박, 2/3 다수결로 false positive 제거' },
  ],
}

// ── 입력 ─────────────────────────────────────────────────────────────────────
// args = { diff: string, files: string, repoDocs: string, scope?: string }
//   diff:     통합 diff 텍스트 (변경 라인 번호 포함)
//   files:    변경 파일 목록(개행 구분)
//   repoDocs: CLAUDE.md + ARCHITECTURE.md + ADR.md 본문(가드레일)
//   scope:    리뷰 범위 설명 (예: "main...HEAD") — 표시용
let input = args
if (typeof input === 'string') {
  try {
    input = JSON.parse(input)
  } catch {
    input = {}
  }
}
const diff = input?.diff ?? ''
const files = input?.files ?? ''
const repoDocs = input?.repoDocs ?? ''

log(`[review-code] args=${typeof args} diffLen=${diff.length} filesLen=${files.length} docsLen=${repoDocs.length}`)

if (!diff.trim()) {
  log('[review-code] diff가 비어 종료 (입력 전달 확인 필요)')
  return { confirmed: [], stats: { total: { raw: 0, confirmed: 0 }, byDim: {}, bySeverity: {} } }
}

// ── 스키마 ───────────────────────────────────────────────────────────────────
const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'file', 'line', 'title', 'tldr', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['critical', 'major', 'minor', 'nit'] },
          file: { type: 'string', description: '저장소 루트 기준 경로 (예: src/lib/money.ts)' },
          line: { type: 'number', description: 'diff 신규(RIGHT) 측 라인 번호 — 인라인 코멘트 게시용' },
          title: { type: 'string', description: '한 줄 제목' },
          tldr: { type: 'string', description: '무엇이/왜 문제인가 한 줄' },
          good: { type: 'string', description: '잘 지킨 맥락/규칙 (없으면 빈 문자열)' },
          fix: { type: 'string', description: '수정 방안 — 가능하면 코드 스니펫' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['isReal', 'reason'],
  properties: {
    isReal: { type: 'boolean', description: '진짜 문제이며 보고할 가치가 있으면 true' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    reason: { type: 'string', description: '판단 근거 한 줄' },
  },
}

// ── 차원 정의 (MVP 3개) ──────────────────────────────────────────────────────
// 향후 확장: 이 배열에 { key, prompt } 항목을 추가하기만 하면 된다.
const common = (dimensionName) =>
  `너는 AX Platform 코드 리뷰어다. 아래 diff에서 **${dimensionName}** 차원만 검토한다.\n` +
  `\n규칙:\n` +
  `- 이 차원에 해당하는 위반·버그만 보고하라. 다른 차원·스타일 취향·범위 밖 개선은 무시하라.\n` +
  `- 추측성 지적 금지. diff와 가드레일 문서로 확인 가능한 것만 보고하라.\n` +
  `- 발견이 없으면 findings를 빈 배열로 반환하라. 억지로 만들지 마라.\n` +
  `- 각 발견의 file은 저장소 루트 기준 경로, line은 diff 신규(RIGHT) 측 라인 번호로 적어라(인라인 코멘트 게시에 쓰인다).\n` +
  `- good은 해당 위치에서 잘 지킨 규칙/맥락(없으면 빈 문자열), fix는 수정 방안(가능하면 코드).\n` +
  `\nseverity 기준:\n` +
  `- critical: 보안 취약점 · 데이터 무결성 훼손 · 명백한 런타임/로직 버그(머지 차단 수준)\n` +
  `- major: CRITICAL 규칙 위반 · 잘못된 동작(머지 전 수정 필요)\n` +
  `- minor: 개선 권장(머지는 가능)\n` +
  `- nit: 취향/사소\n`

// 집중 검사 항목 = CLAUDE.md CRITICAL 규칙. 규칙이 바뀌면 CLAUDE.md·AGENTS.md·.github/workflows/code-review.yml 과 함께 갱신.
const DIMENSIONS = [
  {
    key: 'correctness',
    prompt:
      common('correctness (정확성·데이터 무결성)') +
      `\n이 차원의 집중 검사 항목(AX CRITICAL 규칙):\n` +
      `- 경로 정규화 후 prefix 검사(users/<본인>/ 한정, traversal 차단)가 빠지거나 순서가 틀리지 않았는가.\n` +
      `- 멱등성: webhook event_id 선삽입, pg-boss singletonKey(git.write single-writer), 재시도 시 중복 부작용.\n` +
      `- 상태 전이: run 8단계 · D0~D9 · 세션(ACTIVE/EXPIRED) · 승격 상태 머신이 허용된 전이만 하는가.\n` +
      `- wiki 정본은 git 마크다운 — DB 에만 존재하는 wiki 내용을 만들거나 repo 에서 재구성 불가능한 상태를 만들지 않는가.\n` +
      `- 테스트가 실제 동작을 검증하는가(항상 통과하는 단언, 구현 세부에만 붙은 테스트, cleanup 누락으로 인한 오염).\n` +
      `- 그 외 일반 로직 버그(off-by-one, null/undefined 처리, 잘못된 비교, 시간대 처리, 셸 스크립트의 인용/이식성).`,
  },
  {
    key: 'security',
    prompt:
      common('security & privacy (보안·개인정보)') +
      `\n이 차원의 집중 검사 항목(AX CRITICAL 규칙):\n` +
      `- 시크릿 필터(정규식+엔트로피)는 서버측에서 모든 wiki_write·트레일 요약에 적용되는가. 클라이언트 값을 신뢰하지 않는가.\n` +
      `- 토큰은 해시 저장, 평문은 발급 시 1회만. NEXT_PUBLIC_ 에 비밀 없음. 회사 API 키는 서버 env 만. 로그·audit 에 시크릿 redact.\n` +
      `- 권한은 서버 DB 상태(role admin/champion/member)로만 판정 — 요청 body/header 의 role·tier 를 신뢰하면 위반.\n` +
      `- shared/ 직접 쓰기 금지(승격 wiki_promote 게이트만). 무인 에이전트(M2/M3·maintainer) 쓰기는 PR, prod 자원 read-only, 도구 화이트리스트·예산·hard limit.\n` +
      `- 웹훅 raw body 서명검증(HMAC) + 멱등. 훅 스크립트(scripts/hooks/*)가 위험 명령·references/ 쓰기를 실제로 차단하는가(우회 가능한 패턴).\n` +
      `- 프로토타입/화면에 실제 토큰·이메일·내부 URL 같은 민감 값이 하드코딩되지 않았는가.`,
  },
  {
    key: 'conventions',
    prompt:
      common('conventions & architecture (컨벤션·아키텍처)') +
      `\n이 차원의 집중 검사 항목(AX CRITICAL 규칙):\n` +
      `- 레이어 의존 단방향: lib/ 는 types/ 만 import(services/·@anthropic-ai/*·@modelcontextprotocol/*·discord.js·simple-git 금지, clsx 같은 순수 유틸 예외). services/ → lib/+types/+adapters/.\n` +
      `- 외부 SDK 는 adapters/ 에서만, 모듈 import 시점이 아니라 호출 시점에 지연 생성(키 없이 build/test 통과).\n` +
      `- wiki repo git 쓰기는 worker git.write 잡만(web/mcp 프로세스 금지). 모든 MCP 도구는 intent 인자. 무인 프롬프트는 wiki skills/<name>/SKILL.md 로드(코드 하드코딩 금지).\n` +
      `- 컴포넌트는 props 만 받는 dumb — 계산·파싱·날짜·진행률 로직은 lib/(TDD). Server Component 기본, 'use client' 는 인터랙션에만. 디렉토리 src/{app,components,server,services,lib,db,adapters,types}.\n` +
      `- UI: 색은 docs/DESIGN.md·.claude/skills/ax-design/colors_and_type.css 토큰만(hex 인라인·bg-[#..] 금지), UI_GUIDE 안티패턴(blur·gradient text·보라/인디고·glow·orb·균일 rounded-2xl·"Powered by AI"·결정 카드 버튼 3개 이상) 금지, 숫자·경로는 JetBrains Mono, Lucide strokeWidth 1.5.\n` +
      `- 하네스: 훅·스킬·에이전트·문서 변경이 같은 커밋에 시나리오(PROCESS_TESTING P-xx)·카탈로그(DEV_ENV)·버전표를 동반하는가. CLAUDE.md ↔ AGENTS.md 동일.`,
  },
]

// ── 검증 폭발 방지 ───────────────────────────────────────────────────────────
const MAX_PER_DIM = 6 // 차원당 검증 대상 finding 상한. 초과분은 log로 고지(silent cap 금지).

// ── skeptic 에게는 해당 파일의 diff 만 ──────────────────────────────────────
// P1 step 6: skeptic 24개가 매번 170KB 전체 diff 를 읽어 회당 $10~16 → 구독 세션 한도 소진(4회 재현).
// 발견은 파일:라인 단위이므로 그 파일의 hunk 만 주고, 필요하면 에이전트가 Read 로 저장소를 직접 본다.
const diffByFile = {}
{
  const parts = diff.split(/^(?=diff --git )/m)
  for (const part of parts) {
    const m = part.match(/^diff --git a\/(\S+) b\/(\S+)/)
    if (m) diffByFile[m[2]] = part
  }
}
const isPointer = Object.keys(diffByFile).length === 0 // diff 대신 파일 경로 안내문이 넘어온 경우(대용량) — 슬라이스 불가
const sliceFor = (file) => diffByFile[file] ?? (isPointer ? diff : `(diff 에 ${file} 의 hunk 가 없다 — Read 로 파일을 직접 확인하라)\n\n${diff.slice(0, 4000)}`)

// ── Review → Verify 파이프라인 ───────────────────────────────────────────────
// pipeline: 한 차원의 발견이 검증되는 동안 다른 차원은 아직 리뷰 중이어도 됨(barrier 불필요).
const results = await pipeline(
  DIMENSIONS,
  // 1단계: 차원별 리뷰
  (d) =>
    agent(
      `${d.prompt}\n\n## 가드레일 문서\n${repoDocs}\n\n## 변경 파일\n${files}\n\n## diff\n${diff}`,
      { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
    ),
  // 2단계: 각 발견을 3명 skeptic이 반박 → 2/3 다수결
  (review, dim) => {
    const found = (review?.findings ?? []).map((f) => ({ ...f, dimension: dim.key }))
    if (found.length > MAX_PER_DIM) {
      log(`${dim.key}: 발견 ${found.length}건 중 상위 ${MAX_PER_DIM}건만 검증(상한). 나머지는 미검증으로 제외.`)
    }
    return parallel(
      found.slice(0, MAX_PER_DIM).map((f) => () =>
        parallel(
          Array.from({ length: 3 }, (_, i) => () =>
            agent(
              `다음 리뷰 발견이 진짜 문제인지 반박하라. 의심부터 하고, 확신이 없으면 isReal=false를 기본값으로 삼아라.\n\n` +
                `[${f.severity}] ${f.title}\n위치: ${f.file}:${f.line}\nTL;DR: ${f.tldr}\n제안된 수정: ${f.fix}\n\n` +
                `아래 diff(해당 파일만)와 가드레일로 교차검증하라. 발견이 실제 변경된 코드에 근거하는지, 오해/허위(예: 존재하지 않는 라인, 이미 처리된 케이스)는 아닌지 확인하라. 다른 파일이 필요하면 Read 로 직접 열어라.\n\n` +
                `## 가드레일 문서\n${repoDocs}\n\n## diff (${f.file})\n${sliceFor(f.file)}`,
              { label: `verify:${dim.key}:${i}`, phase: 'Verify', schema: VERDICT_SCHEMA },
            ),
          ),
        ).then((votes) => {
          const yes = votes.filter(Boolean).filter((v) => v.isReal).length
          return { ...f, real: yes >= 2, votes: yes }
        }),
      ),
    )
  },
)

// ── 집계 ─────────────────────────────────────────────────────────────────────
const all = results.flat().filter(Boolean)
const confirmed = all.filter((f) => f.real)

const byDim = {}
for (const f of all) {
  byDim[f.dimension] = byDim[f.dimension] ?? { raw: 0, confirmed: 0 }
  byDim[f.dimension].raw++
  if (f.real) byDim[f.dimension].confirmed++
}

const bySeverity = { critical: 0, major: 0, minor: 0, nit: 0 }
for (const f of confirmed) bySeverity[f.severity] = (bySeverity[f.severity] ?? 0) + 1

log(
  `검증 완료: 후보 ${all.length}건 → 확정 ${confirmed.length}건 ` +
    `(critical ${bySeverity.critical} · major ${bySeverity.major} · minor ${bySeverity.minor} · nit ${bySeverity.nit})`,
)

return {
  confirmed,
  stats: { total: { raw: all.length, confirmed: confirmed.length }, byDim, bySeverity },
}
