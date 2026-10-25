#!/usr/bin/env python3
"""환자 카드 → (조건 요약, 지침별 검색 질의, LLM 판정 프롬프트)  — RAG 팀에 넘기는 입력 생성
실행: python3 build_queries.py cards_eval20.jsonl queries_eval20.jsonl
조건 계산 함수는 rule_judge/rule_judge_kr.py 의 것을 그대로 가져온다 (규칙 판정과 같은 눈으로 카드를 읽게).
"""
import json, sys, os
sys.argv_backup = sys.argv[:]
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "rule_judge", "rule_judge_kr.py"), encoding="utf-8").read().split('if __name__ == "__main__":')[0]
ns = {}; exec(src, ns); cap_severity, cap_risks, uti_sepsis = ns["cap_severity"], ns["cap_risks"], ns["uti_sepsis"]

KO = {"severe": "중증", "nonsevere": "비중증", "unknown": "중증도 미확정(활력징후 일부 없음)", "yes": "있음", "no": "없음"}
EN = {"severe": "severe", "nonsevere": "non-severe", "unknown": "severity undetermined (some vitals missing)", "yes": "present", "no": "absent"}

def features(c):
    f = {"group": c["cohort_group"], "regimen": sorted({e["ingredient"] for e in c["empirical_regimen"]})}
    if c["cohort_group"] == "pneumonia":
        sev, detail = cap_severity(c); mrsa, pa = cap_risks(c)
        f.update(severity=sev, severity_detail=detail, mrsa_risk=mrsa, pseudomonas_risk=pa)
    else:
        sep, detail = uti_sepsis(c); f.update(sepsis_at_t0=sep, sepsis_detail=detail)
    return f

def queries(c, f):
    """지침 그룹별 검색 질의. K = 국내(K02/K04), M = 해외(M03/M04/M07), W = WHO(W01/W02)"""
    if f["group"] == "pneumonia":
        s, m, p = f["severity"], f["mrsa_risk"], f["pseudomonas_risk"]
        pa_ko = "있음" if p == "yes" else "없음" if p == "no" else "일부(입원력 또는 정주 항생제 중 하나)"
        return {
          "K02": f"국내 지역사회획득폐렴 실무지침 표 4: 입원 성인, {KO[s]}, MRSA 집락 이력 {'있음' if m else '없음'}, 90일 내 입원력·정주 항생제 사용력 {pa_ko}인 환자의 경험적 항생제 추천 약제와 대안 약제, 각 용량·경로·투여 빈도는?",
          "M03": f"IDSA/ATS 2019 community-acquired pneumonia guideline: standard empiric inpatient regimen and alternatives, with doses, for {EN[s]} CAP, prior respiratory MRSA isolation {'present' if m else 'absent'}, hospitalization with IV antibiotics in the past 90 days {EN.get(p, 'partly present')}.",
          "W01": "WHO AWaRe antibiotic book, community-acquired pneumonia in adults, severe (hospital) presentation: first-choice and second-choice empiric antibiotics with dose, route and frequency."}
    s = f["sepsis_at_t0"]
    return {
      "K04": f"국내 요로감염 실무지침 표 5: 전신 요로감염(신우신염) 입원 환자, 패혈증 {'동반' if s == 'yes' else '없음' if s == 'no' else '여부 미확정'}, 주사제 치료의 추천 약제와 대안 약제는? 기관 감수성 자료가 없을 때의 주의사항(각주)은?",
      "M07": f"IDSA 2025 complicated urinary tract infection guideline: recommended empiric antibiotics for a hospitalized adult with pyelonephritis / complicated UTI {'with sepsis' if s == 'yes' else 'without sepsis' if s == 'no' else '(sepsis status undetermined)'}, including when to use carbapenems.",
      "W01": "WHO AWaRe antibiotic book, upper urinary tract infection / pyelonephritis in adults, severe (hospital) presentation: first-choice and second-choice empiric antibiotics with dose, route and frequency."}

PROMPT = """당신은 감염내과 지침 준수를 판정하는 보조자다. 아래 [환자 카드]와 [검색된 지침 구절]만 사용한다. 카드에 없는 정보는 '모름'으로 두고, 지침 구절에 없는 권고를 지어내지 않는다.

[환자 카드]
{card}

[검색된 지침 구절]  (각 구절은 file, page, section, chunk_id, text 를 가진다)
{chunks}

할 일
1. 카드 값만으로 지침의 분류 조건을 판단한다 (폐렴: 중증 여부 · MRSA 집락 이력 · 90일 내 입원/정주 항생제; 요로감염: 패혈증 여부). 판단에 쓴 카드 값을 적는다.
2. 해당하는 권고 행(추천 약제 · 대안 약제)을 검색된 구절에서 찾아 인용한다. 없으면 "해당 구절 없음"이라고 쓴다.
3. 환자의 초기 요법(empirical_regimen)을 그 권고와 성분 집합으로 비교한다. 판정값은 아래 8개 중 하나만 쓴다.
   준수(추천) / 준수(대안) / 비준수(누락) / 비준수(과잉) / 비준수(다른 약제) / 정당한 이탈 / 해당 없음 / 판정 불가
   - 추천 조합의 일부만 썼으면 비준수(누락), 추천 조합에 설명되지 않는 약제를 더했으면 비준수(과잉)이다. 약제 개수 비율로 점수를 매기지 않는다.
   - 정당한 이탈은 카드 안에 근거(위험인자 · 과거 분리균 · 금기 등)가 있을 때만 쓰고 근거를 적는다.
   - 조건이 '모름'이라 결론이 갈리면 판정 불가로 두고 무엇이 없는지 적는다.
4. 아래 JSON만 출력한다.
{{"case_id": "...", "guideline_id": "...",
  "classification": {{"severity_or_sepsis": "...", "mrsa_risk": "...", "pseudomonas_risk": "...", "card_values_used": ["..."]}},
  "applicable_rule": {{"row": "...", "recommended": ["..."], "alternative": ["..."], "file": "...", "page": 0, "section": "...", "chunk_id": "...", "quote": "..."}},
  "regimen": ["..."], "verdict": "...", "reason": "...", "extra_agents": ["..."], "missing_agents": ["..."],
  "dose_check": [{{"agent": "...", "ordered": "...", "guideline": "...", "ok": true}}],
  "justified_deviation_evidence": "...", "confidence": 0.0}}
"""

def build(c):
    f = features(c); q = queries(c, f)
    card = {k: v for k, v in c.items() if k != "not_included"}
    return {"case_id": c["case_id"], "group": c["cohort_group"], "features": f, "queries": q,
            "prompt": PROMPT.replace("{card}", json.dumps(card, ensure_ascii=False, indent=1)).replace("{chunks}", "<<여기에 검색 결과 상위 5개를 넣는다>>")}

if __name__ == "__main__":
    inp, out = sys.argv[1], sys.argv[2]
    with open(inp, encoding="utf-8") as fi, open(out, "w", encoding="utf-8") as fo:
        n = 0
        for line in fi:
            fo.write(json.dumps(build(json.loads(line)), ensure_ascii=False) + "\n"); n += 1
    print("wrote", out, n)
