#!/usr/bin/env python3
"""/review-code 워크플로 결과(JSON: {confirmed, stats}) → phases/<phase>/reviews/<step>-review*.md 기록.

P1 에서 step 12·17·23 리뷰마다 같은 파싱·집계를 손으로 4번 했다(3번의 법칙 → 스크립트). 판정은 stats 만으로 계산한다(추정 없음).
사용: python3 scripts/review/render-review.py <out.md> "<제목>" "<범위 한 줄>" <workflow-result.json>
  workflow-result.json = Workflow 태스크 output 의 .result (jq '.result' <task output>) 또는 {confirmed, stats} 그대로.
"""
import json,html,sys
out_path,title,scope_line=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(sys.argv[4])); st=d['stats']
emo={'critical':'🔴','major':'🟠','minor':'🟡','nit':'⚪'}
order={'critical':0,'major':1,'minor':2,'nit':3}
fs=sorted(d['confirmed'],key=lambda f:(order[f['severity']],f['file'],f['line']))
bs=st['bySeverity']
uniq={}
for f in fs:
    k=(f['file'],f['line']//1)
    uniq.setdefault(f['file'],[]).append(f)
bs=st['bySeverity']
verdict='Blocked' if bs['critical']>0 else ('Changes Requested' if bs['major']>0 else 'Approve')
print('판정:',verdict,'|',json.dumps(bs,ensure_ascii=False))
for f in fs:
    print(f"[{f['severity']}|{f['dimension']}|v{f.get('votes')}] {f['file']}:{f['line']} — {f['title']}")
out=[f"# {title}\n",scope_line+"\n",f"## 판정: {verdict}\n",
 f"🔴 critical {bs['critical']} · 🟠 major {bs['major']} · 🟡 minor {bs['minor']} · ⚪ nit {bs['nit']}   (검증 통과 {st['total']['confirmed']}/{st['total']['raw']})\n",
 "\n## 확정 발견 전체 (인라인)\n"]
for f in fs:
    out.append(f"### {emo[f['severity']]} [{f['severity']}] `{f['file']}:{f['line']}` — {f['title']}\n")
    out.append(f"- 차원·표결: {f['dimension']} {f.get('votes')}/3\n")
    out.append(f"- TL;DR: {html.unescape(f['tldr'])}\n")
    if f.get('good'): out.append(f"- ✓ Good: {html.unescape(f['good'])}\n")
    out.append(f"- → Fix:\n\n{html.unescape(f['fix'])}\n\n---\n")
out.append("\n차원별: " + " · ".join(f"{k} {v['confirmed']}/{v['raw']}" for k,v in st['byDim'].items()))
open(out_path,'w').write("\n".join(out))
