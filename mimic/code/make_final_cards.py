#!/usr/bin/env python3
"""최종 데이터 (RAG · 에이전트에 붙일 것) — 표준 라이브러리만 사용
  results/final/cards_all.jsonl      최종 코호트(지역사회 획득) 전원의 사례 카드, 1행 = 1 JSON
  results/final/cards_eval20.jsonl   임상의 평가용 본 표본 20건 (results/eval_sample.csv 의 main)
  results/final/labels.csv           카드에 넣지 않은 라벨 · 결과 (판정 뒤 준수율 집계 · 분석용)
  results/final/card_schema.md       필드 설명
카드 규칙: 모든 시각은 첫 항생제 = T+0 기준. 값은 '보고 시각(storetime, 없으면 기록 시각) ≤ T+0' 인 것만 넣는다 (정보 누출 방지).
실행: python3 make_final_cards.py   (code/ 폴더에서)
"""
import csv, json, os, hashlib
from collections import defaultdict
DATA, RES = "../data", "../results"; OUT = f"{RES}/final"; os.makedirs(OUT, exist_ok=True)
def read(name, d=DATA):
    with open(f"{d}/{name}", newline="", encoding="utf-8") as f: return list(csv.DictReader(f))
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

cohort = read("cohort_with_sofa.csv", RES) if os.path.exists(f"{RES}/cohort_with_sofa.csv") else read("cohort.csv")
ca = [c for c in cohort if c["community_acquired"] == "1" and c["t_first_antibiotic"] != ""]
t_abx = {c["hashed_id"]: num(c["t_first_antibiotic"]) for c in ca}
print("final cohort with first antibiotic:", len(ca))

# 1) 첫 항생제 전 24h 안의 마지막 값 — 보고 시각 기준
last = defaultdict(dict); n_leak_blocked = 0
with open(f"{DATA}/vitals_labs.csv", newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        h = r["hashed_id"]; ta = t_abx.get(h)
        if ta is None: continue
        tc = num(r["t_chart"]); ts = num(r["t_store"]); avail = ts if ts is not None else tc
        v = num(r["valuenum"]) if r["valuenum"] else num(r["value"])
        if tc is None or v is None or tc < ta - 24 or tc > ta: continue
        if avail > ta: n_leak_blocked += 1; continue
        it = r["item"]
        if it not in last[h] or tc > last[h][it][0]: last[h][it] = (tc, v, avail)
print("values drawn before T0 but reported after (blocked):", n_leak_blocked)

abx_by = defaultdict(list)
for r in read("antibiotics.csv"):
    if r["in_initial_regimen"] == "1": abx_by[r["hashed_id"]].append(r)
cult_by = defaultdict(set)
for r in read("cultures.csv"):
    if r["is_culture"] == "1" and num(r["t_collect"]) is not None: cult_by[r["hashed_id"]].add((num(r["t_collect"]), r["spec_type"]))

def rel(t, ta): return f"T{(num(t) - ta):+.1f}h" if t not in ("", None) and num(t) is not None else None
def card(c):
    h = c["hashed_id"]; ta = t_abx[h]; lb = last.get(h, {})
    def lastv(*items):
        for it in items:
            if it in lb: return lb[it][1]
    def lastt(*items):
        for it in items:
            if it in lb: return f"T{(lb[it][0] - ta):+.1f}h"
    temp = lastv("temp_c"); tf = lastv("temp_f")
    if temp is None and tf is not None: temp = round((tf - 32) * 5 / 9, 1)
    vent_on = c["mech_vent"] == "1" and num(c["t_vent_start"]) is not None and num(c["t_vent_start"]) <= ta
    vaso_on = c["vasopressor"] == "1" and num(c["t_vaso_start"]) is not None and num(c["t_vaso_start"]) <= ta
    emp = sorted(({"ingredient": r["ingredient"], "class": r["abx_class"], "aware": r["aware"], "route": r["route"],
                   "dose": f"{r['dose']} {r['dose_unit']}".strip(), "doses_per_24h": r["doses_per_24h"],
                   "ordered": rel(r["t_start"], ta), "first_administered": rel(r["t_first_administration"], ta)} for r in abx_by.get(h, [])),
                 key=lambda e: (e["ordered"] or "", e["ingredient"]))
    return {
        "case_id": h, "dataset": "MIMIC-IV v3.1", "hospital": c["hospital"], "admission_era": c["anchor_year_group"],
        "cohort_group": c["group"],                      # 퇴원 코드로 정한 코호트 라벨 (폐렴 / 요로감염). 세부 분류 · 중증도는 에이전트(A1)가 판단
        "time_reference": "T+0 = first antibiotic order; all times relative; values included only if reported before T+0",
        "hospital_arrival": rel(0, ta), "ed_visit": c["ed_visit"] == "1", "icu_admission": rel(c["t_icu_in"], ta), "icu_type": c["first_icu_type"],
        "age": int(float(c["age"])), "sex": c["sex"], "weight_kg": num(c["weight_kg"]),
        "vitals_before_t0": {"heart_rate": lastv("heart_rate"), "sbp": lastv("sbp_abp", "sbp_nibp"), "dbp": lastv("dbp_abp", "dbp_nibp"), "map": lastv("map_abp", "map_nibp"),
                             "resp_rate": lastv("resp_rate"), "spo2": lastv("spo2"), "temp_c": temp, "gcs_eye": lastv("gcs_eye"), "gcs_verbal": lastv("gcs_verbal"), "gcs_motor": lastv("gcs_motor"),
                             "fio2": lastv("fio2"), "measured_at": {k: lastt(*v) for k, v in (("heart_rate", ("heart_rate",)), ("map", ("map_abp", "map_nibp")), ("temp_c", ("temp_c", "temp_f")))}},
        "labs_before_t0": {k: lastv(k) for k in ("wbc", "platelets", "creatinine", "bun", "bilirubin_total", "lactate", "crp", "pao2", "pco2", "ph", "sodium", "potassium", "glucose", "albumin", "inr", "bicarbonate", "troponin_t", "ntprobnp", "hemoglobin")},
        "respiratory_support": {"invasive_ventilation": vent_on, "started": rel(c["t_vent_start"], ta) if vent_on else None},
        "vasopressor": {"any": vaso_on, "started": rel(c["t_vaso_start"], ta) if vaso_on else None},
        "cultures_before_t0": [{"specimen": sp, "collected": f"T{t - ta:+.1f}h"} for t, sp in sorted(cult_by.get(h, set())) if t <= ta],
        "history": {"admission_within_90d": c["prior_admission_90d"] == "1", "iv_antibiotics_within_90d": c["prior_iv_abx_90d"] == "1",
                    "mrsa_isolated_within_1y": c["prior_mrsa_1y"] == "1", "pseudomonas_isolated_within_1y": c["prior_pseudomonas_1y"] == "1"},
        "comorbidities": [k for k in ("dm", "ckd", "copd", "bronchiectasis", "hf", "liver", "cancer", "immuno", "pregnancy", "uro_obstruction", "alcohol") if c[k] == "1"],
        "empirical_regimen": emp,
        "not_included": ["discharge diagnoses", "in-hospital death", "culture results reported after T+0", "SOFA score / sepsis label", "values reported after T+0"],
    }

n = 0
with open(f"{OUT}/cards_all.jsonl", "w", encoding="utf-8") as f:
    for c in ca: f.write(json.dumps(card(c), ensure_ascii=False) + "\n"); n += 1
print("cards_all.jsonl:", n)
ev = [r for r in read("eval_sample.csv", RES) if r["role"] == "main"]; evid = {r["hashed_id"] for r in ev}
with open(f"{OUT}/cards_eval20.jsonl", "w", encoding="utf-8") as f:
    for c in ca:
        if c["hashed_id"] in evid: f.write(json.dumps(card(c), ensure_ascii=False) + "\n")
print("cards_eval20.jsonl:", len(evid))
for c in ca: c["cefazolin_only_regimen"] = "1" if c.get("initial_regimen", "") == "cefazolin" else "0"   # 수술 예방 투여 의심 → 판정에서 "해당 없음"
LAB = ["hashed_id", "group", "cefazolin_only_regimen", "sepsis3", "sepsis_by_sofa", "sofa_simplified", "sepsis_by_code", "septic_shock_by_code", "sofa_window_covers_icu", "suspicion_rule",
       "t_infection_suspected", "t_first_antibiotic", "initial_regimen", "n_initial_antibiotics", "blood_culture_before_antibiotic", "death_inhosp", "icu_los_d", "hosp_los_d",
       "mech_vent", "vasopressor", "viral_cocode", "icd_version", "anchor_year_group"]
with open(f"{OUT}/labels.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=LAB, extrasaction="ignore"); w.writeheader(); w.writerows(ca)
open(f"{OUT}/card_schema.md", "w", encoding="utf-8").write("""# 사례 카드 (cards_all.jsonl) 필드 설명

한 줄 = 환자 1명(입원 1건)의 JSON. 에이전트 · RAG 입력은 이 카드만 쓴다. 정답 · 결과(labels.csv)는 판정 뒤 집계에만 쓴다.

| 필드 | 뜻 |
|---|---|
| case_id | 해시 ID (id_map.csv 로만 복원) |
| dataset, hospital, admission_era | 데이터셋 · 기관 · 입원 시기(3년 구간; 지침 발행 연도와 맞출 때 사용) |
| cohort_group | 코호트 라벨 pneumonia / uti (퇴원 코드로 선정). CAP 세부형 · 중증도 · 단순/복잡 UTI 는 에이전트(A1)가 카드 내용으로 판단 |
| time_reference | 모든 시각은 첫 항생제 처방 = T+0 기준 상대 시간. 'T-5.2h' = 첫 항생제 5.2시간 전 |
| hospital_arrival, ed_visit, icu_admission, icu_type | 도착 시각(상대), 응급실 경유, ICU 입실 시각(상대; T+ 이면 항생제 뒤 입실), 첫 ICU 종류 |
| age, sex, weight_kg | 체중은 ICU 기록(없으면 null) |
| vitals_before_t0 | T+0 전 24h 안에서 **보고 시각 ≤ T+0** 인 마지막 값. 활력징후는 ICU 재실 중에만 기록되므로 응급실 단계면 null 이 많다 (약 32%). measured_at 에 측정 시각 |
| labs_before_t0 | 같은 규칙의 마지막 검사값 (WBC, 혈소판, Cr, BUN, 빌리루빈, 젖산, CRP, PaO2, pCO2, pH, Na, K, 당, 알부민, INR, HCO3, 트로포닌, NT-proBNP, Hb). procalcitonin 은 MIMIC-IV 에 없음 |
| respiratory_support, vasopressor | T+0 이전에 시작된 침습적 환기 · 승압제 여부와 시작 시각 |
| cultures_before_t0 | T+0 이전 채취 검체의 종류와 시각만. **결과 · 균 · 감수성은 없음** |
| history | 90일 내 입원 · 정맥 항생제, 1년 내 MRSA · 녹농균 분리 (이전 입원 · 검사 기록 기준) |
| comorbidities | 코드 기반 플래그 목록: dm, ckd, copd, bronchiectasis, hf, liver, cancer, immuno, pregnancy, uro_obstruction, alcohol |
| empirical_regimen | 초기 요법 = T+0 부터 24h 안에 시작된 전신 항생제. 성분(INN) · 계열 · AWaRe(2023 목록) · 경로 · 용량 · 하루 횟수 · 처방 시각 · 첫 투여 시각(EMAR, 2016+) |
| not_included | 일부러 뺀 것 |

## labels.csv (카드에 없는 정보 — 판정 뒤에만 사용)
sepsis3(공식, 주 라벨) · sepsis_by_sofa · sofa_simplified · sepsis_by_code · septic_shock_by_code · sofa_window_covers_icu · suspicion_rule · t_infection_suspected · t_first_antibiotic · initial_regimen · n_initial_antibiotics · blood_culture_before_antibiotic · death_inhosp · icu_los_d · hosp_los_d · mech_vent · vasopressor · viral_cocode · icd_version · anchor_year_group

## 에이전트 출력(판정) 권장 형식
{"case_id", "classification": {"syndrome", "severity", "basis"}, "rules_checked": [{"rule_id", "jurisdiction": "KR|INTL", "item": "timing|culture_first|selection|stop|avoid", "verdict": "준수|비준수|해당 없음|정당한 이탈", "evidence": "지침 원문 구절 · 쪽", "reason"}], "overall": "준수|비준수|정당한 이탈"}
준수율 = 집단별(폐렴/요로감염 × 패혈증 유/무, labels.csv 의 sepsis3 기준) 규칙 항목별 '준수' 비율.

## 주의
MIMIC-IV 파생 환자 단위 자료다. PhysioNet 자격자 · 허가된 플랫폼 안에서만 다루고, 외부 LLM API 로 보내지 않는다. K-MIMIC 카드도 같은 필드로 만들면 같은 에이전트 코드가 돈다.
""")
print("done:", sorted(os.listdir(OUT)))