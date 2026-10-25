#!/usr/bin/env python3
"""노트북(mimic_pna_uti.ipynb)을 만들고, 각 코드 셀을 순서대로 실행해 출력까지 심는다 (jupyter 없이 동작).
실행: python3 build_notebook.py  (notebooks/ 폴더에서 상대경로 ../data, ../results 를 쓴다)
"""
import io, json, os, sys, traceback, contextlib, time

CELLS = []
def md(s): CELLS.append(("markdown", s.strip("\n")))
def code(s): CELLS.append(("code", s.strip("\n")))

md("""
# MIMIC-IV 폐렴 · 요로감염 초기 항생제 코호트 — 데이터 확인과 분석

**목적** — K-MIMIC에서 할 분석을 MIMIC-IV v3.1로 먼저 끝까지 돌려 본다. 같은 컬럼 구조(`data/*.csv`)로 K-MIMIC을 뽑으면 이 노트북을 그대로 다시 쓸 수 있다.

**시간 기준** — `t0 = 병원 도착 = min(응급실 등록, 입원)`. 모든 `t_*` 컬럼은 t0 기준 상대 시간(시간). 절대 날짜는 없다.

**주의** — `data/`의 파일은 MIMIC-IV에서 파생한 **환자 단위 자료**다. PhysioNet 자격이 없는 사람과 공유하거나 외부 서비스에 올리면 안 된다. 공유는 `results/`의 집계표만.

파일: `cohort.csv`(입원 1건 = 1행) · `antibiotics.csv`(처방 1건 = 1행) · `cultures.csv`(검체 × 균 × 항생제) · `vitals_labs.csv`(측정 1건 = 1행) · `vasopressors.csv` · `ventilation.csv` · `id_map.csv`(해시 → 원 ID) · `drug_raw_counts.csv` · `item_map.csv` · `funnel.json`
""")
code("""
import csv, json, os, random, statistics, gzip
from collections import Counter, defaultdict
DATA, RES = "../data", "../results"
MIMIC = "<로컬 경로>"      # 원자료 위치 (1장에서만 사용)

def read(name):
    with open(f"{DATA}/{name}", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
def median(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None
def pct(k, n): return f"{100*k/n:.1f}" if n else "-"

cohort = read("cohort.csv"); abx = read("antibiotics.csv"); cult = read("cultures.csv")
funnel = json.load(open(f"{DATA}/funnel.json"))
by_id = {c["hashed_id"]: c for c in cohort}
print("cohort", len(cohort), "rows ·", "antibiotics", len(abx), "·", "cultures", len(cult))
print("groups:", Counter(c["group"] for c in cohort))
""")
md("""
## 1. 원자료 훑어보기 — MIMIC-IV 테이블의 첫 행

추출 코드가 어떤 컬럼을 쓰는지 눈으로 확인한다. (`labevents` · `chartevents`는 수억 행이라 첫 2행만 읽는다.)
""")
code("""
def peek(sub, name, n=2):
    with gzip.open(f"{MIMIC}/{sub}/{name}.csv.gz", "rt", newline="") as f:
        r = csv.reader(f); head = next(r)
        print(f"\\n[{sub}/{name}] columns({len(head)}):", ", ".join(head))
        for i, row in zip(range(n), r):
            print("   ", dict(list(zip(head, row))[:12]))
for sub, name in [("hosp","patients"),("hosp","admissions"),("icu","icustays"),("hosp","diagnoses_icd"),("hosp","prescriptions"),
                  ("hosp","emar"),("hosp","microbiologyevents"),("hosp","labevents"),("icu","chartevents"),("icu","inputevents"),("icu","procedureevents")]:
    peek(sub, name)
""")
md("""
## 2. 코호트 정의와 단계별 n

1. 환자별 **첫 ICU 입실** 1회(MIMIC-IV `stay_id`는 연속 재실 1회 = 이미 병합 단위), 그 입원 1건. 재입실 · 재입원 제외.
2. **성인** 18세 이상.
3. **폐렴** ICD-10 J13 · J14 · J15 · J16 · J18.0/.1/.8/.9, ICD-9 481 · 482 · 483 · 485 · 486. 흡인성(J69.0/507.0) · VAP(J95.851/997.31) 있으면 제외. 바이러스 · 인플루엔자만 있으면 미포함.
4. **요로감염** N10 · N12 · N39.0, 590.1 · 590.80 · 590.9 · 599.0. 카테터 관련(T83.51/996.64) 제외. 방광염만은 미포함.
5. 둘 다 있으면 **겹침 제외**.
6. **감염 의심 시각 `t_infection_suspected`** — `culture_first`: 배양 → 72h 안 전신 항생제 ⇒ 배양 시각. `antibiotic_first`: 항생제 → 24h 안 배양 ⇒ 항생제 시각. 가장 이른 것.
7. **지역사회 획득** t_infection_suspected ≤ t0 + 48h.
8. **초기 요법** 의심 시각 이후 첫 항생제 `t_first_antibiotic`부터 24h 안에 시작된 전신 항생제 성분 집합.
""")
code("""
steps = [("환자별 첫 ICU 입실 · 성인", "adult_18plus", "adult_18plus"),
         ("질환 코드 있음", "pna_code", "uti_code"),
         ("제외 코드 뺀 뒤 (흡인성 · VAP / 카테터)", "pna_after_exclusion", "uti_after_exclusion"),
         ("폐렴 · 요로감염 겹침 제외 후", "pna_selected", "uti_selected"),
         ("전신 항생제 기록 있음", "pneumonia_with_antibiotic", "uti_with_antibiotic"),
         ("배양 있음", "pneumonia_with_culture", "uti_with_culture"),
         ("감염 의심 시각 있음", "pneumonia_suspected", "uti_suspected"),
         ("   culture_first: 배양 → 72h 안 항생제", "pneumonia_suspected_culture_first", "uti_suspected_culture_first"),
         ("   antibiotic_first: 항생제 → 24h 안 배양", "pneumonia_suspected_antibiotic_first", "uti_suspected_antibiotic_first"),
         ("48h 이내 = 지역사회 획득 (최종)", "pneumonia_community_acquired", "uti_community_acquired"),
         ("   그중 패혈증 코드 있음", "pneumonia_ca_sepsis_by_code", "uti_ca_sepsis_by_code")]
print(f"{'단계':40}{'폐렴':>10}{'요로감염':>10}")
for lab, kp, ku in steps:
    print(f"{lab:40}{funnel[kp]:>10,}{funnel[ku]:>10,}")
print(f"\\n겹침으로 제외 {funnel['overlap_excluded']:,} · 방광염만 {funnel['cystitis_only_not_included']:,} (미포함) · 바이러스 코드 동반 폐렴(포함, 표시)",
      sum(int(c['viral_cocode']) for c in cohort if c['group']=='pneumonia'))
# cohort.csv의 플래그로 다시 세어 funnel.json과 맞는지 확인
ca = [c for c in cohort if c["community_acquired"] == "1"]
print("cohort.csv에서 다시 센 최종 코호트:", Counter(c["group"] for c in ca))
""")
md("""
## 3. 패혈증 분류 — 세 가지 라벨

| 컬럼 | 정의 | 용도 |
|---|---|---|
| `sepsis_by_code` | ICD-10-CM A40 · A41 · R65.20 · R65.21, ICD-9 038 · 995.91 · 995.92 · 785.52 (K-MIMIC은 KCD A40 · A41 + R65.1) | 코드 기준 보조 |
| `sepsis_by_sofa` | 의심 시각 −48h ~ +24h 창의 **간이 SOFA** ≥ 2 (아래 코드). K-MIMIC에도 같은 코드를 돌린다 | 두 데이터 공용 |
| `sepsis3` | mimic-code 공식 `mimiciv_derived.sepsis3` (BigQuery에서 뽑아 `data/sepsis3_mimic_code.csv`로 둔 경우) | MIMIC 주 라벨 |

간이 SOFA: 호흡(PaO2/FiO2, 4h 안 FiO2 기록이 있을 때만 · 3–4점은 침습 환기 중일 때만) · 응고(혈소판) · 간(빌리루빈) · 심혈관(MAP · 승압제 용량) · 중추신경(GCS) · 신장(크레아티닌 · 소변량). 결측 항목 0점, 기저 SOFA 0 가정.

**활력징후는 ICU 재실 중에만 있다**(응급실 기록은 이 데이터셋에 없음). 의심 시각 뒤 24h 안에 ICU에 들어오지 않은 환자(`sofa_window_covers_icu = 0`, 약 18%)는 검사값으로만 점수가 나와 호흡 · 순환 · 의식 점수가 빠진다. 이 환자들을 빼지 않고 플래그로 표시해 같이 보고한다. 공식 sepsis3 표도 ICU 안에서만 정의되므로 같은 한계를 가진다.
""")
code("""
W_LO, W_HI = -48, 24
t_infection_suspected = {c["hashed_id"]: num(c["t_infection_suspected"]) for c in cohort}
t_first_antibiotic = {c["hashed_id"]: num(c["t_first_antibiotic"]) for c in cohort}
win = defaultdict(lambda: defaultdict(list))        # hid -> item -> [(t, v, text)]
last_before = defaultdict(dict)                      # hid -> item -> (t, v)  (t_first_antibiotic −24h ~ t_first_antibiotic, 기록 시각 기준)
n_rows = 0
with open(f"{DATA}/vitals_labs.csv", newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        n_rows += 1
        h = r["hashed_id"]; ts, ta = t_infection_suspected.get(h), t_first_antibiotic.get(h)
        t = num(r["t_chart"]); v = num(r["valuenum"]) if r["valuenum"] else num(r["value"])
        if t is None or v is None: continue
        if ts is not None and ts + W_LO <= t <= ts + W_HI:
            win[h][r["item"]].append((t, v, r["value"]))
        if ta is not None and ta - 24 <= t <= ta and (r["item"] not in last_before[h] or t > last_before[h][r["item"]][0]):
            last_before[h][r["item"]] = (t, v)
print("vitals_labs rows:", n_rows, "· patients with window data:", len(win))

vent = defaultdict(list)
for r in read("ventilation.csv"):
    if r["type"] == "invasive": vent[r["hashed_id"]].append((num(r["t_start"]), num(r["t_end"])))
vaso = defaultdict(list)
for r in read("vasopressors.csv"):
    vaso[r["hashed_id"]].append((num(r["t_start"]), num(r["t_end"]), r["drug"], num(r["rate"]), r["rateuom"]))

def fio2_frac(v): return v / 100 if v > 1 else v
def sofa(h):
    w = win.get(h, {}); ts = t_infection_suspected[h]; s = {}
    # 호흡: PaO2 / 직전 6h 안 FiO2 (없으면 0.21)
    f_list = sorted(w.get("fio2", []) + w.get("fio2_lab", [])); ratios = []
    for t, p, _ in w.get("pao2", []):
        prev = [x for x in f_list if t - 4 <= x[0] <= t]          # 4h 안의 FiO2 기록이 있을 때만 (없으면 호흡 점수 없음)
        if prev and fio2_frac(prev[-1][1]) > 0: ratios.append(p / fio2_frac(prev[-1][1]))
    if ratios:
        r = min(ratios); ventilated = any(t1 is not None and t1 <= ts + W_HI and (t2 is None or t2 >= ts + W_LO) for t1, t2 in vent.get(h, []))
        s["resp"] = (4 if r < 100 else 3 if r < 200 else 2) if (r < 200 and ventilated) else (2 if r < 300 else 1 if r < 400 else 0)
    if w.get("platelets"):
        p = min(x[1] for x in w["platelets"]); s["coag"] = 4 if p < 20 else 3 if p < 50 else 2 if p < 100 else 1 if p < 150 else 0
    if w.get("bilirubin_total"):
        b = max(x[1] for x in w["bilirubin_total"]); s["liver"] = 4 if b >= 12 else 3 if b >= 6 else 2 if b >= 2 else 1 if b >= 1.2 else 0
    maps = [x[1] for x in w.get("map_abp", []) + w.get("map_nibp", [])]
    cv = 1 if maps and min(maps) < 70 else 0
    for t1, t2, drug, rate, uom in vaso.get(h, []):
        if t1 is None or t1 > ts + W_HI or (t2 is not None and t2 < ts + W_LO): continue
        rate = rate or 0
        if drug == "dobutamine": cv = max(cv, 2)
        elif drug == "dopamine": cv = max(cv, 4 if rate > 15 else 3 if rate > 5 else 2)
        elif drug in ("norepinephrine", "epinephrine"): cv = max(cv, 4 if rate > 0.1 else 3)
    if maps or vaso.get(h): s["cardio"] = cv
    # GCS: 같은 시각의 eye+motor+verbal (verbal 0 = 삽관 → 1점으로 봄)
    byt = defaultdict(dict)
    for item in ("gcs_eye", "gcs_verbal", "gcs_motor"):
        for t, v, _ in w.get(item, []): byt[t][item] = v
    totals = [d["gcs_eye"] + d["gcs_motor"] + (d["gcs_verbal"] if d["gcs_verbal"] > 0 else 1) for d in byt.values() if len(d) == 3]
    if totals:
        g = min(totals); s["cns"] = 4 if g < 6 else 3 if g < 10 else 2 if g < 13 else 1 if g < 15 else 0
    ren = None
    if w.get("creatinine"):
        c = max(x[1] for x in w["creatinine"]); ren = 4 if c >= 5 else 3 if c >= 3.5 else 2 if c >= 2 else 1 if c >= 1.2 else 0
    uo = sorted(w.get("urine_output_ml", []))
    if len(uo) >= 2 and uo[-1][0] - uo[0][0] >= 12:
        per_day = sum(x[1] for x in uo) / ((uo[-1][0] - uo[0][0]) / 24)
        ren = max(ren or 0, 4 if per_day < 200 else 3 if per_day < 500 else 0)
    if ren is not None: s["renal"] = ren
    return s
for c in cohort:
    h = c["hashed_id"]
    if t_infection_suspected[h] is None: c["sofa_simplified"] = ""; c["sepsis_by_sofa"] = ""; continue
    s = sofa(h); c["sofa_simplified"] = sum(s.values()); c["sofa_components"] = s; c["sepsis_by_sofa"] = int(sum(s.values()) >= 2)
ca = [c for c in cohort if c["community_acquired"] == "1"]
print(f"\\n{'집단':12}{'n':>7}{'패혈증 코드':>12}{'SOFA≥2':>10}{'둘 다':>8}{'코드만':>8}{'SOFA만':>8}{'일치율':>8}")
for g in ("pneumonia", "uti"):
    d = [c for c in ca if c["group"] == g]; n = len(d)
    code_ = sum(c["sepsis_by_code"] == "1" for c in d); sofa_ = sum(c["sepsis_by_sofa"] == 1 for c in d)
    both = sum(c["sepsis_by_code"] == "1" and c["sepsis_by_sofa"] == 1 for c in d)
    agree = sum((c["sepsis_by_code"] == "1") == (c["sepsis_by_sofa"] == 1) for c in d)
    print(f"{g:12}{n:>7,}{code_:>12,}{sofa_:>10,}{both:>8,}{code_-both:>8,}{sofa_-both:>8,}{pct(agree, n):>8}")
print("\\nSOFA 구성요소가 하나라도 계산된 비율:", pct(sum(1 for c in ca if c.get('sofa_components')), len(ca)), "%")
cov = Counter(c["sofa_window_covers_icu"] for c in ca)
print(f"SOFA 창이 ICU 재실과 겹치는 환자 {cov.get('1',0):,} ({pct(cov.get('1',0), len(ca))}%) · 안 겹침(검사값만으로 점수) {cov.get('0',0):,} ({pct(cov.get('0',0), len(ca))}%)")
for g in ("pneumonia", "uti"):
    d = [c for c in ca if c["group"] == g and c["sofa_window_covers_icu"] == "0"]
    print(f"  [{g}] 창이 ICU와 안 겹치는 환자 중 간이 SOFA≥2: {pct(sum(c['sepsis_by_sofa'] == 1 for c in d), len(d))}% (n={len(d):,})")
""")
md("""
### 3-2. mimic-code 공식 sepsis3 표 결합

BigQuery(physionet-data)에서 `docs/bigquery_sepsis3.sql`의 1번 쿼리를 돌려 CSV로 저장하고 `data/sepsis3_mimic_code.csv`로 두면 아래 셀이 `stay_id`로 결합한다. 파일이 없으면 건너뛴다.
""")
code("""
from datetime import datetime
SEP = f"{DATA}/sepsis3_mimic_code.csv"; HAS_SEPSIS3 = os.path.exists(SEP)
def pdt(x):
    x = (x or "").strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try: return datetime.strptime(x, fmt)
        except ValueError: pass
    return None
if HAS_SEPSIS3:
    idm = {r["hashed_id"]: r for r in read("id_map.csv")}
    s3 = {r["stay_id"]: r for r in csv.DictReader(open(SEP, newline="", encoding="utf-8-sig"))}
    for c in cohort:
        m = idm[c["hashed_id"]]; r = s3.get(m["stay_id"]); t0 = pdt(m.get("t0_abs", ""))
        c["sepsis3"] = int(r is not None and str(r.get("sepsis3", "")).strip().lower() in ("true", "1", "t"))
        c["sepsis3_sofa_score"] = r["sofa_score"] if r else ""
        tsus = pdt(r["suspected_infection_time"]) if r else None
        c["t_sepsis3_suspected"] = round((tsus - t0).total_seconds() / 3600, 2) if (tsus and t0) else ""
    print(f"sepsis3 표 {len(s3):,} stay 결합 · 코호트 중 표에 있는 입원 {sum(1 for c in cohort if c['sepsis3_sofa_score'] != ''):,}")
    print(f"\\n{'집단':12}{'n':>7}{'sepsis3':>9}{'코드':>7}{'간이SOFA':>9}{'sepsis3=코드 일치':>18}{'sepsis3=SOFA 일치':>18}{'의심시각 차 중앙값(h)':>22}")
    for g in ("pneumonia", "uti"):
        d = [c for c in ca if c["group"] == g]; n = len(d)
        a3 = sum(c["sepsis3"] == 1 for c in d); ac = sum(c["sepsis_by_code"] == "1" for c in d); asf = sum(c["sepsis_by_sofa"] == 1 for c in d)
        ag_c = sum((c["sepsis3"] == 1) == (c["sepsis_by_code"] == "1") for c in d); ag_s = sum((c["sepsis3"] == 1) == (c["sepsis_by_sofa"] == 1) for c in d)
        dt = median([abs(num(c["t_sepsis3_suspected"]) - num(c["t_infection_suspected"])) for c in d if c["t_sepsis3_suspected"] != ""])
        print(f"{g:12}{n:>7,}{a3:>9,}{ac:>7,}{asf:>9,}{pct(ag_c, n):>18}{pct(ag_s, n):>18}{(round(dt, 1) if dt is not None else '-'):>22}")
else:
    for c in cohort: c["sepsis3"] = ""
    print("data/sepsis3_mimic_code.csv 없음 → BigQuery에서 docs/bigquery_sepsis3.sql 1번 쿼리를 돌려 넣으면 결합한다.")
SEPSIS_PRIMARY = "sepsis3" if HAS_SEPSIS3 else "sepsis_by_code"
print("집단 나누기와 평가 표본의 기준 라벨:", SEPSIS_PRIMARY)
""")
md("""
## 4. 집단별 요약 — 폐렴 / 요로감염 × 패혈증 유 / 무

`sepsis_by_code` · `sepsis_by_sofa` · (있으면) `sepsis3` 기준 표를 낸다. 항생제 성분 · 요법 · AWaRe는 **초기 요법**(t_first_antibiotic ~ +24h 시작) 기준.
""")
code("""
reg_by = defaultdict(set); aware_of, class_of = {}, {}
for r in abx:
    aware_of[r["ingredient"]] = r["aware"]; class_of[r["ingredient"]] = r["abx_class"]
    if r["in_initial_regimen"] == "1": reg_by[r["hashed_id"]].add(r["ingredient"])

def summ(d):
    n = len(d); o = {"n": n}
    if not n: return o
    o["원내 사망 %"] = pct(sum(c["death_inhosp"] == "1" for c in d), n)
    o["나이 중앙값"] = median([num(c["age"]) for c in d]); o["여성 %"] = pct(sum(c["sex"] == "F" for c in d), n)
    o["ICU 재실 중앙값(일)"] = round(median([num(c["icu_los_d"]) for c in d]), 1)
    o["t0→첫 항생제 중앙값(h)"] = round(median([num(c["t_first_antibiotic"]) for c in d]), 1)
    o["의심 시각이 ICU 입실 전 %"] = pct(sum(c["suspicion_before_icu"] == "1" for c in d), n)
    o["SOFA 창이 ICU와 겹침 %"] = pct(sum(c["sofa_window_covers_icu"] == "1" for c in d), n)
    o["첫 항생제 전 혈액배양 %"] = pct(sum(c["blood_culture_before_antibiotic"] == "1" for c in d), n)
    o["기계환기 %"] = pct(sum(c["mech_vent"] == "1" for c in d), n); o["승압제 %"] = pct(sum(c["vasopressor"] == "1" for c in d), n)
    nag = Counter(min(int(c["n_initial_antibiotics"]), 3) if c["n_initial_antibiotics"] else 0 for c in d)
    o["성분 수 1/2/3+ %"] = " / ".join(pct(nag[k], n) for k in (1, 2, 3))
    ing = Counter(i for c in d for i in reg_by.get(c["hashed_id"], ()))
    o["성분 상위 5"] = ", ".join(f"{i} {pct(k, n)}%" for i, k in ing.most_common(5))
    reg = Counter(c["initial_regimen"] for c in d if c["initial_regimen"])
    o["요법 상위 5"] = ", ".join(f"{r} {pct(k, n)}%" for r, k in reg.most_common(5))
    aw = Counter(aware_of.get(i, "?") for c in d for i in reg_by.get(c["hashed_id"], ()))
    tot = sum(aw.values()) or 1
    o["AWaRe (성분 건수 기준) Access/Watch/Reserve %"] = " / ".join(pct(aw[k], tot) for k in ("access", "watch", "reserve"))
    o["anti-MRSA 포함 %"] = pct(sum(any("anti_MRSA" in class_of.get(i, "") for i in reg_by.get(c["hashed_id"], ())) for c in d), n)
    o["항녹농균 포함 %"] = pct(sum(any("antipseudomonal" in class_of.get(i, "") for i in reg_by.get(c["hashed_id"], ())) for c in d), n)
    o["당뇨/CKD/COPD/면역저하 %"] = " / ".join(pct(sum(c[k] == "1" for c in d), n) for k in ("dm", "ckd", "copd", "immuno"))
    o["90일 내 입원 / IV 항생제 %"] = " / ".join(pct(sum(c[k] == "1" for c in d), n) for k in ("prior_admission_90d", "prior_iv_abx_90d"))
    return o

def table(key, label):
    cols = [(g, s, f"{'폐렴' if g=='pneumonia' else '요로감염'} · 패혈증 {'있음' if s else '없음'}") for g in ("pneumonia", "uti") for s in (1, 0)]
    res = {}
    for g, s, name in cols:
        d = [c for c in ca if c["group"] == g and (str(c[key]) == "1") == bool(s)]
        res[name] = summ(d)
    print(f"\\n=== {label} ===")
    keys = list(next(iter(res.values())).keys())
    print(f"{'':36}" + "".join(f"{name:>34}" for name in res))
    for k in keys:
        if k in ("성분 상위 5", "요법 상위 5"):
            print(f"{k}:")
            for name in res: print(f"   {name}: {res[name].get(k, '')}")
        else:
            print(f"{k:36}" + "".join(f"{str(res[name].get(k, '')):>34}"[:34] for name in res))
    return res
summary_code = table("sepsis_by_code", "패혈증 = 진단코드")
summary_sofa = table("sepsis_by_sofa", "패혈증 = 간이 SOFA ≥ 2")
summary_sepsis3 = table("sepsis3", "패혈증 = mimic-code sepsis3 (주 라벨)") if HAS_SEPSIS3 else None
""")
md("""
## 5. 타이밍 분포

- 감염 의심 시각이 t0(병원 도착)로부터 언제인가, 배양→항생제(culture_first)에 걸린 시간, 항생제→배양(antibiotic_first)에 걸린 시간.
- 병원 도착 → 첫 항생제(door-to-antibiotic)는 CAP 지침의 시간 지표. "쇼크 인지 후 1시간 · 패혈증 3시간"은 인지 시각이 없어 도착 시각으로 대신 본다.
""")
code("""
def hist(vals, bins, unit="h"):
    vals = [v for v in vals if v is not None]; n = len(vals)
    for lo, hi in zip(bins[:-1], bins[1:]):
        k = sum(lo <= v < hi for v in vals); print(f"  {lo:>5}~{hi:<5}{unit} {k:>6,} ({pct(k, n)}%)")
    print(f"  ≥{bins[-1]:<10}{unit} {sum(v >= bins[-1] for v in vals):>6,}")
for g in ("pneumonia", "uti"):
    d = [c for c in ca if c["group"] == g]
    print(f"\\n[{g}] t0 → 감염 의심 시각")
    hist([num(c["t_infection_suspected"]) for c in d], [-48, -6, 0, 6, 12, 24, 48])
    print(f"[{g}] culture_first: 배양 → 첫 항생제 (h)")
    hist([num(c["t_first_antibiotic"]) - num(c["t_infection_suspected"]) for c in d if c["suspicion_rule"] == "culture_first" and c["t_first_antibiotic"] != ""], [0, 1, 3, 6, 12, 24, 72])
    print(f"[{g}] 병원 도착 → 첫 항생제 (door-to-antibiotic) 1h / 3h / 6h 이내 %:",
          " / ".join(pct(sum(num(c['t_first_antibiotic']) <= k for c in d if c['t_first_antibiotic'] != ''), len(d)) for k in (1, 3, 6)))
    print(f"[{g}] 응급실 경유 %:", pct(sum(c['ed_visit'] == '1' for c in d), len(d)), "· ICD-10 시기 %:", pct(sum(c['icd_version'] == '10' for c in d), len(d)))
""")
md("""
## 6. 약품명 → 성분 매핑 확인

K-MIMIC에서는 약품명이 한글 · 상품명일 수 있어 같은 표(`drug_raw → ingredient → class → AWaRe`)를 먼저 만들어야 한다. MIMIC의 표기(tall-man 대문자, 괄호 상품명)를 어떻게 성분으로 접었는지 본다. AWaRe는 2023 목록 기준이라 **2025 목록으로 검수**가 필요하다.
""")
code("""
dr = read("drug_raw_counts.csv")
print(f"{'drug_raw (원문)':50}{'ingredient':30}{'n':>8}")
for r in dr[:30]:
    print(f"{r['drug_raw'][:50]:50}{r['ingredient']:30}{int(r['n']):>8,}")
print("\\n성분 수:", len({r['ingredient'] for r in dr}), "· AWaRe 미매핑 성분:", sorted({r['ingredient'] for r in abx if not r['aware']}))
print("경로(route) 분포 상위:", Counter(r['route'] for r in abx).most_common(8))
""")
md("""
## 7. 사례 카드 예시 — 에이전트에게 보여줄 형태

t_first_antibiotic = T+0. 카드에는 **t_first_antibiotic 이전에 알 수 있던 것만** 넣는다: 퇴원 진단 · 사망 · t_first_antibiotic 이후 배양 결과는 뺀다. 배양은 "채취 사실"만.
""")
code("""
def card(c):
    h = c["hashed_id"]; ta = num(c["t_first_antibiotic"]); rel = lambda t: f"T{(num(t) - ta):+.1f}h" if t not in ("", None) and num(t) is not None else None
    lb = last_before.get(h, {})
    def last(*items):
        for it in items:
            if it in lb: return lb[it][1]
    temp = last("temp_c"); tf = last("temp_f")
    if temp is None and tf is not None: temp = round((tf - 32) * 5 / 9, 1)
    cults = sorted({(num(r["t_collect"]), r["spec_type"]) for r in cult if r["hashed_id"] == h and r["is_culture"] == "1" and num(r["t_collect"]) is not None and num(r["t_collect"]) <= ta})
    emp = [{"ingredient": r["ingredient"], "class": r["abx_class"], "aware": r["aware"], "route": r["route"], "dose": f"{r['dose']} {r['dose_unit']}".strip(),
            "start": rel(r["t_start"]), "first_admin": rel(r["t_first_administration"])} for r in abx if r["hashed_id"] == h and r["in_initial_regimen"] == "1"]
    return {"case_id": h, "group": c["group"], "t0": "T+0 = 첫 항생제 처방", "hospital_arrival": rel(0), "icu_admit": rel(c["t_icu_in"]),
            "age": int(c["age"]), "sex": c["sex"], "weight_kg": c["weight_kg"] or None, "ed_visit": c["ed_visit"] == "1",
            "vitals_before_t0": {"heart_rate": last("heart_rate"), "map": last("map_abp", "map_nibp"), "sbp": last("sbp_abp", "sbp_nibp"), "resp_rate": last("resp_rate"),
                                 "spo2": last("spo2"), "temp_c": temp, "gcs_eye": last("gcs_eye"), "gcs_motor": last("gcs_motor"), "fio2": last("fio2")},
            "labs_before_t0": {k: last(k) for k in ("wbc", "platelets", "creatinine", "bun", "lactate", "bilirubin_total", "crp", "pao2", "ph")},
            "ventilation": {"invasive": c["mech_vent"] == "1" and num(c["t_vent_start"]) is not None and num(c["t_vent_start"]) <= ta, "started": rel(c["t_vent_start"]) if c["mech_vent"] == "1" else None},
            "vasopressor": {"any": c["vasopressor"] == "1" and num(c["t_vaso_start"]) is not None and num(c["t_vaso_start"]) <= ta, "started": rel(c["t_vaso_start"]) if c["vasopressor"] == "1" else None},
            "cultures_before_t0": [{"type": s, "time": f"T{t - ta:+.1f}h"} for t, s in cults],
            "history": {"admission_90d": c["prior_admission_90d"] == "1", "iv_antibiotics_90d": c["prior_iv_abx_90d"] == "1", "mrsa_1y": c["prior_mrsa_1y"] == "1", "pseudomonas_1y": c["prior_pseudomonas_1y"] == "1"},
            "comorbidities": [k for k in ("dm", "ckd", "copd", "bronchiectasis", "hf", "liver", "cancer", "immuno", "pregnancy", "uro_obstruction", "alcohol") if c[k] == "1"],
            "empirical_set": emp,
            "not_included": ["퇴원 진단코드", "사망 여부", "t0 이후 배양 결과", "SOFA 점수"]}
random.seed(7)
ex = random.choice([c for c in ca if c["t_first_antibiotic"] != "" and c["group"] == "pneumonia"])
print(json.dumps(card(ex), ensure_ascii=False, indent=1))
""")
md("""
## 8. 평가용 표본과 결과 저장

4집단(주 라벨 기준: sepsis3가 있으면 sepsis3, 없으면 진단코드) × 5명 + 예비 5명, 고정 seed. `results/` 에 집계표 · 표본 목록 · 카드 JSON(본 표본 20명)을 저장한다.
""")
code("""
os.makedirs(f"{RES}/cards", exist_ok=True)
random.seed(2026); sample = []
for g in ("pneumonia", "uti"):
    for s in ("1", "0"):
        pool = [c for c in ca if c["group"] == g and str(c[SEPSIS_PRIMARY]) == s and c["t_first_antibiotic"] != "" and c["initial_regimen"]]
        pick = random.sample(pool, 10)
        for i, c in enumerate(pick):
            sample.append({"hashed_id": c["hashed_id"], "group": g, "stratified_by": SEPSIS_PRIMARY, "sepsis_label": s, "sepsis_by_code": c["sepsis_by_code"], "sepsis_by_sofa": c["sepsis_by_sofa"], "sepsis3": c["sepsis3"], "role": "main" if i < 5 else "backup"})
            if i < 5: json.dump(card(c), open(f"{RES}/cards/{c['hashed_id']}.json", "w"), ensure_ascii=False, indent=1)
with open(f"{RES}/eval_sample.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(sample[0])); w.writeheader(); w.writerows(sample)

with open(f"{RES}/funnel.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["step", "pneumonia", "uti"])
    for lab, kp, ku in steps: w.writerow([lab.strip(), funnel[kp], funnel[ku]])
json.dump({"sepsis_by_code": summary_code, "sepsis_by_sofa": summary_sofa, "sepsis3": summary_sepsis3}, open(f"{RES}/group_summary.json", "w"), ensure_ascii=False, indent=1)
with open(f"{RES}/cohort_with_sofa.csv", "w", newline="") as f:
    fields = [k for k in cohort[0].keys() if k != "sofa_components"] + ["sofa_components"]
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
    for c in cohort: w.writerow({**c, "sofa_components": json.dumps(c.get("sofa_components", {}))})
# 사람이 읽는 요약 (마크다운)
L = ["# MIMIC-IV 폐렴 · 요로감염 초기 항생제 코호트 — 결과 요약", "", "## 단계별 n", "", "| 단계 | 폐렴 | 요로감염 |", "|---|---|---|"]
L += [f"| {lab.strip()} | {funnel[kp]:,} | {funnel[ku]:,} |" for lab, kp, ku in steps]
for title, res in [("패혈증 = 진단코드", summary_code), ("패혈증 = 간이 SOFA ≥ 2", summary_sofa)] + ([("패혈증 = mimic-code sepsis3", summary_sepsis3)] if HAS_SEPSIS3 else []):
    L += ["", f"## 집단별 요약 ({title})", "", "| 항목 | " + " | ".join(res) + " |", "|---|" + "---|" * len(res)]
    for k in next(iter(res.values())):
        L.append(f"| {k} | " + " | ".join(str(res[name].get(k, "")) for name in res) + " |")
open(f"{RES}/summary.md", "w", encoding="utf-8").write("\\n".join(L))
print("saved:", sorted(os.listdir(RES)))
""")
md("""
## 9. 한계와 K-MIMIC에 적용할 때 할 일

- **단일 기관**(BIDMC) · 2008–2022. 항생제 시각은 처방 시작 시각이고, 실제 투여 시각(`t_first_administration`)은 2016년 이후 입원에만 있다.
- **활력징후는 ICU 안에서만** 기록된다. 의심 시각이 응급실이면 카드의 vital이 비어 있을 수 있다. 검사(labevents)는 응급실부터 있다.
- 패혈증 라벨은 **진단코드** · **간이 SOFA**(두 데이터 공용 코드) · **mimic-code sepsis3**(MIMIC 주 라벨) 세 가지다. 공식 표와 간이 SOFA의 일치율이 간이 SOFA를 K-MIMIC에 쓸 수 있는지의 근거가 된다.
- `procalcitonin`은 MIMIC-IV에 없다. AWaRe 매핑은 2023 목록 기준.
- K-MIMIC: `extract_mimic_cohort.py`의 테이블 · 컬럼 이름(대문자) · KCD 코드 · 약품명 매핑 · ICU stay 병합 · 날짜 상대화 · 나이 문자열만 바꾸면 같은 CSV가 나온다. 그러면 이 노트북은 2장부터 그대로 돈다.
""")

def build(execute=True):
    here = os.path.dirname(os.path.abspath(__file__)); nbdir = os.path.join(here, "..", "notebooks"); os.chdir(nbdir)
    ns = {}; cells = []
    for i, (kind, src) in enumerate(CELLS):
        if kind == "markdown":
            cells.append({"cell_type": "markdown", "metadata": {}, "source": src}); continue
        outputs = []
        if execute:
            buf = io.StringIO(); t = time.time()
            try:
                with contextlib.redirect_stdout(buf): exec(compile(src, f"<cell {i}>", "exec"), ns)
            except Exception:
                buf.write(traceback.format_exc()); print(f"cell {i} ERROR", file=sys.stderr)
            text = buf.getvalue()
            if text: outputs.append({"output_type": "stream", "name": "stdout", "text": text})
            print(f"cell {i} ok {time.time()-t:.0f}s, {len(text)} chars", file=sys.stderr)
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "source": src, "outputs": outputs})
    nb = {"cells": cells, "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
          "language_info": {"name": "python", "version": "3.10"}}, "nbformat": 4, "nbformat_minor": 5}
    json.dump(nb, open("mimic_pna_uti.ipynb", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("notebook written", file=sys.stderr)

if __name__ == "__main__":
    build(execute="--no-exec" not in sys.argv)
