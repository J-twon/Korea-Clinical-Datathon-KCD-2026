-- mimic-code 공식 Sepsis-3 표를 BigQuery에서 뽑는 쿼리
-- 어디서: https://console.cloud.google.com/bigquery  (physionet-data 프로젝트를 "Star a project by name"으로 추가한 뒤)
-- 데이터셋 이름: 사이드바에 mimiciv_3_1_derived 가 있으면 그것(우리 추출은 v3.1), 없으면 mimiciv_derived (v2.2 기준이라 stay_id 일부가 빠짐).
-- 결과 저장: 쿼리 결과 → Save results → CSV (local file). 10 MB 제한이 있어 1)·2)는 되고 3)은 Google Drive로 저장.
-- 파일 이름을 아래처럼 바꿔 data/ 폴더에 두면 노트북 3-2 셀이 자동으로 결합한다.
-- 비용: 표가 작아(수 MB) 사실상 0. 프로젝트에 결제 계정만 연결되어 있으면 된다.

-- 1) Sepsis-3 공식 표 → data/sepsis3_mimic_code.csv
--    한 ICU stay = 1행. "의심 감염 + SOFA>=2" 가 있는 stay만 들어 있으므로 표에 없는 stay = sepsis3 아님.
SELECT subject_id, stay_id, antibiotic_time, culture_time, suspected_infection_time,
       sofa_time, sofa_score, respiration, coagulation, liver, cardiovascular, cns, renal, sepsis3
FROM `physionet-data.mimiciv_3_1_derived.sepsis3`;

-- 2) (선택) 첫 24시간 SOFA → data/first_day_sofa.csv   (ICU 입실 기준 중증도 보조 지표)
SELECT subject_id, stay_id, sofa, respiration, coagulation, liver, cardiovascular, cns, renal
FROM `physionet-data.mimiciv_3_1_derived.first_day_sofa`;

-- 3) (선택) 감염 의심 행 전체 → data/suspicion_of_infection.csv   (우리 t_infection_suspected 와 비교용, 행이 많음)
SELECT subject_id, stay_id, hadm_id, ab_id, antibiotic, antibiotic_time, culture_time,
       suspected_infection, suspected_infection_time, specimen, positive_culture
FROM `physionet-data.mimiciv_3_1_derived.suspicion_of_infection`
WHERE stay_id IS NOT NULL;
