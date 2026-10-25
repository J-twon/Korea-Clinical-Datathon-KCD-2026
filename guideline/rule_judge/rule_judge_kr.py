#!/usr/bin/env python3
"""국내 지침 규칙 판정 — CAP 2026 표 3·표 4(입원 행), 요로감염 2026 표 5(전신 요로감염)
입력: 사례 카드(JSONL). 출력: 환자별 판정(JSONL) + 집계.
판정값: 준수(추천) / 준수(대안) / 비준수(누락) / 비준수(과잉) / 비준수(다른 약제) / 해당 없음 / 판정 불가
"""
import json, sys, re, csv
from collections import Counter, defaultdict

CEPH34 = {"ceftriaxone", "cefotaxime", "ceftazidime", "cefepime", "cefpodoxime", "cefoperazone/sulbactam", "cefixime"}
FQ = {"ciprofloxacin", "levofloxacin", "moxifloxacin"}
CARBA = {"meropenem", "imipenem", "ertapenem"}
AMINOGLY = {"gentamicin", "amikacin", "tobramycin"}
ANTI_MRSA = {"vancomycin", "linezolid", "daptomycin", "ceftaroline"}
ANTIPSEUDO = {"piperacillin/tazobactam", "cefepime", "ceftazidime", "meropenem", "imipenem", "aztreonam", "ciprofloxacin", "levofloxacin"}

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
def mg(dose):
    m = re.match(r"\s*([\d.]+)\s*([a-zA-Z]+)", dose or "")
    if not m: return None
    v = float(m.group(1)); u = m.group(2).lower()
    return v * 1000 if u in ("g", "gm", "gram", "grams") else v if u == "mg" else None

# ---------- 조건 계산 (카드의 T+0 이전 값만) ----------
def cap_severity(c):
    """표 3: 주기준 1개 이상 또는 부기준 3개 이상 → 중증. 반환 (status, detail)  status ∈ severe / nonsevere / unknown"""
    v, l = c["vitals_before_t0"], c["labs_before_t0"]
    major = []
    if c["respiratory_support"]["invasive_ventilation"]: major.append("기계환기")
    if c["vasopressor"]["any"]: major.append("승압제")
    if major: return "severe", "주기준: " + ", ".join(major)
    minor, unknown = [], []
    def chk(name, val, cond):
        if val is None: unknown.append(name)
        elif cond(val): minor.append(name)
    chk("BUN≥20", l.get("bun"), lambda x: x >= 20)
    gcs = [v.get("gcs_eye"), v.get("gcs_verbal"), v.get("gcs_motor")]
    if None in gcs: unknown.append("의식")
    elif gcs[1] == 0: unknown.append("의식(삽관)")
    elif sum(gcs) < 15: minor.append("의식저하")
    chk("체온<36", v.get("temp_c"), lambda x: x < 36)
    chk("저혈압(SBP<90)", v.get("sbp"), lambda x: x < 90)
    unknown.append("다엽침윤(영상 없음)")
    if l.get("pao2") is not None and v.get("fio2") is not None and v["fio2"] > 0:
        ratio = l["pao2"] / (v["fio2"] / 100 if v["fio2"] > 1 else v["fio2"])
        if ratio <= 250: minor.append(f"PaO2/FiO2≤250({ratio:.0f})")
    else: unknown.append("PaO2/FiO2")
    chk("혈소판<10만", l.get("platelets"), lambda x: x < 100)
    chk("호흡수≥30", v.get("resp_rate"), lambda x: x >= 30)
    chk("WBC<4000", l.get("wbc"), lambda x: x < 4)
    if len(minor) >= 3: return "severe", "부기준 " + ", ".join(minor)
    if len(minor) + len(unknown) < 3: return "nonsevere", f"부기준 {len(minor)}개 (모름 {len(unknown)})"
    return "unknown", f"부기준 {len(minor)}개 확인 + 모름 {len(unknown)}개: " + ", ".join(unknown)

def cap_risks(c):
    h = c["history"]
    mrsa = h["mrsa_isolated_within_1y"]
    both = h["admission_within_90d"] and h["iv_antibiotics_within_90d"]
    either = h["admission_within_90d"] or h["iv_antibiotics_within_90d"]
    pa = "yes" if (both or h["pseudomonas_isolated_within_1y"]) else ("unknown" if either else "no")
    return mrsa, pa

def uti_sepsis(c):
    """표 2: 패혈증 = qSOFA≥2 또는 SOFA≥2 (카드로는 qSOFA + 승압제·환기). 반환 yes / no / unknown"""
    v = c["vitals_before_t0"]
    if c["vasopressor"]["any"] or c["respiratory_support"]["invasive_ventilation"]: return "yes", "승압제/기계환기"
    pts, unk = 0, 0
    for name, val, cond in (("RR≥22", v.get("resp_rate"), lambda x: x >= 22), ("SBP≤100", v.get("sbp"), lambda x: x <= 100)):
        if val is None: unk += 1
        elif cond(val): pts += 1
    gcs = [v.get("gcs_eye"), v.get("gcs_verbal"), v.get("gcs_motor")]
    if None in gcs or gcs[1] == 0: unk += 1
    elif sum(gcs) < 15: pts += 1
    if pts >= 2: return "yes", f"qSOFA {pts}"
    if pts + unk < 2: return "no", f"qSOFA {pts}"
    return "unknown", f"qSOFA {pts} + 모름 {unk}"

# ---------- 규칙 행 ----------
def cap_rows(severity, mrsa, pa):
    """후보 행 목록 [(row_id, S(set of frozensets), A, note)]"""
    base = {"nonsevere": [("K02-입원-비중증", [{"ceftriaxone"}], [{"levofloxacin"}])],
            "severe_noMDR": [("K02-입원-중증-내성균없음", [{"ceftriaxone", "azithromycin"}], [{"levofloxacin"}])],
            "severe_PA": [("K02-입원-중증-녹농균", [{"cefepime", "azithromycin"}], [{"piperacillin/tazobactam", "levofloxacin"}])]}
    sev = ["nonsevere", "severe"] if severity == "unknown" else [severity]
    rows = []
    for s in sev:
        if s == "nonsevere": rows += base["nonsevere"]
        else:
            pas = ["no", "yes"] if pa == "unknown" else [pa]
            for p in pas:
                for rid, S, A in (base["severe_PA"] if p == "yes" else base["severe_noMDR"]):
                    if mrsa: rows.append((rid + "+MRSA", [x | {"vancomycin"} for x in S], [x | {"vancomycin"} for x in A]))
                    else: rows.append((rid, S, A))
    return rows

def compare(R, S_list, A_list, explain_extra):
    """성분 집합 비교 → (판정, 이유)"""
    for S in S_list:
        if R == S: return "준수(추천)", "추천 조합과 동일"
    for A in A_list:
        if R == A: return "준수(대안)", "대안 조합과 동일 (알레르기 정보 없음 → 증빙 없이 인정)"
    for S in S_list + A_list:
        if R > S:
            extra = R - S; unexplained = [e for e in extra if not explain_extra(e)]
            if not unexplained: return "준수(추천)" if S in S_list else "준수(대안)", f"추천 조합 + 위험인자로 설명되는 추가 약제 {sorted(extra)}"
            return "비준수(과잉)", f"추천 조합에 설명되지 않는 추가 약제 {sorted(unexplained)}"
    for S in S_list + A_list:
        if R < S: return "비준수(누락)", f"추천 조합 중 {sorted(S - R)} 누락"
    overlap = [S for S in S_list + A_list if R & S]
    if overlap: return "비준수(다른 약제)", f"추천 약제 {sorted(R & overlap[0])} 외에 다른 약제 {sorted(R - overlap[0])}, 누락 {sorted(overlap[0] - R)}"
    return "비준수(다른 약제)", "추천·대안 조합과 겹치는 성분 없음"

ICU_IMPLIES_SEVERE = False
CLASS_EQUIV = False   # --class-equiv: teicoplanin→vancomycin, cefotaxime→ceftriaxone, clarithromycin→azithromycin 로 보고 판정
EQUIV = {"teicoplanin": "vancomycin", "cefotaxime": "ceftriaxone", "clarithromycin": "azithromycin"}
def regimen_set(c):
    R = {e["ingredient"] for e in c["empirical_regimen"]}
    return {EQUIV.get(x, x) for x in R} if CLASS_EQUIV else R
def judge_cap(c):
    R = regimen_set(c)
    if not R: return {"verdict": "해당 없음", "reason": "요법 없음"}
    if R == {"cefazolin"}: return {"verdict": "해당 없음", "reason": "cefazolin 단독 — 수술 예방적 투여 의심"}
    sev, sev_detail = cap_severity(c); mrsa, pa = cap_risks(c)
    if ICU_IMPLIES_SEVERE and sev != "severe": sev, sev_detail = "severe", "가정: ICU 입실 환자 = 중증 (" + sev_detail + ")"
    rows = cap_rows(sev, mrsa, pa)
    def explain(agent):
        if agent in ANTI_MRSA: return mrsa
        if agent in ANTIPSEUDO: return pa == "yes"
        return False
    verdicts = []
    for rid, S, A in rows:
        v, why = compare(R, S, A, explain); verdicts.append((rid, v, why))
    cats = {v for _, v, _ in verdicts}
    if len(cats) == 1: final, why = verdicts[0][1], verdicts[0][2]; row = " / ".join(r for r, _, _ in verdicts)
    else: final, why, row = "판정 불가", "중증도·위험인자 미확정으로 후보 행 결론이 다름: " + "; ".join(f"{r}→{v}" for r, v, _ in verdicts), "후보 여러 개"
    return {"verdict": final, "reason": why, "row": row, "severity": f"{sev} ({sev_detail})", "mrsa_risk": mrsa, "pa_risk": pa, "regimen": sorted(R), "candidates": verdicts}

def judge_uti(c):
    R = regimen_set(c)
    if not R: return {"verdict": "해당 없음", "reason": "요법 없음"}
    if R == {"cefazolin"}: return {"verdict": "해당 없음", "reason": "cefazolin 단독 — 수술 예방적 투여 의심"}
    sep, sep_detail = uti_sepsis(c)
    routes = {e["ingredient"]: e["route"] for e in c["empirical_regimen"]}
    rec_iv = CEPH34 | {"piperacillin/tazobactam"} | FQ
    def verdict_for(sepsis):
        rec = rec_iv | (CARBA if sepsis == "yes" else set()); alt = AMINOGLY
        oral_rec = {"ciprofloxacin", "levofloxacin", "trimethoprim/sulfamethoxazole"}; oral_alt = {"amoxicillin/clavulanate", "cephalexin", "cefpodoxime", "cefadroxil", "cefuroxime"}
        in_rec, in_alt = R & rec, R & alt
        extras = R - rec - alt
        if sepsis == "no" and all(routes.get(a, "").upper() in ("PO", "ORAL", "NG") for a in R) and R <= (oral_rec | oral_alt):
            return ("준수(추천)" if R & oral_rec else "준수(대안)"), "경구 요법 행"
        if in_rec and not extras:
            note = ""
            if sepsis == "yes" and len(R) == 1 and (R <= FQ or R <= {"ceftriaxone", "cefotaxime", "cefpodoxime"}): note = " · 각주5: 기관 감수성 자료 없이 FQ/3세대 단독은 피해야 함 → 조건부"
            return "준수(추천)", f"추천 약제 {sorted(in_rec)}" + note
        if in_alt and not in_rec and not extras: return "준수(대안)", f"대안 약제 {sorted(in_alt)}"
        if (in_rec or in_alt) and extras: return "비준수(과잉)", f"추천 약제 {sorted(in_rec | in_alt)} + 표에 없는 추가 약제 {sorted(extras)}"
        return "비준수(다른 약제)", f"추천·대안에 없는 약제만 사용 {sorted(R)}"
    cands = ["yes", "no"] if sep == "unknown" else [sep]
    vs = [(s, *verdict_for(s)) for s in cands]
    if len({v for _, v, _ in vs}) == 1: final, why = vs[0][1], vs[0][2]
    else: final, why = "판정 불가", "패혈증 여부 미확정으로 후보 행 결론이 다름: " + "; ".join(f"패혈증 {s}→{v}" for s, v, _ in vs)
    return {"verdict": final, "reason": why, "row": "K04-표5-전신-" + ("패혈증" if sep == "yes" else "비패혈증" if sep == "no" else "미확정"), "sepsis_at_t0": f"{sep} ({sep_detail})", "regimen": sorted(R), "candidates": vs}

DOSE = {"ceftriaxone": (2000, 1), "azithromycin": (500, 1), "cefepime": (2000, 3), "levofloxacin": (750, 1), "piperacillin/tazobactam": (4500, (3, 4))}
def dose_check(c):
    out = []; seen = set()
    for e in sorted(c["empirical_regimen"], key=lambda e: e["ordered"] or ""):
        ing = e["ingredient"]
        if ing in seen: continue
        seen.add(ing)
        if ing == "vancomycin":
            w = c.get("weight_kg"); d = mg(e["dose"])
            if not w or d is None: out.append((ing, "판정 불가", "체중 또는 용량 없음")); continue
            per = d / w; out.append((ing, "준수" if 15 <= per <= 20 or (20 < per <= 35) else "비준수", f"{per:.0f} mg/kg (유지 15–20, 초회 20–35)"))
        elif ing in DOSE:
            tgt, freq = DOSE[ing]; d = mg(e["dose"]); f = num(e["doses_per_24h"]); f = f if f else None
            if d is None: out.append((ing, "판정 불가", "용량 없음")); continue
            ok_d = abs(d - tgt) <= tgt * 0.1; ok_f = (f is None) or (f in freq if isinstance(freq, tuple) else f == freq)
            out.append((ing, ("준수" if ok_d and ok_f else "비준수") + ("(횟수 모름)" if f is None else "") + " · 참고: 신기능 조정 미반영",
                        f"{e['dose']} ×{e['doses_per_24h'] or '?'}/일 (지침 {tgt/1000:g} g ×{freq}/일)"))
    return out

def run(path, out_path=None, verbose_ids=()):
    res = []; agg = defaultdict(Counter)
    with open(path, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line); g = c["cohort_group"]
            j = judge_cap(c) if g == "pneumonia" else judge_uti(c)
            j.update({"case_id": c["case_id"], "group": g, "era": c["admission_era"], "dose": dose_check(c) if g == "pneumonia" else []})
            res.append(j); agg[g][j["verdict"]] += 1
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            for j in res: f.write(json.dumps(j, ensure_ascii=False) + "\n")
    return res, agg

def extra_summary(res):
    from collections import Counter, defaultdict
    for g in ("pneumonia", "uti"):
        R = [j for j in res if j["group"] == g]
        print(f"\n[{g}] 시기별 준수율 (판정된 환자 기준)")
        by = defaultdict(Counter)
        for j in R: by[j["era"]][j["verdict"]] += 1
        for era in sorted(by):
            c = by[era]; den = sum(c.values()) - c["해당 없음"] - c["판정 불가"]; adh = c["준수(추천)"] + c["준수(대안)"]
            print(f"   {era}: {100*adh/den:5.1f}%  (판정된 {den:,} · 판정 불가 {c['판정 불가']:,})" if den else f"   {era}: -")
        print(f"[{g}] 판정값별 상위 요법")
        for v in ("준수(추천)", "준수(대안)", "비준수(과잉)", "비준수(다른 약제)", "판정 불가"):
            top = Counter(" + ".join(j.get("regimen", [])) for j in R if j["verdict"] == v).most_common(4)
            if top: print(f"   {v:12} " + " / ".join(f"{r} ({k:,})" for r, k in top))

def summary(agg):
    for g, cnt in agg.items():
        n = sum(cnt.values()); na = cnt["해당 없음"]; und = cnt["판정 불가"]; adh = cnt["준수(추천)"] + cnt["준수(대안)"]; den = n - na - und
        print(f"\n[{g}] n={n:,} · 해당 없음 {na:,} · 판정 불가 {und:,} · 판정된 {den:,}")
        for k in ("준수(추천)", "준수(대안)", "비준수(누락)", "비준수(과잉)", "비준수(다른 약제)"): print(f"   {k:12} {cnt[k]:6,} ({100*cnt[k]/den:.1f}% of 판정된)" if den else "")
        print(f"   준수율 = {adh:,}/{den:,} = {100*adh/den:.1f}%  · 하한선(판정 불가=비준수) = {100*adh/(den+und):.1f}%" if den else "")

if __name__ == "__main__":
    if "--icu-severe" in sys.argv: ICU_IMPLIES_SEVERE = True; sys.argv.remove("--icu-severe")
    if "--class-equiv" in sys.argv: CLASS_EQUIV = True; sys.argv.remove("--class-equiv")
    res, agg = run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    summary(agg); extra_summary(res)
