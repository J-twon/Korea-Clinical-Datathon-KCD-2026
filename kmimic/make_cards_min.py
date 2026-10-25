#!/usr/bin/env python3
"""최소 사례 카드 생성 — cohort.csv + antibiotics.csv (+ cultures.csv) 만으로 cards_all.jsonl 을 만든다 (vital·검사 없음 → null).
K-MIMIC: antibiotics.csv 에 ingredient 가 없으면 atc 컬럼을 atc_to_ingredient.csv 로 붙인다.
실행: python3 make_cards_min.py DATA_DIR OUT.jsonl atc_to_ingredient.csv [--abx-only-suspicion] [--hospitals=003,004] [--cohort=DATA_DIR/cohort_derived.csv]
"""
import csv, json, sys, os
from collections import defaultdict
D, OUT = sys.argv[1], sys.argv[2]; ATC = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "atc_to_ingredient.csv")
def read(n):
    p = os.path.join(D, n)
    return list(csv.DictReader(open(p, newline="", encoding="utf-8-sig"))) if os.path.exists(p) else []
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
atc = {r["atc"]: r for r in csv.DictReader(open(ATC, encoding="utf-8"))} if os.path.exists(ATC) else {}
BY_NAME = {r["ingredient"]: r for r in atc.values()}
NORMALIZE = {"piperacillin and beta-lactamase inhibitor": "piperacillin/tazobactam", "piperacillin/tazobactam": "piperacillin/tazobactam", "tazoperan": "piperacillin/tazobactam",
             "sulfamethoxazole and trimethoprim": "trimethoprim/sulfamethoxazole", "trimethoprim and sulfamethoxazole": "trimethoprim/sulfamethoxazole", "cotrimoxazole": "trimethoprim/sulfamethoxazole",
             "amoxicillin and beta-lactamase inhibitor": "amoxicillin/clavulanate", "ampicillin and beta-lactamase inhibitor": "ampicillin/sulbactam", "sultamicillin": "ampicillin/sulbactam",
             "imipenem and cilastatin": "imipenem", "cefoperazone and beta-lactamase inhibitor": "cefoperazone/sulbactam", "ceftazidime and beta-lactamase inhibitor": "ceftazidime/avibactam",
             "ceftolozane and beta-lactamase inhibitor": "ceftolozane/tazobactam", "benzylpenicillin": "penicillin", "phenoxymethylpenicillin": "penicillin", "cefalexin": "cephalexin",
             "cefalotin": "cefazolin", "cefradine": "cephalexin", "polymyxin b": "colistin", "colistimethate": "colistin"}
def norm_name(x):
    x = (x or "").strip().lower()
    if x in NORMALIZE: return NORMALIZE[x]
    if x in BY_NAME: return x
    for k, v in NORMALIZE.items():
        if k in x: return v
    for k in BY_NAME:
        if k in x: return k
    return x
FLAGS = set(a for a in sys.argv[4:] if a.startswith("--"))
ABX_ONLY = "--abx-only-suspicion" in FLAGS
HOSPITALS = next((a.split("=", 1)[1].split(",") for a in FLAGS if a.startswith("--hospitals=")), None)   # 예: --hospitals=003,004
COHORT_FILE = next((a.split("=", 1)[1] for a in FLAGS if a.startswith("--cohort=")), None)       # 예: --cohort=cohort_derived.csv (derive 결과를 쓸 때)
cohort = list(csv.DictReader(open(COHORT_FILE, newline="", encoding="utf-8-sig"))) if COHORT_FILE else read("cohort.csv"); abx = read("antibiotics.csv"); cult = read("cultures.csv")
abx_all = defaultdict(list); unmapped = defaultdict(int)
abx = [r for r in abx if r.get("hadm_is_cohort", "1") not in ("0", "0.0") and r.get("is_vasopressor", "0") not in ("1", "1.0")]   # 새 SQL: 이전 입원 행 · 승압제 행 제외(플래그는 derive 가 cohort 에 넣음)
for r in abx:
    code = (r.get("atc") or r.get("gsn") or "")[:7]
    m = atc.get(code)
    ing = norm_name(r.get("ingredient") or r.get("ingredient_name") or r.get("atc_name") or (m["ingredient"] if m else ""))
    if not ing:                                                   # ATC 가 없거나 표에 없음 → 약품명(상품명 괄호 안 성분 등)에서 찾되, 아는 성분일 때만
        cand = norm_name(r.get("drug_raw") or r.get("drug") or ""); ing = cand if cand in BY_NAME else ""
    if not ing: unmapped[code or (r.get("drug_raw") or r.get("drug") or "")[:40]] += 1; continue
    ref = BY_NAME.get(ing) or m
    r["ingredient"] = ing; r["abx_class"] = r.get("abx_class") or (ref["abx_class"] if ref else ""); r["aware"] = r.get("aware") or (ref["aware"] if ref else "")
    abx_all[r["hashed_id"]].append(r)
abx_by = defaultdict(list)
t_abx_of = {c["hashed_id"]: num(c.get("t_first_antibiotic")) for c in cohort}
for h, rows in abx_all.items():
    ta = t_abx_of.get(h)
    if ta is not None and any(num(r.get("t_start")) is not None for r in rows):
        abx_by[h] = [r for r in rows if num(r.get("t_start")) is not None and ta <= num(r["t_start"]) <= ta + 24]   # 첫 항생제 +24h 안 시작
    else:
        abx_by[h] = [r for r in rows if r.get("in_initial_regimen") == "1"]
# --abx-only-suspicion: 짝이 없어 의심 시각이 비는 환자는 첫 전신 항생제 시각을 기준으로 (민감도 코호트)
derived = {}
if ABX_ONLY:
    for c in cohort:
        if c.get("t_infection_suspected") or not abx_all.get(c["hashed_id"]): continue
        ts = [num(r.get("t_start")) for r in abx_all[c["hashed_id"]] if num(r.get("t_start")) is not None]
        if not ts: continue
        ta = min(ts); c["t_infection_suspected"] = ta; c["t_first_antibiotic"] = ta; c["suspicion_rule"] = "antibiotic_only"
        c["community_acquired"] = "1" if ta <= 48 else "0"
        abx_by[c["hashed_id"]] = [r for r in abx_all[c["hashed_id"]] if num(r.get("t_start")) is not None and ta <= num(r["t_start"]) <= ta + 24]
        derived[c["hashed_id"]] = True
cult_by = defaultdict(set)
for r in cult:
    if num(r.get("t_collect")) is not None and num(r["t_collect"]) >= -48: cult_by[r["hashed_id"]].add((num(r["t_collect"]), r.get("spec_type", "")))   # −48h 이전 행은 과거력용
def rel(t, ta): return f"T{(num(t) - ta):+.1f}h" if num(t) is not None else None
n = 0
with open(OUT, "w", encoding="utf-8") as f:
    for c in cohort:
        c["group"] = c.get("group") or c.get("grp") or c.get("cohort_group") or ""
        if HOSPITALS and str(c.get("hospital", "")).zfill(3) not in HOSPITALS: continue
        if str(c.get("community_acquired")) not in ("1", "1.0", "true", "True") or not c.get("t_first_antibiotic"): continue
        h = c["hashed_id"]; ta = num(c["t_first_antibiotic"])
        card = {"case_id": h, "dataset": "K-MIMIC" if c.get("hospital", "") != "BIDMC" else "MIMIC-IV", "hospital": c.get("hospital"), "admission_era": c.get("anchor_year_group", ""),
                "cohort_group": c["group"], "suspicion_rule": c.get("suspicion_rule", ""), "time_reference": "T+0 = first antibiotic order; relative times; no vitals/labs in this minimal card",
                "hospital_arrival": rel(0, ta), "ed_visit": c.get("ed_visit") == "1", "icu_admission": rel(c.get("t_icu_in"), ta), "icu_type": c.get("first_icu_type"),
                "age": int(float(c["age"])) if c.get("age") else None, "sex": c.get("sex"), "weight_kg": num(c.get("weight_kg")),
                "vitals_before_t0": {k: None for k in ("heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temp_c", "gcs_eye", "gcs_verbal", "gcs_motor", "fio2")},
                "labs_before_t0": {k: None for k in ("wbc", "platelets", "creatinine", "bun", "bilirubin_total", "lactate", "crp", "pao2", "ph")},
                "respiratory_support": {"invasive_ventilation": None if c.get("mech_vent", "") == "" else (c.get("mech_vent") == "1" and num(c.get("t_vent_start")) is not None and num(c["t_vent_start"]) <= ta), "started": None},
                "vasopressor": {"any": None if c.get("vasopressor", "") == "" else (c.get("vasopressor") == "1" and num(c.get("t_vaso_start")) is not None and num(c["t_vaso_start"]) <= ta), "started": None},
                "cultures_before_t0": [{"specimen": sp, "collected": f"T{t - ta:+.1f}h"} for t, sp in sorted(cult_by.get(h, set())) if t <= ta],
                "history": {"admission_within_90d": c.get("prior_admission_90d") == "1", "iv_antibiotics_within_90d": c.get("prior_iv_abx_90d") == "1",
                            "mrsa_isolated_within_1y": c.get("prior_mrsa_1y") == "1", "pseudomonas_isolated_within_1y": c.get("prior_pseudomonas_1y") == "1"},
                "comorbidities": [k for k in ("dm", "ckd", "copd", "bronchiectasis", "hf", "liver", "cancer", "immuno", "pregnancy", "uro_obstruction", "alcohol") if c.get(k) == "1"],
                "empirical_regimen": sorted(({"ingredient": r["ingredient"], "class": r.get("abx_class", ""), "aware": r.get("aware", ""), "route": r.get("route", ""),
                                             "dose": f"{r.get('dose','')} {r.get('dose_unit','')}".strip(), "doses_per_24h": r.get("doses_per_24h", ""),
                                             "ordered": rel(r.get("t_start"), ta), "first_administered": rel(r.get("t_first_administration"), ta)} for r in abx_by.get(h, [])),
                                            key=lambda e: (e["ordered"] or "", e["ingredient"])),
                "not_included": ["discharge diagnoses", "in-hospital death", "culture results after T+0", "sepsis label", "vitals/labs (minimal card)"]}
        f.write(json.dumps(card, ensure_ascii=False) + "\n"); n += 1
print("cards:", n, "| 항생제 단독 기준으로 살린 환자:", len(derived), "| 미매핑:", dict(sorted(unmapped.items(), key=lambda x: -x[1])[:15]))
