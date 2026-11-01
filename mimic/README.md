# MIMIC-IV 폐렴 · 요로감염 초기 항생제 코호트 패키지

Korea Clinical Datathon 2026 · 항생제 가이드라인 준수 연구의 MIMIC-IV 쪽 데이터 · 코드 · 결과.
K-MIMIC은 플랫폼 안에서 같은 컬럼 구조로 뽑아 같은 코드로 돌린다.

## 폴더
- `code/extract_mimic_cohort.py` — MIMIC-IV v3.1 csv.gz → `data/*.csv` (표준 라이브러리만, 전체 약 7분. `--skip-events`면 3분).
- `code/build_notebook.py` — 노트북을 만들고 실행해 출력까지 심는다 (jupyter 없이 동작).
- `code/make_final_cards.py` — 사례 카드 생성: `results/final/cards_all.jsonl`(최종 코호트 전원) · `cards_eval20.jsonl`(평가 표본) · `labels.csv` · `card_schema.md`. 값은 보고 시각(storetime) ≤ 첫 항생제 처방 시각인 것만 넣는다.
- `docs/bigquery_sepsis3.sql` — mimic-code 공식 Sepsis-3 표를 BigQuery에서 뽑는 쿼리. 결과를 `data/sepsis3_mimic_code.csv`로 두면 노트북이 결합한다.
- `notebooks/mimic_pna_uti.ipynb` — 데이터 확인 → 코호트 → 패혈증 분류 → 집단 요약 → 타이밍 → 매핑 → 사례 카드 → 결과 저장.
- `data/` — 추출 CSV (아래 정의). **환자 단위 자료: PhysioNet 자격자만. 외부 공유 · 업로드 금지.**
- `results/` — 집계표(`summary.md`, `funnel.csv`, `group_summary.json`), 평가 표본(`eval_sample.csv`, `cards/*.json`), `cohort_with_sofa.csv`, 추출 로그.

## 시간 기준
`t0 = 병원 도착 = min(응급실 등록 edregtime, 입원 admittime)`. 모든 `t_*`는 t0 기준 상대 시간(시간 단위). 절대 날짜 없음. ID는 해시(`id_map.csv`로 복원).

## 코호트 정의
1. 환자별 첫 ICU 입실 1회(연속 재실 1 stay), 그 입원 1건. 재입실 · 재입원 제외. 2. 성인 ≥18세.
3. 폐렴: ICD-10 J13 · J14 · J15 · J16 · J18.0/.1/.8/.9, ICD-9 481 · 482 · 483 · 485 · 486. 흡인성(J69.0/507.0) · VAP(J95.851/997.31) 제외. 바이러스 · 인플루엔자만은 미포함(동반 시 `viral_cocode=1`).
4. 요로감염: N10 · N12 · N39.0, 590.1 · 590.80 · 590.9 · 599.0. 카테터 관련(T83.51/996.64) 제외. 방광염만 미포함.
5. 폐렴 · 요로감염 코드 둘 다 → 제외.
6. 감염 의심 시각 `t_infection_suspected`: `culture_first` 배양 → 72h 안 전신 항생제 ⇒ 배양 시각 / `antibiotic_first` 항생제 → 24h 안 배양 ⇒ 항생제 시각 / 가장 이른 것.
7. 지역사회 획득 `community_acquired` = 의심 시각 ≤ 48h. 8. 초기 요법 = `t_first_antibiotic`(의심 시각 이후 첫 항생제)부터 24h 안에 시작된 전신 항생제 성분 집합.
9. 패혈증 라벨 셋: `sepsis_by_code`(ICD) · `sepsis_by_sofa`(간이 SOFA ≥ 2) · `sepsis3`(mimic-code 공식 표, MIMIC 주 라벨). `sofa_window_covers_icu = 0`(약 18%)은 SOFA 창이 ICU 재실과 안 겹쳐 검사값만으로 점수가 난 환자 — 빼지 않고 플래그로 보고.

## data/ 컬럼
- `cohort.csv`: hashed_id, hospital, group(pneumonia/uti), age, sex, anchor_year_group, icd_version, ed_visit, admission_type, admission_location, first_icu_type, t_ed, t_admit, t_icu_in, t_icu_out, t_disch, icu_los_d, hosp_los_d, death_inhosp, t_death, has_antibiotic, has_culture, t_infection_suspected, suspicion_rule(culture_first/antibiotic_first), community_acquired, t_first_antibiotic, initial_regimen, n_initial_antibiotics, blood_culture_before_antibiotic, hours_suspicion_to_icu(양수 = ICU 입실이 나중), suspicion_before_icu, sofa_window_covers_icu, sepsis_by_code, septic_shock_by_code, viral_cocode, cystitis_code, dm, ckd, copd, bronchiectasis, hf, liver, cancer, immuno, pregnancy, uro_obstruction, alcohol, prior_admission_90d, prior_iv_abx_90d, prior_mrsa_1y, prior_pseudomonas_1y, mech_vent, t_vent_start, vasopressor, t_vaso_start, weight_kg
- `antibiotics.csv`: hashed_id, drug_raw, ingredient, abx_class, aware, route, dose, dose_unit, doses_per_24h, t_start, t_stop, t_first_administration(EMAR, 2016+), in_initial_regimen, source
- `cultures.csv`: hashed_id, spec_type, test_name, is_culture, t_collect, t_result, organism, antibiotic, interpretation (창: t0 −48h ~ 퇴원)
- `vitals_labs.csv`: hashed_id, item, itemid, valuenum, value, unit, t_chart, t_store, source_table (anchor = 감염 의심 시각(없으면 t0); 검사 · GCS · FiO2 · 소변량 −48h~+72h, 활력징후 −48h~+24h, 체중은 전체)
- `vasopressors.csv`, `ventilation.csv`, `id_map.csv`(hashed_id, subject_id, hadm_id, stay_id, t0_abs), `drug_raw_counts.csv`, `item_map.csv`, `funnel.json`
- (선택) `sepsis3_mimic_code.csv` — BigQuery에서 뽑은 공식 Sepsis-3 표 (`docs/bigquery_sepsis3.sql`)

## 전신 항생제 판정
약품명 정규식으로 성분 55종. 안약 · 귀약 · 국소 · 흡입 · 카테터 lock · 경구 vancomycin · neomycin 제외. 항진균 · 항바이러스 · 항결핵 미포함. 계열(anti_MRSA · antipseudomonal …)과 WHO AWaRe(2023 목록, 2025로 검수 필요)는 `antibiotics.csv`에 붙어 있다.

## 다시 돌리기
```bash
cd code && python3 extract_mimic_cohort.py --mimic /path/to/mimiciv/3.1 --out ../data && python3 build_notebook.py && python3 make_final_cards.py
```
