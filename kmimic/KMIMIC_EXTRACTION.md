# K-MIMIC 추출 · 판정 실행 안내

K-MIMIC 원천 테이블에서 SQL 3개로 CSV 3개를 만들고, 나머지(의심 시각 · 초기 요법 · 카드 · 판정 · 집계)는 이 폴더의 파이썬(표준 라이브러리만)이 한다. 환자 단위 파일은 플랫폼 안에 두고 집계 텍스트만 내보낸다.

```
 K-MIMIC 원천 테이블                      파이썬 (이 폴더, 표준 라이브러리만)
 ┌──────────────┐  쿼리 1  cohort.csv      ┌───────────────────────────┐
 │ ADMISSIONS   │ ───────▶ (입원 1건=1행)   │ ② derive   의심 시각·초기 요법 │
 │ PATIENTS     │  쿼리 2  antibiotics.csv │ ③ cards    사례 카드(JSON)     │ ──▶ summary_kr.txt
 │ ICUSTAYS     │ ───────▶ (처방 1건=1행)   │ ④ judge    국내 지침 규칙 판정  │     단계별 n · 요법 상위 · 판정 분포
 │ DIAGNOSES_ICD│  쿼리 3  cultures.csv    │ ⑤ summarize 기관별 집계        │     (이것만 내보냄)
 │ PRESCRIPTIONS│ ───────▶ (검체 1건=1행)   └───────────────────────────┘
 │ MICROBIOLOGY │
 └──────────────┘
```

파일: `kmimic_extract.sql`(쿼리 3개) · `run_extract.py`(쿼리 실행기) · `analyze_kmimic_cohort.py` · `make_cards_min.py` · `aware_table.py` + `aware_2025.csv`(WHO AWaRe 2025 분류) · `atc_to_ingredient.csv` · `test_data/`(합성 3명, 동작 확인용). 국내 지침 판정기 `rule_judge_kr.py` 는 `../guideline/rule_judge/` 에 있다(플랫폼에 올릴 때 이 폴더로 복사).

---

## 1. 확정 조건 (한 표)

| 항목 | 결정 |
|---|---|
| 기관 · 데이터셋 | 기관별 데이터셋(`kmimic-emr-001 … -202`)의 테이블 구조는 같다 → **데이터셋마다 같은 쿼리 3개를 실행**해 기관별 CSV 로 저장 후 이어 붙인다. 본 분석 = **001 003 004 005 006 009**, **202 는 따로**(GSN · 용량 없음, EMAR event_txt 없음, ICD10CM; 카드 단계에서 `--hospitals=202` 로 분리) |
| 월 배치 중복 | 키(hadm_id / subject_id / stay_id / 처방 키)당 **최신 src_batch_id 1행** |
| 분석 단위 | 환자별 **첫 ICU 재실 1회**(stay 간격 ≤ 60분이면 병합)의 입원 1건. 재입실 · 재입원 제외 |
| 성인 | 입원 시 ≥ 18세. `anchor_age` 문자열 파싱: `N years` → N + (입원연도 − anchor_year), `90 years or older` → 90, months/days → 0 |
| 폐렴 | J13, J14, J15x, J16x, J180/181/188/189 (주 · 부상병 전부, 점 없는 코드). **J690 있으면 제외**. 바이러스 · 인플루엔자(J12x, J100, J110) 동반은 `viral_cocode=1` 표시만 |
| 요로감염 | N10x, N12x, N390. **T835x 있으면 제외**. 방광염(N300/N309) 동반은 `cystitis_code=1` 표시만 |
| 둘 다 | 폐렴 · 요로감염 코드가 둘 다 있으면 제외 |
| 시간 0 | t0 = min(edregtime, admittime) = 병원 도착. 모든 `t_*` 는 t0 기준 **시간(h)**. 절대 날짜는 출력하지 않음 |
| 전신 항생제 | `PRESCRIPTIONS.gsn LIKE 'J01%'`(gsn = ATC). gsn 이 비면 약품명 규칙(cef·cillin·penem·vanco·tazo…; 항암 ·항진균 ·외용 제외). 경구 vancomycin(A07AA) · 외용 경로 제외. **시각 = starttime**(EMAR 는 쓰지 않음: 001 · 005 · 009 charttime 이 0093~6280년으로 오염) |
| 배양 | `MICROBIOLOGYEVENTS.charttime` = 채취, `storetime` = 보고. 창 = t0 −365일 ~ 퇴원(과거 분리균 계산용; 짝짓기는 derive 가 함). **선별 검사는 배양이 아님**(직장 VRE/CRE, 비강 MRSA, stool screen, catheter tip, PCR, 항원) → `is_culture=0` |
| 감염 의심 시각 | (파이썬 derive) `culture_first`: 배양 → 72h 안 항생제 ⇒ 배양 시각 / `antibiotic_first`: 항생제 → 24h 안 배양 ⇒ 항생제 시각 / 가장 이른 것. 짝이 없으면 `--abx-only-suspicion` 으로 첫 항생제 시각을 씀(`antibiotic_only`, 민감도 코호트) |
| 지역사회 획득 | 의심 시각 ≤ 48h. 넘으면 원내 감염으로 제외(수만 보고) |
| 초기 요법 | 의심 시각 이후 첫 항생제(`t_first_antibiotic`)부터 **+24h 안에 시작한 성분 집합** |
| 패혈증 라벨 | `sepsis_by_code` = A40x, A41x, R651 (KCD: R652/R653 은 비감염성). SOFA 는 계산하지 않음(MIMIC 은 sepsis3, 두 데이터 라벨을 맞추지 않기로 함) |
| 과거력 | `prior_admission_90d` 는 쿼리 1 이 낸다. `prior_iv_abx_90d` · `prior_mrsa_1y` · `prior_pseudomonas_1y` 는 파이썬 derive 가 antibiotics.csv(이전 입원 행 `hadm_is_cohort=0`, t0 −90일) · cultures.csv(`is_mrsa` · `is_pseudomonas`, t0 −365일)에서 계산한다 |
| 승압제 | PRESCRIPTIONS 의 ATC C01CA03/24/04/07 · H01BA01(norepinephrine · epinephrine · dopamine · dobutamine · vasopressin) 또는 약품명. 쿼리 2 가 `is_vasopressor=1` 행으로 내보내고 derive 가 `vasopressor`, `t_vaso_start` 를 만든다 |
| 기계환기 | 추출하지 않음(기관별 ITEMID 가 다름). 카드에서는 '모름' 이 되므로 중증도 판정은 `--icu-severe`(ICU 입실 = 중증) 로 한다 |
| 하지 않는 것 | SOFA, 활력징후 · 검사값, 용량 검사, EMAR 투여 시각 |

---

## 2. 쓰는 테이블 · 컬럼

| 테이블 | 쓰는 컬럼 | 주의 |
|---|---|---|
| ADMISSIONS | subject_id, hadm_id, admittime, dischtime, deathtime, hospital_expire_flag, edregtime, admission_type, admission_location, src_hospital_id, src_batch_id | ID 는 전부 VARCHAR. 날짜는 환자별 이동(3000년대까지) → epoch 변환 금지, `date_diff` 만 |
| PATIENTS | subject_id, sex, anchor_age, anchor_year, anchor_year_group | anchor_age 는 문자열 4종 |
| ICUSTAYS | subject_id, hadm_id, stay_id, intime, outtime, first_careunit, op_flag | 전실 단위 stay → 병합 필요. 001 stay_id 에 `00110000.0` 같은 오염값 |
| DIAGNOSES_ICD | hadm_id, icd_code (seq_num 은 안 씀) | 점 없는 코드, KCD 버전 혼재(202 만 ICD10CM). J16 은 데이터에 없음 |
| PRESCRIPTIONS | hadm_id, pharmacy_id, starttime, stoptime, drug, gsn, route, dose_val_rx, dose_unit_rx, doses_per_24_hrs | gsn = ATC(202 는 0%). drug 는 상품명 중심 `Tazoperan 4.5g inj(Piperacillin/Tazobactam)` |
| MICROBIOLOGYEVENTS | subject_id, micro_specimen_id, chartdate, charttime, storetime, spec_type_desc, test_name, org_name, ab_name, interpretation | 일부 데이터셋 정책상 `chartdate IS NOT NULL` 조건 필요. 검체명 한글 · 영문 혼용 |

---

## 3. 실행 순서

### ① SQL → CSV 3개  (`kmimic_extract.sql`)
`run_extract.py` 의 `run_sql()` 한 함수만 SQL 실행 환경에 맞게 채우면 데이터셋마다 쿼리 3개를 실행해 CSV 로 바로 저장한다(이미 있는 파일은 건너뜀). 수동으로 할 때는 데이터셋(= 기관) 하나를 열고 쿼리 1 · 2 · 3 을 각각 실행해 **기관별 파일**로 저장한다. 세 쿼리는 같은 공통 블록(B1~B6)으로 시작하므로 각각 단독 실행된다. 테이블 이름 앞에 데이터셋 접두어가 필요한 환경이면 `ADMISSIONS` → `"kmimic-emr-003".ADMISSIONS` 처럼 6개 테이블명만 바꾼다.

| 쿼리 | 저장 파일 | 한 행 | 핵심 컬럼 |
|---|---|---|---|
| 1 | `DATA/raw/cohort_003.csv` … | 입원 1건 | hashed_id, hospital, group, age, sex, anchor_year_group, admission_type, admission_location, first_icu_type, op_flag, ed_visit, t_ed, t_admit, t_icu_in, t_icu_out, t_disch, icu_los_d, hosp_los_d, death_inhosp, t_death, viral_cocode, cystitis_code, sepsis_by_code, 기저질환 11개, prior_admission_90d, **hadm_id, subject_id, stay_id** |
| 2 | `DATA/raw/antibiotics_003.csv` … | 처방 1건 (코호트 입원 + t0 −90일 내 이전 입원, 승압제 포함) | hashed_id, hospital, hadm_is_cohort(0 = 이전 입원 행), is_vasopressor, drug_raw, atc, route, dose, dose_unit, doses_per_24h, t_start, t_stop, source |
| 3 | `DATA/raw/cultures_003.csv` … | 검체 × 균 1건 (t0 −365일 ~ 퇴원) | hashed_id, hospital, micro_specimen_id, spec_type, test_name, is_culture, t_collect, t_result, organism, is_mrsa, is_pseudomonas |

기관별 파일을 이어 붙이고(헤더 한 번) `cohort.csv` 의 마지막 세 컬럼(hadm_id, subject_id, stay_id)을 `id_map.csv` 로 떼어 낸다:
```bash
python3 -c "
import csv, glob
for n in ('cohort', 'antibiotics', 'cultures'):
    rows = [r for f in sorted(glob.glob(f'DATA/raw/{n}_*.csv')) for r in csv.DictReader(open(f, encoding='utf-8-sig'))]
    w = csv.DictWriter(open(f'DATA/{n}.csv', 'w', newline=''), list(rows[0].keys())); w.writeheader(); w.writerows(rows); print(n, len(rows))
r = list(csv.DictReader(open('DATA/cohort.csv', encoding='utf-8-sig'))); k = ['hashed_id', 'hadm_id', 'subject_id', 'stay_id']
w = csv.DictWriter(open('DATA/id_map.csv', 'w', newline=''), k); w.writeheader(); [w.writerow({x: d[x] for x in k}) for d in r]
f = [c for c in r[0] if c not in k[1:]]; w = csv.DictWriter(open('DATA/cohort.csv', 'w', newline=''), f, extrasaction='ignore'); w.writeheader(); w.writerows(r)"
```
- hashed_id 는 기관 + hadm_id 로 만들어 기관 간 충돌이 없다.
- 방언이 다르면 파일 머리의 치환표(date_diff · MIN_BY · regexp_* · md5 · `"group"`)만 손본다.

### ② 의심 시각 · 초기 요법 (derive)
```bash
python3 analyze_kmimic_cohort.py derive --cohort DATA/cohort.csv --abx DATA/antibiotics.csv --cultures DATA/cultures.csv --out DATA/cohort_derived.csv
```
출력: `cohort_derived.csv`(+ t_infection_suspected, suspicion_rule, community_acquired, t_first_antibiotic, initial_regimen, n_initial_antibiotics, has_antibiotic, has_culture, 그리고 antibiotics · cultures 에서 계산한 prior_iv_abx_90d, prior_mrsa_1y, prior_pseudomonas_1y, vasopressor, t_vaso_start) 와 화면에 **기관별 단계 n 표 · 집단 요약**(이것이 n수 표). 이전 입원 행과 승압제 행은 요법 · 짝짓기에서 자동으로 빠진다. 성분명은 같은 폴더의 `atc_to_ingredient.csv` 로 붙는다.

### ③ 사례 카드
```bash
python3 make_cards_min.py DATA DATA/cards_main.jsonl atc_to_ingredient.csv --abx-only-suspicion --cohort=DATA/cohort_derived.csv
python3 make_cards_min.py DATA DATA/cards_202.jsonl  atc_to_ingredient.csv --abx-only-suspicion --cohort=DATA/cohort_derived.csv --hospitals=202
```
화면의 `미매핑: {...}` 에 ATC 코드가 나오면 `atc_to_ingredient.csv` 에 한 줄 추가하고 다시 돌린다. 기관별 보고가 필요하면 `--hospitals=003` 처럼 하나씩.

### ④ 국내 지침 규칙 판정  (`../guideline/rule_judge/rule_judge_kr.py` 를 이 폴더로 복사)
```bash
python3 rule_judge_kr.py --icu-severe --class-equiv DATA/cards_main.jsonl DATA/verdicts_main.jsonl > DATA/summary_kr_main.txt
python3 rule_judge_kr.py --icu-severe --class-equiv DATA/cards_202.jsonl  DATA/verdicts_202.jsonl  > DATA/summary_kr_202.txt
```
민감도 두 가지를 같이 보고한다: ③ 에서 `--abx-only-suspicion` 을 빼면 "배양 짝이 성립한 환자만", ④ 에서 `--icu-severe` 를 빼면 "중증도를 카드 값으로만 판정(strict)".

### ⑤ 집계 (단계별 n · 요법 상위 · 계열 비율)
```bash
python3 analyze_kmimic_cohort.py summarize --cohort DATA/cohort_derived.csv --abx DATA/antibiotics.csv > DATA/summary_cohort.txt
```

### ⑥ WHO AWaRe 비율 (두 데이터 공통 잣대)
```bash
python3 aware_table.py DATA/cards_main.jsonl --by=hospital > DATA/summary_aware_main.txt
python3 aware_table.py DATA/cards_202.jsonl  --by=hospital > DATA/summary_aware_202.txt
```
성분 건수 기준 Access / Watch / Reserve % 와 환자 기준(Access 만 · Watch 포함 · Reserve 포함)을 집단 × 기관으로 낸다. 분류는 `aware_2025.csv`(WHO AWaRe 2025; fosfomycin · minocycline 은 경구/정맥 구분). "분류 없음" 이 나오면 그 성분을 csv 에 한 줄 추가.

### 먼저 동작 확인 (실데이터 전에)
```bash
python3 analyze_kmimic_cohort.py derive --cohort test_data/cohort.csv --abx test_data/antibiotics.csv --cultures test_data/cultures.csv --out test_data/cohort_derived.csv
python3 make_cards_min.py test_data test_data/cards.jsonl atc_to_ingredient.csv --abx-only-suspicion --cohort=test_data/cohort_derived.csv
python3 rule_judge_kr.py --icu-severe --class-equiv test_data/cards.jsonl test_data/verdicts.jsonl
```

### 플랫폼 밖으로 내보내는 것
- 집계 텍스트만: `summary_kr_*.txt`, `summary_cohort.txt`, `summary_aware_*.txt`, 기관별 판정 분포(verdict 별 n), 미매핑 목록.
- 환자 단위 파일(cohort · antibiotics · cultures CSV, id_map, cards · verdicts jsonl)은 내보내지 않는다.

---

## 4. 뽑자마자 볼 QC

| 볼 것 | 정상 범위 · 판단 |
|---|---|
| 의심 시각 성립률 (derive 표) | 처방 시각 · 선별 제외 후 60~90% 면 정상. 20%대 기관은 cultures 추출(날짜 조건 · subject 조인) 확인 |
| 48h 이내 비율 | 의심 시각 있는 환자의 50~70% |
| `미매핑` (카드 단계) | 상위 코드부터 `atc_to_ingredient.csv` 에 추가. 202 는 약품명 → `make_cards_min.py` 의 NORMALIZE 에 상품명 추가 |
| route 고유값 | IV / PO / IM 표기 확인(한글 '정맥' 등 섞이면 그대로 두어도 판정에는 영향 없음) |
| vasopressor 비율 | 기관별 20~50%. 0% 또는 90% 면 ATC · 약품명 매핑 오류 |
| t_icu_in < 0 비율 | ICU 입실이 병원 도착보다 빠른 행. 수 % 이상이면 edregtime/admittime 의미 재확인 |
| hashed_id 중복 | 0 이어야 함(기관 + hadm_id 로 해시) |
| is_culture = 0 비율 | 10~30%. 0% 면 선별 검체명이 다른 표기(목록 추가), 60% 이상이면 정규식이 과하게 잡음 |
| age | 18~90, '90 years or older' 가 90 으로 |

---

## 5. K-MIMIC 데이터 특성 (코드가 전제하는 것)

1. 날짜가 환자별로 이동돼 3000년대까지 있음 → 절대 시각 · epoch 변환 금지. 상대 시간만.
2. 월 배치 중복(src_batch_id) → DISTINCT 가 아니라 **키당 최신 배치 1행**.
3. ID 전부 VARCHAR, 기관마다 자릿수 다름. 001 stay_id 오염값 있음. subject_id 는 기관 안에서만 유일하다고 보고 **항상 src_hospital_id 와 함께** 조인.
4. anchor_age 문자열(years / months / days / 90 years or older).
5. 진단코드 점 없음, KCD 버전 혼재, 하위코드 위주 → 접두사 매칭. J16 은 없음. seq_num=1 이 2개이거나 없는 입원이 소수 있음(안 씀).
6. PRESCRIPTIONS.gsn 이 ATC(202 는 전부 NULL). drug 는 상품명(괄호 안 성분명은 일부만).
7. EMAR charttime 이 001 · 005 · 009 에서 0093~6280년 → 투여 시각 사용 금지. 202 는 event_txt 없음.
8. MICROBIOLOGYEVENTS: charttime = 채취, storetime = 보고(평균 71~168h 지연). 검체명 한글 · 영문 혼용, 기관마다 다름. 선별 검체가 많음(직장 VRE/CRE, 비강 MRSA, stool screen).
9. SOFA 점수 항목 없음. PaO2 · 소변량 · lactate 는 기관별 ITEMID 와 단위가 달라 SOFA 를 계산하지 않는다. 승압제는 기관별 이벤트 테이블 대신 PRESCRIPTIONS 의 ATC 로 판정한다.
10. 202: ICD10CM, gsn · 용량 없음, EDSTAY 1행, 승압제 항목 미확인 → 별도 코호트로 보고.
11. ED 처방이 PRESCRIPTIONS 에 hadm_id 로 연결되는지 미확인 → t_first_antibiotic 중앙값이 MIMIC(8~15h) 보다 많이 크면 의심.
