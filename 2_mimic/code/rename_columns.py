"""이전 버전 패키지의 data/*.csv 컬럼 이름을 새 이름으로 바꾼다 (재추출 없이 플랫폼에 올린 사본을 맞출 때).
실행: python3 rename_columns.py ../data
"""
import csv, sys, os
D = sys.argv[1] if len(sys.argv) > 1 else "../data"
COH = {"t_sus": "t_infection_suspected", "sus_rule": "suspicion_rule", "t_abx": "t_first_antibiotic", "n_agents": "n_initial_antibiotics",
       "blood_cx_before_abx": "blood_culture_before_antibiotic", "has_abx": "has_antibiotic", "sepsis_code": "sepsis_by_code", "septic_shock_code": "septic_shock_by_code"}
VAL = {"10a": "culture_first", "11a": "antibiotic_first"}
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
p = os.path.join(D, "cohort.csv"); rows = list(csv.DictReader(open(p, newline="", encoding="utf-8")))
if rows and "t_sus" in rows[0]:
    out = []
    for r in rows:
        o = {COH.get(k, k): v for k, v in r.items() if k != "t_sus_minus_icu_in_h"}
        o["suspicion_rule"] = VAL.get(o.get("suspicion_rule", ""), o.get("suspicion_rule", ""))
        d = num(r.get("t_sus_minus_icu_in_h")); ts, icu_in, icu_out = num(r.get("t_sus")), num(r.get("t_icu_in")), num(r.get("t_icu_out"))
        o["hours_suspicion_to_icu"] = round(-d, 2) if d is not None else ""
        o["suspicion_before_icu"] = int(d < 0) if d is not None else ""
        o["sofa_window_covers_icu"] = int(icu_in <= ts + 24 and (icu_out is None or icu_out >= ts - 48)) if (ts is not None and icu_in is not None) else ""
        out.append(o)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print("cohort.csv renamed")
p = os.path.join(D, "antibiotics.csv"); rows = list(csv.DictReader(open(p, newline="", encoding="utf-8")))
if rows and "t_first_admin" in rows[0]:
    with open(p, "w", newline="", encoding="utf-8") as f:
        fields = ["t_first_administration" if k == "t_first_admin" else k for k in rows[0].keys()]
        w = csv.writer(f); w.writerow(fields); w.writerows(list(r.values()) for r in rows)
    print("antibiotics.csv renamed")
print("done")
