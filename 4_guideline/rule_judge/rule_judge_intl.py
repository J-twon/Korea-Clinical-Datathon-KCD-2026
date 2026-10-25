#!/usr/bin/env python3
"""해외 지침 규칙 판정 — MIMIC-IV 카드용
  폐렴:    M03 ATS/IDSA CAP 2019, Table 4(입원 환자 초기 요법: 중증도 × MRSA/녹농균 위험) + Table 1(2007 중증 기준)   → text/cap_intl.txt 474–519행, 227–253행
  요로감염: M07 IDSA cUTI 2025, Table 1.1(패혈증 유무 × 투여 경로별 Preferred/Alternative)                         → text/cuti_intl.txt
입력 · 출력 · 판정값 8종 · 집계는 rule_judge_kr.py 와 동일. 공통 함수(중증도 · qSOFA · 집합 비교 · 집계)는 같은 폴더의 rule_judge_kr.py 에서 가져온다.
실행: python3 rule_judge_intl.py [--icu-severe] [--class-equiv] [--sepsis-broad-ok] cards.jsonl verdicts.jsonl
  --icu-severe       ICU 입실 환자 = 중증 폐렴으로 가정 (카드 값으로 중증도가 안 정해질 때)
  --class-equiv      teicoplanin→vancomycin, cefotaxime→ceftriaxone, clarithromycin→azithromycin 동등 취급 (MIMIC 에서는 거의 무의미)
  --sepsis-broad-ok  M07 Remark: 패혈증 환자에서 anti-MRSA · 항장구균 추가를 "진단 불확실 시 고려 가능"으로 보고 허용 (기본은 과잉)
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_judge_kr as kr
from rule_judge_kr import cap_severity, uti_sepsis, compare, summary, extra_summary

# ---- M03 Table 4 약제 집합 ----
BL = {"ceftriaxone", "cefotaxime", "ampicillin/sulbactam", "ceftaroline"}                      # † 표준 β-lactam
MACRO = {"azithromycin", "clarithromycin"}                                                      # † macrolide
FQ_RESP = {"levofloxacin", "moxifloxacin"}                                                      # ‡ respiratory FQ
ANTI_MRSA = {"vancomycin", "linezolid"}                                                         # § MRSA 범위
AP_BL = {"piperacillin/tazobactam", "cefepime", "ceftazidime", "imipenem", "meropenem", "aztreonam"}   # ‖ 녹농균 범위
# ---- M07 Table 1.1 약제 집합 ----
CEPH34_IV = {"ceftriaxone", "ceftazidime", "cefotaxime", "cefepime"}
CARBA = {"imipenem", "doripenem", "meropenem", "ertapenem"}
FQ_UTI = {"ciprofloxacin", "levofloxacin"}
NOVEL = {"ceftolozane/tazobactam", "ceftazidime/avibactam", "meropenem/vaborbactam", "imipenem/relebactam", "cefiderocol", "plazomicin"}
AMINOGLY = {"gentamicin", "amikacin", "tobramycin"}
ORAL_REC = FQ_UTI | {"trimethoprim/sulfamethoxazole"}
ORAL_ALT = {"amoxicillin/clavulanate", "cefixime", "cefpodoxime", "ceftibuten", "cefuroxime", "cephalexin"}
ORAL_ROUTES = {"PO", "ORAL", "NG", "PO/NG"}
BROAD = {"vancomycin", "linezolid", "daptomycin", "teicoplanin", "ampicillin", "amoxicillin", "ampicillin/sulbactam"}   # Remark: 녹농균 · 장구균 · MRSA 대상 광범위 추가
NOT_FOR_CUTI = {"nitrofurantoin", "fosfomycin"}

ICU_IMPLIES_SEVERE = False
SEPSIS_BROAD_OK = False

def cap_rows(severity, mrsa_prior, pa_prior, recent):
    """후보 행 [(row_id, S_list, A_list, explained)]. explained = 위험인자로 설명되는 추가 약제 집합"""
    def combos(bls, partners): return [{b, p} for b in bls for p in partners]
    rows = []
    for sev in (["nonsevere", "severe"] if severity == "unknown" else [severity]):
        bls = AP_BL if pa_prior else BL
        if sev == "nonsevere":
            S = combos(bls, MACRO) + ([{f} for f in FQ_RESP] if not pa_prior else [])        # FQ 단독은 녹농균 범위가 아님
            A = combos(bls, {"doxycycline"})                                                   # 본문: macrolide · FQ 금기 시 β-lactam + doxycycline (conditional)
            rid, explained = "M03-T4-비중증" + ("-녹농균이력" if pa_prior else ""), set()      # 비중증: 최근 입원+정맥항생제여도 배양 전 범위 추가는 보류 → 추가는 과잉
        else:
            S = combos(bls, MACRO) + combos(bls, FQ_RESP); A = []
            rid, explained = "M03-T4-중증" + ("-녹농균이력" if pa_prior else ""), set()
            if recent:                                                                         # 중증 + 최근 입원·정맥항생제: MRSA · 녹농균 범위 추가 허용(배양으로 축소)
                explained = ANTI_MRSA | AP_BL; rid += "-최근입원"
                if not pa_prior: S = S + combos(AP_BL, MACRO) + combos(AP_BL, FQ_RESP)
        if mrsa_prior:
            S = [s | {m} for s in S for m in ANTI_MRSA]; A = [a | {m} for a in A for m in ANTI_MRSA]; rid += "+MRSA이력"
        rows.append((rid, S, A, explained))
    return rows

CATEGORY = [("표준 β-lactam(ceftriaxone · cefotaxime · ampicillin/sulbactam · ceftaroline 중 1)", BL), ("항녹농균 β-lactam(pip/tazo · cefepime · ceftazidime · carbapenem · aztreonam 중 1)", AP_BL),
            ("macrolide(azithromycin · clarithromycin)", MACRO), ("respiratory FQ(levofloxacin · moxifloxacin)", FQ_RESP), ("MRSA 범위(vancomycin · linezolid)", ANTI_MRSA), ("doxycycline", {"doxycycline"})]
def missing_text(R, sets):
    """R 을 포함하는 추천 조합들 중 빠진 약제가 가장 적은 것을 골라 계열 이름으로 설명 (특정 약제 이름을 임의로 집지 않도록)"""
    opts = []
    for S in sets:
        if R < S:
            cats = sorted({next((name for name, grp in CATEGORY if a in grp), a) for a in S - R}); opts.append((len(S - R), cats))
    if not opts: return "?"
    cats = min(opts)[1]
    return " + ".join(cats) + (" (macrolide 대신 FQ 조합도 가능)" if any("macrolide" in c for c in cats) and any("respiratory FQ" in c for o in opts for c in o[1]) else "")
def judge_cap(c):
    R = kr.regimen_set(c)
    if not R: return {"verdict": "해당 없음", "reason": "요법 없음"}
    if R == {"cefazolin"}: return {"verdict": "해당 없음", "reason": "cefazolin 단독 — 수술 예방적 투여 의심"}
    sev, sev_detail = cap_severity(c)
    if ICU_IMPLIES_SEVERE and sev != "severe": sev, sev_detail = "severe", "가정: ICU 입실 환자 = 중증 (" + sev_detail + ")"
    h = c["history"]; mrsa_prior = h["mrsa_isolated_within_1y"]; pa_prior = h["pseudomonas_isolated_within_1y"]
    recent = h["admission_within_90d"] and h["iv_antibiotics_within_90d"]
    verdicts = []
    for rid, S, A, explained in cap_rows(sev, mrsa_prior, pa_prior, recent):
        v, why = compare(R, S, A, lambda a: a in explained)
        if v == "비준수(누락)": why = "추천 조합 중 누락: " + missing_text(R, S + A)
        verdicts.append((rid, v, why))
    cats = {v for _, v, _ in verdicts}
    if len(cats) == 1: final, why, row = verdicts[0][1], verdicts[0][2], " / ".join(r for r, _, _ in verdicts)
    else: final, why, row = "판정 불가", "중증도 미확정으로 후보 행 결론이 다름: " + "; ".join(f"{r}→{v}" for r, v, _ in verdicts), "후보 여러 개"
    return {"verdict": final, "reason": why, "row": row, "severity": f"{sev} ({sev_detail})", "mrsa_prior": mrsa_prior, "pa_prior": pa_prior,
            "recent_hosp_iv_abx": recent, "regimen": sorted(R), "candidates": verdicts}

def judge_uti(c):
    R = kr.regimen_set(c)
    if not R: return {"verdict": "해당 없음", "reason": "요법 없음"}
    if R == {"cefazolin"}: return {"verdict": "해당 없음", "reason": "cefazolin 단독 — 수술 예방적 투여 의심"}
    sep, sep_detail = uti_sepsis(c)
    routes = {e["ingredient"]: (e["route"] or "").upper() for e in c["empirical_regimen"]}
    all_oral = all(routes.get(a, "") in ORAL_ROUTES for a in R)
    def verdict_for(sepsis):
        if sepsis == "yes": rec, alt, row = CEPH34_IV | CARBA | {"piperacillin/tazobactam"} | FQ_UTI, NOVEL | AMINOGLY, "M07-T1.1-패혈증"
        elif all_oral: rec, alt, row = ORAL_REC, ORAL_ALT, "M07-T1.1-비패혈증-경구"
        else: rec, alt, row = CEPH34_IV | {"piperacillin/tazobactam"} | FQ_UTI, CARBA | NOVEL | AMINOGLY, "M07-T1.1-비패혈증-정맥"
        in_rec, in_alt = R & rec, R & alt; extras = R - rec - alt
        if in_rec and not extras: return "준수(추천)", f"Preferred 약제 {sorted(in_rec)}", row
        if in_alt and not in_rec and not extras: return "준수(대안)", f"Alternative 약제 {sorted(in_alt)}", row
        if (in_rec or in_alt) and extras:
            if sepsis == "yes" and extras <= BROAD:
                if SEPSIS_BROAD_OK: return ("준수(추천)" if in_rec else "준수(대안)"), f"{sorted(in_rec | in_alt)} + 광범위 추가 {sorted(extras)} (M07 Remark: 패혈증 · 진단 불확실 시 고려 가능 → 허용)", row
                return "비준수(과잉)", f"{sorted(in_rec | in_alt)} + 표에 없는 추가 약제 {sorted(extras)} · M07 Remark: 패혈증에서 진단 불확실 시 고려 가능(조건부)", row
            return "비준수(과잉)", f"{sorted(in_rec | in_alt)} + 표에 없는 추가 약제 {sorted(extras)}", row
        note = " · nitrofurantoin/경구 fosfomycin 은 cUTI 에 부적절(Table 1.1 각주)" if R & NOT_FOR_CUTI else ""
        return "비준수(다른 약제)", f"Preferred · Alternative 에 없는 약제만 사용 {sorted(R)}" + note, row
    cands = ["yes", "no"] if sep == "unknown" else [sep]
    vs = [(s, *verdict_for(s)) for s in cands]
    if len({v for _, v, _, _ in vs}) == 1: final, why, row = vs[0][1], vs[0][2], vs[0][3]
    else: final, why, row = "판정 불가", "패혈증 여부 미확정으로 후보 행 결론이 다름: " + "; ".join(f"패혈증 {s}→{v}" for s, v, _, _ in vs), "후보 여러 개"
    return {"verdict": final, "reason": why, "row": row, "sepsis_at_t0": f"{sep} ({sep_detail})", "regimen": sorted(R), "candidates": [(s, v, w) for s, v, w, _ in vs]}

def run(path, out_path=None):
    from collections import Counter, defaultdict
    res = []; agg = defaultdict(Counter)
    with open(path, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line); g = c["cohort_group"]
            j = judge_cap(c) if g == "pneumonia" else judge_uti(c)
            j.update({"case_id": c["case_id"], "group": g, "era": c["admission_era"], "guideline": "M03 ATS/IDSA CAP 2019" if g == "pneumonia" else "M07 IDSA cUTI 2025"})
            res.append(j); agg[g][j["verdict"]] += 1
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            for j in res: f.write(json.dumps(j, ensure_ascii=False) + "\n")
    return res, agg

if __name__ == "__main__":
    if "--icu-severe" in sys.argv: ICU_IMPLIES_SEVERE = True; sys.argv.remove("--icu-severe")
    if "--class-equiv" in sys.argv: kr.CLASS_EQUIV = True; sys.argv.remove("--class-equiv")
    if "--sepsis-broad-ok" in sys.argv: SEPSIS_BROAD_OK = True; sys.argv.remove("--sepsis-broad-ok")
    res, agg = run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"해외 지침 규칙 판정 (M03 CAP 2019 · M07 cUTI 2025) · 옵션: icu_severe={ICU_IMPLIES_SEVERE} class_equiv={kr.CLASS_EQUIV} sepsis_broad_ok={SEPSIS_BROAD_OK}")
    summary(agg); extra_summary(res)
