#!/usr/bin/env python3
"""LLM+RAG 판정(JSONL: case_id, verdict, reason …)과 규칙 판정(rule_judge/*.jsonl)을 case_id로 맞춰 일치율 · 불일치 목록을 낸다.
실행: python3 compare_verdicts.py llm_verdicts.jsonl ../rule_judge/eval20_verdicts_intl.jsonl   (MIMIC; K-MIMIC 은 플랫폼 안에서 rule_judge_kr 결과로)
"""
import json, sys
from collections import Counter, defaultdict
def load(p): return {j["case_id"]: j for j in (json.loads(l) for l in open(p, encoding="utf-8") if l.strip())}
llm, rule = load(sys.argv[1]), load(sys.argv[2])
ids = [i for i in rule if i in llm]
ADH = {"준수(추천)", "준수(대안)"}
agree = sum(llm[i]["verdict"] == rule[i]["verdict"] for i in ids)
agree_bin = sum((llm[i]["verdict"] in ADH) == (rule[i]["verdict"] in ADH) for i in ids if rule[i]["verdict"] not in ("해당 없음", "판정 불가") and llm[i]["verdict"] not in ("해당 없음", "판정 불가"))
den_bin = sum(1 for i in ids if rule[i]["verdict"] not in ("해당 없음", "판정 불가") and llm[i]["verdict"] not in ("해당 없음", "판정 불가"))
print(f"비교 대상 {len(ids)}건 · 8값 완전 일치 {agree} ({100*agree/len(ids):.0f}%) · 준수/비준수 이분 일치 {agree_bin}/{den_bin}")
conf = defaultdict(Counter)
for i in ids: conf[rule[i]["verdict"]][llm[i]["verdict"]] += 1
print("\n규칙 판정 → LLM 판정 분포")
for r, c in conf.items(): print(f"  {r:14} → " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
print("\n불일치 사례")
for i in ids:
    if llm[i]["verdict"] != rule[i]["verdict"]:
        print(f"  {i} [{rule[i].get('group','')}] 규칙={rule[i]['verdict']} ({rule[i].get('reason','')[:60]}) | LLM={llm[i]['verdict']} ({llm[i].get('reason','')[:60]})")
just = [i for i in ids if llm[i]["verdict"] == "정당한 이탈"]
print(f"\nLLM이 '정당한 이탈'로 본 사례 {len(just)}건 → 임상의 확인 대상:", just)
