#!/usr/bin/env python3
"""MIMIC-IV v3.1 → 폐렴/요로감염 초기 항생제 코호트 CSV 추출 (표준 라이브러리만 사용)

실행:  python3 extract_mimic_cohort.py --mimic /path/to/mimiciv/3.1 --out ../data
       --skip-events 를 주면 대용량 이벤트(labevents/chartevents/inputevents/outputevents/procedureevents) 스캔을 생략한다.

시간 기준: t0 = 병원 도착 시각 = min(응급실 등록 edregtime, 입원 admittime). 모든 시간 컬럼은 t0 기준 상대 시간(시간 단위).
출력 (data/):
  cohort.csv        입원 1건 = 1행 (코드 선정 + 겹침 제외 후 전원; 단계 플래그 포함)
  antibiotics.csv   전신 항생제 처방 1건 = 1행
  cultures.csv      미생물 검사 1행 = 검체 × 균 × 항생제
  vitals_labs.csv   활력징후 · 검사 1측정 = 1행 (anchor = 감염 의심 시각, 없으면 t0; 검사 −48h~+72h, 활력징후 −48h~+24h)
  vasopressors.csv, ventilation.csv, id_map.csv, drug_raw_counts.csv, item_map.csv, funnel.json
"""
import argparse, csv, gzip, hashlib, json, os, re, subprocess, time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

ap = argparse.ArgumentParser()
ap.add_argument("--mimic", default="<로컬 경로>")
ap.add_argument("--out", default="../data")
ap.add_argument("--skip-events", action="store_true")
ap.add_argument("--salt", default="kcd2026")
args = ap.parse_args()
M, OUT = args.mimic, args.out
os.makedirs(OUT, exist_ok=True)
T0 = time.time()
def log(*a): print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
H = timedelta(hours=1)

def rows(name, sub="hosp"):
    with gzip.open(f"{M}/{sub}/{name}.csv.gz", "rt", newline="") as f:
        yield from csv.DictReader(f)
def pdt(s):
    if not s: return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    return None
def hid(hadm): return hashlib.sha256(f"{args.salt}:{hadm}".encode()).hexdigest()[:12]
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
def wcsv(name, fields, data):
    with open(f"{OUT}/{name}", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(data)
    log("wrote", name, len(data), "rows")

# ---------------- 항생제 판정 (성분 · 계열 · AWaRe) ----------------
ABX_PATTERNS = [
 ("vancomycin", r"vancomycin"), ("cefepime", r"cefepime"), ("piperacillin/tazobactam", r"piperacillin|zosyn"),
 ("ciprofloxacin", r"ciprofloxacin"), ("ceftriaxone", r"ceftriaxone"), ("metronidazole", r"metronidazole|flagyl"),
 ("cefazolin", r"cefazolin"), ("levofloxacin", r"levofloxacin"), ("azithromycin", r"azithromycin"),
 ("meropenem", r"meropenem"), ("trimethoprim/sulfamethoxazole", r"sulfameth|trimethoprim|bactrim"),
 ("ampicillin/sulbactam", r"ampicillin-sulbactam|unasyn"), ("amoxicillin/clavulanate", r"clavulan|augmentin"),
 ("clindamycin", r"clindamycin"), ("ceftazidime/avibactam", r"avibactam"), ("ceftazidime", r"ceftazidime"), ("linezolid", r"linezolid"),
 ("daptomycin", r"daptomycin"), ("cefpodoxime", r"cefpodoxime"), ("ampicillin", r"ampicillin"),
 ("nafcillin", r"nafcillin"), ("amoxicillin", r"amoxicillin"), ("erythromycin", r"erythromycin"),
 ("tobramycin", r"tobramycin"), ("ertapenem", r"ertapenem"), ("penicillin", r"penicillin"),
 ("clarithromycin", r"clarithromycin"), ("gentamicin", r"gentamicin"), ("doxycycline", r"doxycycline"),
 ("minocycline", r"minocycline"), ("tigecycline", r"tigecycline"), ("aztreonam", r"aztreonam"),
 ("imipenem", r"imipenem|primaxin"), ("oxacillin", r"oxacillin"), ("dicloxacillin", r"dicloxacillin"),
 ("cefuroxime", r"cefuroxime"), ("cefoxitin", r"cefoxitin"), ("cefotaxime", r"cefotaxime"), ("cefadroxil", r"cefadroxil"),
 ("cephalexin", r"cephalexin|keflex"), ("ceftaroline", r"ceftaroline"), ("ceftolozane/tazobactam", r"ceftolozane"),
 ("amikacin", r"amikacin"), ("streptomycin", r"streptomycin"), ("moxifloxacin", r"moxifloxacin"),
 ("nitrofurantoin", r"nitrofurantoin|macrobid|macrodantin"), ("fosfomycin", r"fosfomycin"), ("rifampin", r"rifampin|rifampicin"),
 ("colistin", r"colistin|polymyxin b"), ("chloramphenicol", r"chloramphenicol"), ("tetracycline", r"tetracycline"),
 ("fidaxomicin", r"fidaxomicin"), ("quinupristin/dalfopristin", r"synercid|quinupristin"),
]
ABX_RE = [(n, re.compile(p)) for n, p in ABX_PATTERNS]
BAD_ROUTE = {"OU","OS","OD","AU","AS","AD","TP","BOTH EYES","RIGHT EYE","LEFT EYE","BOTH EARS","RIGHT EAR","LEFT EAR","LOCK","IRR","IR","IH","NEB","NU","IN"}
BAD_DRUG = re.compile(r"cream|ointment|oint|ophth|otic|gel\b|desensit|lotion|drops|irrig|topical|bacitracin|polymyxin-|neomycin|nebu|inhal", re.I)
def classify(drug, route):
    d = drug.lower(); r = (route or "").upper()
    if r in BAD_ROUTE or "eye" in r.lower() or "ear" in r.lower() or BAD_DRUG.search(d): return None
    for n, rx in ABX_RE:
        if rx.search(d):
            if n == "vancomycin" and r in ("PO", "NG", "PR", "ORAL"): return None   # 경구 vancomycin = C. difficile
            return n
    return None
CLASS = {"anti_MRSA": ["vancomycin","linezolid","daptomycin","ceftaroline"],
 "antipseudomonal": ["piperacillin/tazobactam","cefepime","ceftazidime","meropenem","imipenem","aztreonam","ciprofloxacin","levofloxacin","amikacin","tobramycin","ceftazidime/avibactam","ceftolozane/tazobactam"],
 "carbapenem": ["meropenem","imipenem","ertapenem"], "3rd_ceph": ["ceftriaxone","cefotaxime","ceftazidime","cefpodoxime"],
 "1st2nd_ceph": ["cefazolin","cephalexin","cefadroxil","cefuroxime","cefoxitin"],
 "beta_lactam_BLI": ["piperacillin/tazobactam","ampicillin/sulbactam","amoxicillin/clavulanate"],
 "penicillin": ["ampicillin","amoxicillin","penicillin","nafcillin","oxacillin","dicloxacillin"],
 "macrolide": ["azithromycin","clarithromycin","erythromycin"], "fluoroquinolone": ["ciprofloxacin","levofloxacin","moxifloxacin"],
 "aminoglycoside": ["gentamicin","amikacin","tobramycin","streptomycin"], "anaerobe": ["metronidazole","clindamycin"],
 "tetracycline": ["doxycycline","minocycline","tetracycline","tigecycline"], "sulfonamide": ["trimethoprim/sulfamethoxazole"],
 "other": ["nitrofurantoin","fosfomycin","rifampin","colistin","chloramphenicol","fidaxomicin","quinupristin/dalfopristin"]}
ING_CLASS = defaultdict(list)
for c, lst in CLASS.items():
    for i in lst: ING_CLASS[i].append(c)
AWARE = {"access": ["amoxicillin","amoxicillin/clavulanate","ampicillin","ampicillin/sulbactam","penicillin","nafcillin","oxacillin","dicloxacillin",
                    "cefazolin","cephalexin","cefadroxil","clindamycin","doxycycline","tetracycline","gentamicin","amikacin","streptomycin",
                    "metronidazole","nitrofurantoin","trimethoprim/sulfamethoxazole","chloramphenicol"],
         "watch": ["azithromycin","clarithromycin","erythromycin","cefuroxime","cefoxitin","ceftriaxone","cefotaxime","cefpodoxime","ceftazidime","cefepime",
                   "ciprofloxacin","levofloxacin","moxifloxacin","ertapenem","meropenem","imipenem","piperacillin/tazobactam","vancomycin","tobramycin",
                   "rifampin","minocycline","fidaxomicin","fosfomycin"],
         "reserve": ["linezolid","daptomycin","tigecycline","colistin","aztreonam","ceftaroline","ceftazidime/avibactam","ceftolozane/tazobactam","quinupristin/dalfopristin"]}
ING_AWARE = {i: k for k, lst in AWARE.items() for i in lst}   # WHO AWaRe 2023 목록 기준 — 2025 목록으로 검수할 것

# ---------------- 진단코드 ----------------
def P(v10, v9): return (tuple(v10), tuple(v9))
CODES = {
 "pna":        P(["J13","J14","J15","J16","J180","J181","J188","J189"], ["481","482","483","485","486"]),
 "pna_viral":  P(["J12","J100","J110"], ["480","4870"]),
 "pna_asp":    P(["J690"], ["5070"]),
 "vap":        P(["J95851"], ["99731"]),
 "uti":        P(["N10","N12","N390"], ["5901","59080","5909","5990"]),
 "cystitis":   P(["N300","N309"], ["5950","5959"]),
 "cauti":      P(["T8351"], ["99664"]),
 "sepsis":     P(["A40","A41","R6520","R6521"], ["038","99591","99592","78552"]),
 "septic_shock": P(["R6521"], ["78552"]),
 "dm":         P(["E10","E11","E13","E14"], ["250"]),
 "ckd":        P(["N18"], ["585"]),
 "copd":       P(["J44"], ["491","492","496"]),
 "bronchiectasis": P(["J47"], ["494"]),
 "hf":         P(["I50"], ["428"]),
 "liver":      P(["K70","K71","K72","K73","K74","K75","K76","K77"], ["571","572","573"]),
 "cancer":     P(["C"], ["14","15","16","17","18","19","20"]),
 "immuno":     P(["D80","D81","D82","D83","D84","D89","B20","B21","B22","B23","B24","Z94"], ["279","042","V42"]),
 "pregnancy":  P(["O","Z33","Z34"], ["V22","V23","64","65","66","67"]),
 "uro_obstruction": P(["N13","N20","N21","N40"], ["592","594","600"]),
 "alcohol":    P(["F10"], ["303","3050"]),
}
def flags(code, ver):
    for k, (p10, p9) in CODES.items():
        for p in (p10 if ver == "10" else p9):
            if code.startswith(p): yield k; break

# ---------------- 0. 환자 · 입원 · ICU ----------------
pat = {r["subject_id"]: r for r in rows("patients")}
adm = {r["hadm_id"]: r for r in rows("admissions")}
for a in adm.values():
    a["admit"], a["disch"], a["edreg"], a["death"] = pdt(a["admittime"]), pdt(a["dischtime"]), pdt(a["edregtime"]), pdt(a["deathtime"])
    a["t0"] = min([t for t in (a["admit"], a["edreg"]) if t])
log("patients", len(pat), "admissions", len(adm))
first = {}; n_stays = 0
for r in rows("icustays", "icu"):
    n_stays += 1; s = r["subject_id"]; t = pdt(r["intime"])
    if s not in first or t < first[s]["in"]:
        first[s] = {"in": t, "out": pdt(r["outtime"]), "stay": r["stay_id"], "hadm": r["hadm_id"], "unit": r["first_careunit"], "los": r["los"]}
cohort = {}
for s, st in first.items():
    a = adm[st["hadm"]]; p = pat[s]; t0 = a["t0"]
    age = int(p["anchor_age"]) + (a["admit"].year - int(p["anchor_year"]))
    rel = lambda t: round((t - t0).total_seconds() / 3600, 2) if t else ""
    cohort[st["hadm"]] = {"hashed_id": hid(st["hadm"]), "subject_id": s, "hadm_id": st["hadm"], "stay_id": st["stay"], "hospital": "BIDMC",
        "age": age, "sex": p["gender"], "anchor_year_group": p["anchor_year_group"], "ed_visit": int(a["edreg"] is not None),
        "admission_type": a["admission_type"], "admission_location": a["admission_location"], "first_icu_type": st["unit"],
        "t_ed": rel(a["edreg"]), "t_admit": rel(a["admit"]), "t_icu_in": rel(st["in"]), "t_icu_out": rel(st["out"]), "t_disch": rel(a["disch"]),
        "icu_los_d": st["los"], "hosp_los_d": round((a["disch"] - a["admit"]).total_seconds() / 86400, 2),
        "death_inhosp": int(a["hospital_expire_flag"] == "1"), "t_death": rel(a["death"]),
        "t0_abs": t0.strftime("%Y-%m-%d %H:%M:%S"), "_t0": t0, "_disch": a["disch"], "_icu_in": st["in"], "_icu_out": st["out"]}
funnel = {"patients_total": len(pat), "icu_stays_total": n_stays, "first_icu_stay_per_patient": len(cohort)}
adult = {h for h, c in cohort.items() if c["age"] >= 18}; funnel["adult_18plus"] = len(adult)
log("first ICU stays", len(cohort), "adults", len(adult))

# ---------------- 1. 진단 ----------------
dx = defaultdict(set); ver_of = {}
for r in rows("diagnoses_icd"):
    h = r["hadm_id"]
    if h not in adult: continue
    ver_of[h] = r["icd_version"]
    for k in flags(r["icd_code"].strip(), r["icd_version"]): dx[h].add(k)
has = lambda h, k: k in dx.get(h, ())
pna_all = {h for h in adult if has(h, "pna")}; uti_all = {h for h in adult if has(h, "uti")}
pna = {h for h in pna_all if not has(h, "pna_asp") and not has(h, "vap")}
uti = {h for h in uti_all if not has(h, "cauti")}
both = pna & uti; pna -= both; uti -= both
funnel.update({"pna_code": len(pna_all), "pna_aspiration_excluded": len({h for h in pna_all if has(h, "pna_asp")}),
               "pna_vap_excluded": len({h for h in pna_all if has(h, "vap")}), "pna_after_exclusion": len(pna | both),
               "uti_code": len(uti_all), "uti_catheter_excluded": len({h for h in uti_all if has(h, "cauti")}), "uti_after_exclusion": len(uti | both),
               "cystitis_only_not_included": len({h for h in adult if has(h, "cystitis") and not has(h, "uti")}),
               "overlap_excluded": len(both), "pna_selected": len(pna), "uti_selected": len(uti)})
sel = {h: cohort[h] for h in pna | uti}
for h, c in sel.items():
    c["group"] = "pneumonia" if h in pna else "uti"; c["icd_version"] = ver_of.get(h, "")
    c["sepsis_by_code"], c["septic_shock_by_code"] = int(has(h, "sepsis")), int(has(h, "septic_shock"))
    for k in ("dm", "ckd", "copd", "bronchiectasis", "hf", "liver", "cancer", "immuno", "pregnancy", "uro_obstruction", "alcohol"):
        c[k] = int(has(h, k))
    c["viral_cocode"] = int(has(h, "pna_viral")); c["cystitis_code"] = int(has(h, "cystitis"))
log("selected: pna", len(pna), "uti", len(uti), "overlap excluded", len(both))

# 이전 입원 (90일) — 같은 subject의 다른 입원 중 퇴원이 t0 이전 90일 안
subj_h = defaultdict(list)
for h, c in sel.items(): subj_h[c["subject_id"]].append(h)
prior_h = {}   # prior hadm -> index hadm
for a in adm.values():
    s = a["subject_id"]
    if s not in subj_h: continue
    for h in subj_h[s]:
        c = sel[h]
        if a["hadm_id"] != h and a["disch"] and c["_t0"] - timedelta(days=90) <= a["disch"] < c["_t0"]:
            c["prior_admission_90d"] = 1; prior_h[a["hadm_id"]] = h
for c in sel.values(): c.setdefault("prior_admission_90d", 0); c["prior_iv_abx_90d"] = 0

# ---------------- 2. 처방 · 투여 ----------------
abx_rows = []; abx_by = defaultdict(list); drug_counts = Counter()
for r in rows("prescriptions"):
    h = r["hadm_id"]
    if h in prior_h:
        if (r["route"] or "").upper() in ("IV", "IV DRIP", "IV BOLUS", "IVPCA") and classify(r["drug"], r["route"]): sel[prior_h[h]]["prior_iv_abx_90d"] = 1
        continue
    if h not in sel: continue
    n = classify(r["drug"], r["route"])
    if not n: continue
    c = sel[h]; st, sp = pdt(r["starttime"]), pdt(r["stoptime"])
    if not st: continue
    rel = lambda t: round((t - c["_t0"]).total_seconds() / 3600, 2) if t else ""
    row = {"hashed_id": c["hashed_id"], "drug_raw": r["drug"], "ingredient": n, "abx_class": "|".join(ING_CLASS.get(n, [])), "aware": ING_AWARE.get(n, ""),
           "route": r["route"], "dose": r["dose_val_rx"], "dose_unit": r["dose_unit_rx"], "doses_per_24h": r["doses_per_24_hrs"],
           "t_start": rel(st), "t_stop": rel(sp), "t_first_administration": "", "in_initial_regimen": 0, "source": "prescriptions", "_st": st, "_h": h}
    abx_rows.append(row); abx_by[h].append(row); drug_counts[(r["drug"], n)] += 1
log("prescriptions scanned; cohort rows", len(abx_rows))
# emar: 성분별 첫 실제 투여 시각 (2016년 이후 입원에만 있음)
first_admin = {}
ADMIN = {"Administered", "Started", "Restarted", "Administered in Other Location", "Delayed Administered", "Delayed Started", "Partial Administered"}
for r in rows("emar"):
    h = r["hadm_id"]
    if h not in sel or r["event_txt"] not in ADMIN: continue
    n = classify(r["medication"] or "", "")
    if not n: continue
    t = pdt(r["charttime"])
    if t and ((h, n) not in first_admin or t < first_admin[(h, n)]): first_admin[(h, n)] = t
for row in abx_rows:
    t = first_admin.get((row["_h"], row["ingredient"]))
    if t: row["t_first_administration"] = round((t - sel[row["_h"]]["_t0"]).total_seconds() / 3600, 2)
log("emar scanned; (hadm, ingredient) with admin time", len(first_admin))

# ---------------- 3. 미생물 ----------------
cult_rows = []; cult_by = defaultdict(list)
for r in rows("microbiologyevents"):
    s = r["subject_id"]
    if s not in subj_h: continue
    t = pdt(r["charttime"]) or pdt(r["chartdate"])
    if not t: continue
    is_cult = int("CULTURE" in (r["test_name"] or "").upper())
    for h in subj_h[s]:
        c = sel[h]
        if c["_t0"] - 365 * 24 * H <= t < c["_t0"]:      # 과거 분리균 (1년)
            org = (r["org_name"] or "").upper()
            if "PSEUDOMONAS AERUGINOSA" in org: c["prior_pseudomonas_1y"] = 1
            if "STAPH AUREUS" in org and ((r["ab_name"] or "").upper() == "OXACILLIN" and r["interpretation"] == "R" or "METHICILLIN RESISTANT" in org): c["prior_mrsa_1y"] = 1
        if c["_t0"] - 48 * H <= t <= c["_disch"]:
            rel = lambda x: round((x - c["_t0"]).total_seconds() / 3600, 2) if x else ""
            row = {"hashed_id": c["hashed_id"], "spec_type": r["spec_type_desc"], "test_name": r["test_name"], "is_culture": is_cult,
                   "t_collect": rel(t), "t_result": rel(pdt(r["storetime"]) or pdt(r["storedate"])), "organism": r["org_name"],
                   "antibiotic": r["ab_name"], "interpretation": r["interpretation"], "_t": t}
            cult_rows.append(row); cult_by[h].append(row)
for c in sel.values(): c.setdefault("prior_pseudomonas_1y", 0); c.setdefault("prior_mrsa_1y", 0)
log("microbiology scanned; cohort rows", len(cult_rows))

# ---------------- 4. 감염 의심 시각 · 초기 요법 ----------------
for h, c in sel.items():
    A = sorted({r["_st"] for r in abx_by.get(h, [])}); C = sorted({r["_t"] for r in cult_by.get(h, []) if r["is_culture"]})
    c["has_antibiotic"] = int(bool(A)); c["has_culture"] = int(bool(C))
    best = None
    for a in A:
        for cc in C:
            if cc <= a <= cc + 72 * H: cand = (cc, "culture_first")
            elif a < cc <= a + 24 * H: cand = (a, "antibiotic_first")
            else: continue
            if best is None or cand[0] < best[0]: best = cand
    c.update({"t_infection_suspected": "", "suspicion_rule": "", "community_acquired": 0, "t_first_antibiotic": "", "initial_regimen": "", "n_initial_antibiotics": "", "blood_culture_before_antibiotic": "",
              "hours_suspicion_to_icu": "", "suspicion_before_icu": "", "sofa_window_covers_icu": ""})
    if not best: continue
    ts = best[0]; rel = lambda t: round((t - c["_t0"]).total_seconds() / 3600, 2)
    c["t_infection_suspected"], c["suspicion_rule"] = rel(ts), best[1]
    c["community_acquired"] = int(ts <= c["_t0"] + 48 * H)
    c["hours_suspicion_to_icu"] = round((c["_icu_in"] - ts).total_seconds() / 3600, 2)      # 양수 = ICU 입실이 의심 시각보다 나중
    c["suspicion_before_icu"] = int(ts < c["_icu_in"])
    c["sofa_window_covers_icu"] = int(c["_icu_in"] <= ts + 24 * H and (c["_icu_out"] is None or c["_icu_out"] >= ts - 48 * H))   # SOFA 창(−48h~+24h)이 ICU 재실과 겹침
    later = [a for a in A if a >= ts]
    if later:
        ta = min(later); c["t_first_antibiotic"] = rel(ta)
        reg = set()
        for r in abx_by[h]:
            if ta <= r["_st"] <= ta + 24 * H: r["in_initial_regimen"] = 1; reg.add(r["ingredient"])
        c["initial_regimen"] = " + ".join(sorted(reg)); c["n_initial_antibiotics"] = len(reg)
        c["blood_culture_before_antibiotic"] = int(any(r["_t"] <= ta and "BLOOD" in (r["spec_type"] or "").upper() for r in cult_by.get(h, []) if r["is_culture"]))
for g in ("pneumonia", "uti"):
    S = [c for c in sel.values() if c["group"] == g]
    funnel[f"{g}_with_antibiotic"] = sum(c["has_antibiotic"] for c in S); funnel[f"{g}_with_culture"] = sum(c["has_culture"] for c in S)
    funnel[f"{g}_suspected"] = sum(1 for c in S if c["t_infection_suspected"] != ""); funnel[f"{g}_suspected_culture_first"] = sum(c["suspicion_rule"] == "culture_first" for c in S)
    funnel[f"{g}_suspected_antibiotic_first"] = sum(c["suspicion_rule"] == "antibiotic_first" for c in S); funnel[f"{g}_community_acquired"] = sum(c["community_acquired"] for c in S)
    funnel[f"{g}_ca_sepsis_by_code"] = sum(1 for c in S if c["community_acquired"] and c["sepsis_by_code"])
log("suspicion computed")

COHORT_FIELDS = ["hashed_id","hospital","group","age","sex","anchor_year_group","icd_version","ed_visit","admission_type","admission_location","first_icu_type",
 "t_ed","t_admit","t_icu_in","t_icu_out","t_disch","icu_los_d","hosp_los_d","death_inhosp","t_death",
 "has_antibiotic","has_culture","t_infection_suspected","suspicion_rule","community_acquired","t_first_antibiotic","initial_regimen","n_initial_antibiotics","blood_culture_before_antibiotic","hours_suspicion_to_icu","suspicion_before_icu","sofa_window_covers_icu",
 "sepsis_by_code","septic_shock_by_code","viral_cocode","cystitis_code","dm","ckd","copd","bronchiectasis","hf","liver","cancer","immuno","pregnancy","uro_obstruction","alcohol",
 "prior_admission_90d","prior_iv_abx_90d","prior_mrsa_1y","prior_pseudomonas_1y","mech_vent","t_vent_start","vasopressor","t_vaso_start","weight_kg"]
for c in sel.values():
    for k in ("mech_vent", "t_vent_start", "vasopressor", "t_vaso_start", "weight_kg"): c.setdefault(k, "")
cohort_list = sorted(sel.values(), key=lambda c: (c["group"], c["hashed_id"]))
wcsv("cohort.csv", COHORT_FIELDS, cohort_list)
wcsv("id_map.csv", ["hashed_id", "subject_id", "hadm_id", "stay_id", "t0_abs"], cohort_list)
wcsv("antibiotics.csv", ["hashed_id","drug_raw","ingredient","abx_class","aware","route","dose","dose_unit","doses_per_24h","t_start","t_stop","t_first_administration","in_initial_regimen","source"], abx_rows)
wcsv("cultures.csv", ["hashed_id","spec_type","test_name","is_culture","t_collect","t_result","organism","antibiotic","interpretation"], cult_rows)
wcsv("drug_raw_counts.csv", ["drug_raw","ingredient","n"], [{"drug_raw": d, "ingredient": n, "n": k} for (d, n), k in drug_counts.most_common()])
json.dump(funnel, open(f"{OUT}/funnel.json", "w"), indent=1)
log("funnel", json.dumps(funnel))
if args.skip_events: raise SystemExit(0)

# ---------------- 5. 이벤트 (대용량) ----------------
CHART = {220045:"heart_rate",220179:"sbp_nibp",220180:"dbp_nibp",220181:"map_nibp",220050:"sbp_abp",220051:"dbp_abp",220052:"map_abp",225309:"sbp_abp",225310:"dbp_abp",225312:"map_abp",
         220210:"resp_rate",220277:"spo2",223761:"temp_f",223762:"temp_c",223835:"fio2",220739:"gcs_eye",223900:"gcs_verbal",223901:"gcs_motor",226512:"weight_kg",224639:"weight_kg",220339:"peep"}
LAB = {51301:"wbc",51300:"wbc",51265:"platelets",51006:"bun",50912:"creatinine",50885:"bilirubin_total",50813:"lactate",50889:"crp",50821:"pao2",50818:"pco2",50820:"ph",50816:"fio2_lab",
       51222:"hemoglobin",50983:"sodium",50971:"potassium",50931:"glucose",50862:"albumin",51237:"inr",50882:"bicarbonate",51003:"troponin_t",50963:"ntprobnp"}
URINE = {226559,226560,226561,226584,226563,226564,226565,226567,226557,226558,227488,227489}
VASO = {221906:"norepinephrine",221289:"epinephrine",221662:"dopamine",221653:"dobutamine",222315:"vasopressin",221749:"phenylephrine"}
VENT = {225792:"invasive", 225794:"noninvasive"}
HIGHFREQ = {"heart_rate","sbp_nibp","dbp_nibp","map_nibp","sbp_abp","dbp_abp","map_abp","resp_rate","spo2","temp_f","temp_c"}
wcsv("item_map.csv", ["itemid","item","source"], [{"itemid": k, "item": v, "source": "chartevents"} for k, v in CHART.items()] +
     [{"itemid": k, "item": v, "source": "labevents"} for k, v in LAB.items()] + [{"itemid": k, "item": "urine_output_ml", "source": "outputevents"} for k in URINE] +
     [{"itemid": k, "item": v, "source": "inputevents"} for k, v in VASO.items()] + [{"itemid": k, "item": v, "source": "procedureevents"} for k, v in VENT.items()])
fmt = lambda t: t.strftime("%Y-%m-%d %H:%M:%S")
win = {}   # hadm -> (anchor, lab_lo, lab_hi, vit_lo, vit_hi) as strings for fast compare
for h, c in sel.items():
    anc = c["_t0"] + timedelta(hours=c["t_infection_suspected"]) if c["t_infection_suspected"] != "" else c["_t0"]
    win[h] = (anc, fmt(anc - 48 * H), fmt(anc + 72 * H), fmt(anc - 48 * H), fmt(anc + 24 * H))
by_stay = {c["stay_id"]: h for h, c in sel.items()}; by_subj = {}
for h, c in sel.items(): by_subj.setdefault(c["subject_id"], []).append(h)
vl = open(f"{OUT}/vitals_labs.csv", "w", newline="", encoding="utf-8"); vw = csv.writer(vl)
vw.writerow(["hashed_id","item","itemid","valuenum","value","unit","t_chart","t_store","source_table"]); n_vl = 0
def relh(c, s): return round((pdt(s) - c["_t0"]).total_seconds() / 3600, 2) if s else ""

# procedureevents → ventilation
vent_rows = []
for r in rows("procedureevents", "icu"):
    h = by_stay.get(r["stay_id"]); it = int(r["itemid"])
    if h and it in VENT:
        c = sel[h]; vent_rows.append({"hashed_id": c["hashed_id"], "type": VENT[it], "t_start": relh(c, r["starttime"]), "t_end": relh(c, r["endtime"])})
        if VENT[it] == "invasive":
            c["mech_vent"] = 1
            if c["t_vent_start"] == "" or relh(c, r["starttime"]) < c["t_vent_start"]: c["t_vent_start"] = relh(c, r["starttime"])
wcsv("ventilation.csv", ["hashed_id","type","t_start","t_end"], vent_rows)
# inputevents → vasopressors (+ patientweight)
vaso_rows = []
for r in rows("inputevents", "icu"):
    h = by_stay.get(r["stay_id"])
    if not h: continue
    c = sel[h]
    if c["weight_kg"] == "" and num(r["patientweight"]): c["weight_kg"] = num(r["patientweight"])
    it = int(r["itemid"])
    if it in VASO:
        vaso_rows.append({"hashed_id": c["hashed_id"], "drug": VASO[it], "t_start": relh(c, r["starttime"]), "t_end": relh(c, r["endtime"]),
                          "rate": r["rate"], "rateuom": r["rateuom"], "amount": r["amount"], "amountuom": r["amountuom"]})
        c["vasopressor"] = 1
        if c["t_vaso_start"] == "" or relh(c, r["starttime"]) < c["t_vaso_start"]: c["t_vaso_start"] = relh(c, r["starttime"])
wcsv("vasopressors.csv", ["hashed_id","drug","t_start","t_end","rate","rateuom","amount","amountuom"], vaso_rows)
# outputevents → urine output
for r in rows("outputevents", "icu"):
    h = by_stay.get(r["stay_id"])
    if h and int(r["itemid"]) in URINE:
        c = sel[h]; a, lo, hi, _, _ = win[h]
        if lo <= r["charttime"] <= hi:
            vw.writerow([c["hashed_id"], "urine_output_ml", r["itemid"], r["value"], "", r["valueuom"], relh(c, r["charttime"]), relh(c, r["storetime"]), "outputevents"]); n_vl += 1
log("procedure/input/output done; vitals_labs rows", n_vl)

def scan(path, key_idx, key_map, item_map, time_idx, store_idx, vnum_idx, val_idx, uom_idx, source):
    """zcat 파이프로 대용량 csv를 훑어 코호트 · 관심 itemid · 시간창 안의 행만 기록."""
    global n_vl
    proc = subprocess.Popen(["zcat", path], stdout=subprocess.PIPE, bufsize=1 << 20)
    want = {str(k).encode(): v for k, v in item_map.items()}
    header = proc.stdout.readline(); n = 0; kept = 0
    for line in proc.stdout:
        n += 1
        parts = line.split(b",", 7)
        key = parts[key_idx]
        if key not in key_map: continue
        item = want.get(parts[4 if source == "labevents" else 6])
        if not item: continue
        tch = parts[time_idx].decode()
        for h in (key_map[key] if isinstance(key_map[key], list) else [key_map[key]]):
            a, llo, lhi, vlo, vhi = win[h]
            if item == "weight_kg": ok = True
            elif item in HIGHFREQ: ok = vlo <= tch <= vhi
            else: ok = llo <= tch <= lhi
            if not ok: continue
            f = next(csv.reader([line.decode("utf-8", "replace")]))
            c = sel[h]
            vw.writerow([c["hashed_id"], item, f[4 if source == "labevents" else 6], f[vnum_idx], f[val_idx] if item.startswith("gcs") else "", f[uom_idx], relh(c, tch), relh(c, f[store_idx]), source]); kept += 1; n_vl += 1
            if item == "weight_kg" and c["weight_kg"] == "" and num(f[vnum_idx]): c["weight_kg"] = num(f[vnum_idx])
        if n % 50_000_000 == 0: log(source, n, "lines; kept", kept)
    proc.wait(); log(source, "done", n, "lines; kept", kept)
# labevents: labevent_id,subject_id,hadm_id,specimen_id,itemid,order_provider_id,charttime,storetime,value,valuenum,valueuom,...
scan(f"{M}/hosp/labevents.csv.gz", 1, {k.encode(): v for k, v in by_subj.items()}, LAB, 6, 7, 9, 8, 10, "labevents")
# chartevents: subject_id,hadm_id,stay_id,caregiver_id,charttime,storetime,itemid,value,valuenum,valueuom,warning
scan(f"{M}/icu/chartevents.csv.gz", 2, {k.encode(): v for k, v in by_stay.items()}, CHART, 4, 5, 8, 7, 9, "chartevents")
vl.close()
for c in sel.values():
    for k in ("mech_vent", "vasopressor"):
        if c[k] == "": c[k] = 0
wcsv("cohort.csv", COHORT_FIELDS, cohort_list)
log("ALL DONE; vitals_labs rows", n_vl)
