-- ============================================================================================================
-- K-MIMIC 추출 SQL — 폐렴·요로감염 성인 첫 ICU 입원 코호트 (Korea Clinical Datathon 2026)
-- 플랫폼의 K-MIMIC 은 기관별 데이터셋(kmimic-emr-001 … kmimic-emr-202)으로 나뉘어 있고 테이블 구조는 같다.
--   → 데이터셋 하나를 열고 아래 쿼리 3개를 그대로 실행, 결과를 기관별 CSV 로 저장한 뒤 이어 붙인다(KMIMIC_EXTRACTION.md ①).
--   큰 테이블은 기관당 두 번만 읽는다: 쿼리 1 = 작은 테이블만(수 초), 쿼리 2 = PRESCRIPTIONS 1회, 쿼리 3 = MICROBIOLOGYEVENTS 1회. 과거력 · 승압제 플래그는 파이썬(derive)이 그 결과로 계산한다.
-- 쿼리 3개는 각각 단독으로 실행된다(앞부분 공통 블록 [B1~B6] 이 세 번 반복됨):
--   쿼리 1 → cohort_<기관>.csv      쿼리 2 → antibiotics_<기관>.csv      쿼리 3 → cultures_<기관>.csv
-- 그다음은 파이썬: analyze_kmimic_cohort.py derive (의심 시각·초기 요법) → make_cards_min.py → rule_judge_kr.py.
--
-- 모든 시각은 t0(병원 도착 = min(edregtime, admittime)) 기준 상대 시간(시간 단위). 절대 날짜는 출력하지 않는다.
-- src_hospital_id IN (...) 은 안전장치일 뿐이다(데이터셋 = 기관 하나). 테이블 이름 앞에 데이터셋 접두어가 필요한 환경이면 ADMISSIONS → "kmimic-emr-003".ADMISSIONS 식으로 6개 테이블명만 바꾼다.
--
-- 방언 메모 (Trino/Presto 표기로 작성). 다른 엔진이면:
--   date_diff('minute', a, b)   → Spark: (unix_timestamp(b) - unix_timestamp(a)) / 60  ※ 3000년대 날짜라 epoch 변환은 피하고 timestampdiff(MINUTE, a, b) 가 있으면 그것
--   MIN_BY(x, t)                → Spark 동일 / PostgreSQL: (array_agg(x ORDER BY t))[1]
--   regexp_extract(s, p, 1)     → PostgreSQL: substring(s from p)
--   regexp_like(s, p)           → Spark: s RLIKE p / PostgreSQL: s ~ p
--   to_hex(md5(to_utf8(s)))     → Spark·PostgreSQL: md5(s)
--   "group" (예약어 별칭)        → 안 되면 cohort_group 으로 바꾸고 analyze 의 COL["group"] 도 같이 바꾼다
--   timestamp 컬럼이 VARCHAR 로 올라와 있으면 CAST(col AS timestamp) 를 먼저 씌운다
-- ============================================================================================================

-- ########## 쿼리 1 / 3 : cohort.csv ##########
WITH
-- [B1] 원천 중복 제거: 월 배치(src_batch_id)마다 같은 키가 다시 실리므로 키당 최신 배치 1행만 남긴다
adm AS (SELECT * FROM (
          SELECT subject_id, hadm_id, admittime, dischtime, deathtime, hospital_expire_flag, edregtime, admission_type, admission_location, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY src_batch_id DESC) AS rn
          FROM ADMISSIONS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202')) x WHERE rn = 1),
pat AS (SELECT * FROM (
          SELECT subject_id, sex, anchor_age, anchor_year, anchor_year_group, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, subject_id ORDER BY src_batch_id DESC) AS rn
          FROM PATIENTS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202')) x WHERE rn = 1),
icu AS (SELECT * FROM (
          SELECT subject_id, hadm_id, stay_id, intime, outtime, first_careunit, op_flag, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, stay_id ORDER BY src_batch_id DESC) AS rn
          FROM ICUSTAYS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202') AND intime IS NOT NULL) x WHERE rn = 1),
-- [B2] 전실 단위 stay → 연속 재실(episode) 1회로 병합: 이전 outtime 과 다음 intime 간격 ≤ 60분이면 같은 재실
icu_ord AS (SELECT i.*, LAG(outtime) OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY intime) AS prev_out FROM icu i),
icu_ep AS (SELECT i.*, SUM(CASE WHEN prev_out IS NULL OR date_diff('minute', prev_out, intime) > 60 THEN 1 ELSE 0 END)
                          OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY intime ROWS UNBOUNDED PRECEDING) AS ep FROM icu_ord i),
episodes AS (SELECT src_hospital_id, subject_id, hadm_id, ep, MIN(stay_id) AS stay_id, MIN(intime) AS icu_in, MAX(outtime) AS icu_out,
                    MIN_BY(first_careunit, intime) AS first_careunit,
                    MAX(CASE WHEN CAST(op_flag AS varchar) IN ('1', 'Y', 'y', 'true', 'TRUE') THEN 1 ELSE 0 END) AS op_flag
             FROM icu_ep GROUP BY src_hospital_id, subject_id, hadm_id, ep),
-- [B3] 환자별 첫 ICU 재실 1개 → 그 입원 1건 (재입실·재입원 제외)
first_ep AS (SELECT * FROM (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY src_hospital_id, subject_id ORDER BY icu_in) AS rn FROM episodes e) x WHERE rn = 1),
base AS (SELECT f.src_hospital_id AS hospital, f.subject_id, f.hadm_id, f.stay_id, f.icu_in, f.icu_out, f.first_careunit, f.op_flag,
                a.admittime, a.dischtime, a.deathtime, a.hospital_expire_flag, a.edregtime, a.admission_type, a.admission_location,
                CASE WHEN a.edregtime IS NOT NULL AND a.edregtime < a.admittime THEN a.edregtime ELSE a.admittime END AS t0,   -- 시간 0 = 병원 도착
                p.sex, p.anchor_age, p.anchor_year, p.anchor_year_group
         FROM first_ep f
         JOIN adm a ON a.src_hospital_id = f.src_hospital_id AND a.hadm_id = f.hadm_id
         JOIN pat p ON p.src_hospital_id = f.src_hospital_id AND p.subject_id = f.subject_id),
-- [B4] 입원 시 나이: 'N years' → N + (입원연도 − anchor_year); '90 years or older' → 90; 'N months'/'N days' → 0
aged AS (SELECT b.*, CASE WHEN anchor_age LIKE '%or older%' THEN 90
                          WHEN anchor_age LIKE '%year%' THEN CAST(regexp_extract(anchor_age, '^([0-9]+)', 1) AS integer) + (year(admittime) - CAST(anchor_year AS integer))
                          ELSE 0 END AS age FROM base b),
adult AS (SELECT * FROM aged WHERE age >= 18),
-- [B5] 진단 플래그 (DIAGNOSES_ICD 주·부상병 전부, 점 없는 코드, 접두사 매칭)
dx AS (SELECT DISTINCT d.src_hospital_id, d.hadm_id, d.icd_code FROM DIAGNOSES_ICD d JOIN adult s ON s.hospital = d.src_hospital_id AND s.hadm_id = d.hadm_id),
flags AS (SELECT src_hospital_id, hadm_id,
      MAX(CASE WHEN (icd_code IN ('J13', 'J14', 'J180', 'J181', 'J188', 'J189') OR icd_code LIKE 'J15%' OR icd_code LIKE 'J16%' OR icd_code LIKE 'J180%' OR icd_code LIKE 'J181%' OR icd_code LIKE 'J188%' OR icd_code LIKE 'J189%') THEN 1 ELSE 0 END) AS pna,   -- 폐렴 포함 코드
      MAX(CASE WHEN (icd_code LIKE 'J690%') THEN 1 ELSE 0 END) AS pna_asp,   -- 흡인성 → 제외
      MAX(CASE WHEN (icd_code LIKE 'J12%' OR icd_code LIKE 'J100%' OR icd_code LIKE 'J110%') THEN 1 ELSE 0 END) AS viral_cocode,   -- 바이러스·인플루엔자 폐렴 동반 (표시만)
      MAX(CASE WHEN (icd_code IN ('N10', 'N12') OR icd_code LIKE 'N10%' OR icd_code LIKE 'N12%' OR icd_code LIKE 'N390%') THEN 1 ELSE 0 END) AS uti,   -- 요로감염 포함 코드
      MAX(CASE WHEN (icd_code LIKE 'N300%' OR icd_code LIKE 'N309%') THEN 1 ELSE 0 END) AS cystitis_code,   -- 방광염 코드 동반 (표시만)
      MAX(CASE WHEN (icd_code LIKE 'T835%') THEN 1 ELSE 0 END) AS cauti,   -- 카테터 관련 → 제외
      MAX(CASE WHEN (icd_code LIKE 'A40%' OR icd_code LIKE 'A41%' OR icd_code LIKE 'R651%') THEN 1 ELSE 0 END) AS sepsis_by_code,   -- 패혈증 코드 (KCD: R65.1 만. R65.2/3 은 비감염성)
      MAX(CASE WHEN (icd_code LIKE 'E10%' OR icd_code LIKE 'E11%' OR icd_code LIKE 'E13%' OR icd_code LIKE 'E14%') THEN 1 ELSE 0 END) AS dm,
      MAX(CASE WHEN (icd_code LIKE 'N18%') THEN 1 ELSE 0 END) AS ckd,
      MAX(CASE WHEN (icd_code LIKE 'J44%') THEN 1 ELSE 0 END) AS copd,
      MAX(CASE WHEN (icd_code LIKE 'J47%') THEN 1 ELSE 0 END) AS bronchiectasis,
      MAX(CASE WHEN (icd_code LIKE 'I50%') THEN 1 ELSE 0 END) AS hf,
      MAX(CASE WHEN (icd_code LIKE 'K70%' OR icd_code LIKE 'K71%' OR icd_code LIKE 'K72%' OR icd_code LIKE 'K73%' OR icd_code LIKE 'K74%' OR icd_code LIKE 'K75%' OR icd_code LIKE 'K76%' OR icd_code LIKE 'K77%') THEN 1 ELSE 0 END) AS liver,   -- K70–K77
      MAX(CASE WHEN (icd_code LIKE 'C%') THEN 1 ELSE 0 END) AS cancer,
      MAX(CASE WHEN (icd_code LIKE 'D80%' OR icd_code LIKE 'D81%' OR icd_code LIKE 'D82%' OR icd_code LIKE 'D83%' OR icd_code LIKE 'D84%' OR icd_code LIKE 'D89%' OR icd_code LIKE 'B20%' OR icd_code LIKE 'B21%' OR icd_code LIKE 'B22%' OR icd_code LIKE 'B23%' OR icd_code LIKE 'B24%' OR icd_code LIKE 'Z94%') THEN 1 ELSE 0 END) AS immuno,   -- 면역결핍·HIV·이식
      MAX(CASE WHEN (icd_code LIKE 'O%' OR icd_code LIKE 'Z33%' OR icd_code LIKE 'Z34%') THEN 1 ELSE 0 END) AS pregnancy,
      MAX(CASE WHEN (icd_code LIKE 'N13%' OR icd_code LIKE 'N20%' OR icd_code LIKE 'N21%' OR icd_code LIKE 'N40%') THEN 1 ELSE 0 END) AS uro_obstruction,   -- 요로폐색·결석·전립선비대
      MAX(CASE WHEN (icd_code LIKE 'F10%') THEN 1 ELSE 0 END) AS alcohol
          FROM dx GROUP BY src_hospital_id, hadm_id),
-- [B6] 질환군: 폐렴(흡인성 제외) / 요로감염(카테터 관련 제외). 둘 다면 제외
sel AS (SELECT s.*, f.pna, f.pna_asp, f.viral_cocode, f.uti, f.cystitis_code, f.cauti, f.sepsis_by_code, f.dm, f.ckd, f.copd, f.bronchiectasis, f.hf, f.liver, f.cancer, f.immuno, f.pregnancy, f.uro_obstruction, f.alcohol,
               CASE WHEN f.pna = 1 AND f.pna_asp = 0 AND NOT (f.uti = 1 AND f.cauti = 0) THEN 'pneumonia'
                    WHEN f.uti = 1 AND f.cauti = 0 AND NOT (f.pna = 1 AND f.pna_asp = 0) THEN 'uti' END AS grp
        FROM adult s JOIN flags f ON f.src_hospital_id = s.hospital AND f.hadm_id = s.hadm_id),
cohort0 AS (SELECT * FROM sel WHERE grp IS NOT NULL),
-- [C1] 90일 내 이전 입원 (ADMISSIONS 만 사용). 정맥 항생제 · MRSA/녹농균 분리 · 승압제 플래그는 쿼리 2 · 3 의 결과로 파이썬(derive)이 계산한다 → 이 쿼리는 큰 테이블을 읽지 않는다
prior_adm AS (SELECT DISTINCT c.hospital, c.hadm_id FROM cohort0 c
              JOIN adm a ON a.src_hospital_id = c.hospital AND a.subject_id = c.subject_id AND a.hadm_id <> c.hadm_id
              WHERE a.dischtime < c.t0 AND date_diff('day', a.dischtime, c.t0) <= 90)
-- ===== 출력 1: cohort.csv (한 행 = 입원 1건). 마지막 3개 컬럼(hadm_id, subject_id, stay_id)은 id_map.csv 로 떼어 두고 공유본에서는 지운다
SELECT to_hex(md5(to_utf8(c.hospital || '|' || c.hadm_id))) AS hashed_id, c.hospital, c.grp AS "group",
       c.age, c.sex, c.anchor_year_group, c.admission_type, c.admission_location, c.first_careunit AS first_icu_type, c.op_flag,
       CASE WHEN c.edregtime IS NOT NULL THEN 1 ELSE 0 END AS ed_visit,
       date_diff('minute', c.t0, c.edregtime) / 60.0 AS t_ed,
       date_diff('minute', c.t0, c.admittime) / 60.0 AS t_admit,
       date_diff('minute', c.t0, c.icu_in)    / 60.0 AS t_icu_in,
       date_diff('minute', c.t0, c.icu_out)   / 60.0 AS t_icu_out,
       date_diff('minute', c.t0, c.dischtime) / 60.0 AS t_disch,
       date_diff('minute', c.icu_in, c.icu_out)      / 1440.0 AS icu_los_d,
       date_diff('minute', c.admittime, c.dischtime) / 1440.0 AS hosp_los_d,
       CAST(c.hospital_expire_flag AS integer) AS death_inhosp,
       date_diff('minute', c.t0, c.deathtime) / 60.0 AS t_death,
       c.viral_cocode, c.cystitis_code, c.sepsis_by_code, c.dm, c.ckd, c.copd, c.bronchiectasis, c.hf, c.liver, c.cancer, c.immuno, c.pregnancy, c.uro_obstruction, c.alcohol,
       CASE WHEN pa.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS prior_admission_90d,
       c.hadm_id, c.subject_id, c.stay_id
FROM cohort0 c
LEFT JOIN prior_adm pa ON pa.hospital = c.hospital AND pa.hadm_id = c.hadm_id;

-- ########## 쿼리 2 / 3 : antibiotics.csv ##########
WITH
-- [B1] 원천 중복 제거: 월 배치(src_batch_id)마다 같은 키가 다시 실리므로 키당 최신 배치 1행만 남긴다
adm AS (SELECT * FROM (
          SELECT subject_id, hadm_id, admittime, dischtime, deathtime, hospital_expire_flag, edregtime, admission_type, admission_location, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY src_batch_id DESC) AS rn
          FROM ADMISSIONS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202')) x WHERE rn = 1),
pat AS (SELECT * FROM (
          SELECT subject_id, sex, anchor_age, anchor_year, anchor_year_group, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, subject_id ORDER BY src_batch_id DESC) AS rn
          FROM PATIENTS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202')) x WHERE rn = 1),
icu AS (SELECT * FROM (
          SELECT subject_id, hadm_id, stay_id, intime, outtime, first_careunit, op_flag, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, stay_id ORDER BY src_batch_id DESC) AS rn
          FROM ICUSTAYS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202') AND intime IS NOT NULL) x WHERE rn = 1),
-- [B2] 전실 단위 stay → 연속 재실(episode) 1회로 병합: 이전 outtime 과 다음 intime 간격 ≤ 60분이면 같은 재실
icu_ord AS (SELECT i.*, LAG(outtime) OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY intime) AS prev_out FROM icu i),
icu_ep AS (SELECT i.*, SUM(CASE WHEN prev_out IS NULL OR date_diff('minute', prev_out, intime) > 60 THEN 1 ELSE 0 END)
                          OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY intime ROWS UNBOUNDED PRECEDING) AS ep FROM icu_ord i),
episodes AS (SELECT src_hospital_id, subject_id, hadm_id, ep, MIN(stay_id) AS stay_id, MIN(intime) AS icu_in, MAX(outtime) AS icu_out,
                    MIN_BY(first_careunit, intime) AS first_careunit,
                    MAX(CASE WHEN CAST(op_flag AS varchar) IN ('1', 'Y', 'y', 'true', 'TRUE') THEN 1 ELSE 0 END) AS op_flag
             FROM icu_ep GROUP BY src_hospital_id, subject_id, hadm_id, ep),
-- [B3] 환자별 첫 ICU 재실 1개 → 그 입원 1건 (재입실·재입원 제외)
first_ep AS (SELECT * FROM (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY src_hospital_id, subject_id ORDER BY icu_in) AS rn FROM episodes e) x WHERE rn = 1),
base AS (SELECT f.src_hospital_id AS hospital, f.subject_id, f.hadm_id, f.stay_id, f.icu_in, f.icu_out, f.first_careunit, f.op_flag,
                a.admittime, a.dischtime, a.deathtime, a.hospital_expire_flag, a.edregtime, a.admission_type, a.admission_location,
                CASE WHEN a.edregtime IS NOT NULL AND a.edregtime < a.admittime THEN a.edregtime ELSE a.admittime END AS t0,   -- 시간 0 = 병원 도착
                p.sex, p.anchor_age, p.anchor_year, p.anchor_year_group
         FROM first_ep f
         JOIN adm a ON a.src_hospital_id = f.src_hospital_id AND a.hadm_id = f.hadm_id
         JOIN pat p ON p.src_hospital_id = f.src_hospital_id AND p.subject_id = f.subject_id),
-- [B4] 입원 시 나이: 'N years' → N + (입원연도 − anchor_year); '90 years or older' → 90; 'N months'/'N days' → 0
aged AS (SELECT b.*, CASE WHEN anchor_age LIKE '%or older%' THEN 90
                          WHEN anchor_age LIKE '%year%' THEN CAST(regexp_extract(anchor_age, '^([0-9]+)', 1) AS integer) + (year(admittime) - CAST(anchor_year AS integer))
                          ELSE 0 END AS age FROM base b),
adult AS (SELECT * FROM aged WHERE age >= 18),
-- [B5] 진단 플래그 (DIAGNOSES_ICD 주·부상병 전부, 점 없는 코드, 접두사 매칭)
dx AS (SELECT DISTINCT d.src_hospital_id, d.hadm_id, d.icd_code FROM DIAGNOSES_ICD d JOIN adult s ON s.hospital = d.src_hospital_id AND s.hadm_id = d.hadm_id),
flags AS (SELECT src_hospital_id, hadm_id,
      MAX(CASE WHEN (icd_code IN ('J13', 'J14', 'J180', 'J181', 'J188', 'J189') OR icd_code LIKE 'J15%' OR icd_code LIKE 'J16%' OR icd_code LIKE 'J180%' OR icd_code LIKE 'J181%' OR icd_code LIKE 'J188%' OR icd_code LIKE 'J189%') THEN 1 ELSE 0 END) AS pna,   -- 폐렴 포함 코드
      MAX(CASE WHEN (icd_code LIKE 'J690%') THEN 1 ELSE 0 END) AS pna_asp,   -- 흡인성 → 제외
      MAX(CASE WHEN (icd_code LIKE 'J12%' OR icd_code LIKE 'J100%' OR icd_code LIKE 'J110%') THEN 1 ELSE 0 END) AS viral_cocode,   -- 바이러스·인플루엔자 폐렴 동반 (표시만)
      MAX(CASE WHEN (icd_code IN ('N10', 'N12') OR icd_code LIKE 'N10%' OR icd_code LIKE 'N12%' OR icd_code LIKE 'N390%') THEN 1 ELSE 0 END) AS uti,   -- 요로감염 포함 코드
      MAX(CASE WHEN (icd_code LIKE 'N300%' OR icd_code LIKE 'N309%') THEN 1 ELSE 0 END) AS cystitis_code,   -- 방광염 코드 동반 (표시만)
      MAX(CASE WHEN (icd_code LIKE 'T835%') THEN 1 ELSE 0 END) AS cauti,   -- 카테터 관련 → 제외
      MAX(CASE WHEN (icd_code LIKE 'A40%' OR icd_code LIKE 'A41%' OR icd_code LIKE 'R651%') THEN 1 ELSE 0 END) AS sepsis_by_code,   -- 패혈증 코드 (KCD: R65.1 만. R65.2/3 은 비감염성)
      MAX(CASE WHEN (icd_code LIKE 'E10%' OR icd_code LIKE 'E11%' OR icd_code LIKE 'E13%' OR icd_code LIKE 'E14%') THEN 1 ELSE 0 END) AS dm,
      MAX(CASE WHEN (icd_code LIKE 'N18%') THEN 1 ELSE 0 END) AS ckd,
      MAX(CASE WHEN (icd_code LIKE 'J44%') THEN 1 ELSE 0 END) AS copd,
      MAX(CASE WHEN (icd_code LIKE 'J47%') THEN 1 ELSE 0 END) AS bronchiectasis,
      MAX(CASE WHEN (icd_code LIKE 'I50%') THEN 1 ELSE 0 END) AS hf,
      MAX(CASE WHEN (icd_code LIKE 'K70%' OR icd_code LIKE 'K71%' OR icd_code LIKE 'K72%' OR icd_code LIKE 'K73%' OR icd_code LIKE 'K74%' OR icd_code LIKE 'K75%' OR icd_code LIKE 'K76%' OR icd_code LIKE 'K77%') THEN 1 ELSE 0 END) AS liver,   -- K70–K77
      MAX(CASE WHEN (icd_code LIKE 'C%') THEN 1 ELSE 0 END) AS cancer,
      MAX(CASE WHEN (icd_code LIKE 'D80%' OR icd_code LIKE 'D81%' OR icd_code LIKE 'D82%' OR icd_code LIKE 'D83%' OR icd_code LIKE 'D84%' OR icd_code LIKE 'D89%' OR icd_code LIKE 'B20%' OR icd_code LIKE 'B21%' OR icd_code LIKE 'B22%' OR icd_code LIKE 'B23%' OR icd_code LIKE 'B24%' OR icd_code LIKE 'Z94%') THEN 1 ELSE 0 END) AS immuno,   -- 면역결핍·HIV·이식
      MAX(CASE WHEN (icd_code LIKE 'O%' OR icd_code LIKE 'Z33%' OR icd_code LIKE 'Z34%') THEN 1 ELSE 0 END) AS pregnancy,
      MAX(CASE WHEN (icd_code LIKE 'N13%' OR icd_code LIKE 'N20%' OR icd_code LIKE 'N21%' OR icd_code LIKE 'N40%') THEN 1 ELSE 0 END) AS uro_obstruction,   -- 요로폐색·결석·전립선비대
      MAX(CASE WHEN (icd_code LIKE 'F10%') THEN 1 ELSE 0 END) AS alcohol
          FROM dx GROUP BY src_hospital_id, hadm_id),
-- [B6] 질환군: 폐렴(흡인성 제외) / 요로감염(카테터 관련 제외). 둘 다면 제외
sel AS (SELECT s.*, f.pna, f.pna_asp, f.viral_cocode, f.uti, f.cystitis_code, f.cauti, f.sepsis_by_code, f.dm, f.ckd, f.copd, f.bronchiectasis, f.hf, f.liver, f.cancer, f.immuno, f.pregnancy, f.uro_obstruction, f.alcohol,
               CASE WHEN f.pna = 1 AND f.pna_asp = 0 AND NOT (f.uti = 1 AND f.cauti = 0) THEN 'pneumonia'
                    WHEN f.uti = 1 AND f.cauti = 0 AND NOT (f.pna = 1 AND f.pna_asp = 0) THEN 'uti' END AS grp
        FROM adult s JOIN flags f ON f.src_hospital_id = s.hospital AND f.hadm_id = s.hadm_id),
cohort0 AS (SELECT * FROM sel WHERE grp IS NOT NULL),
-- [A1] PRESCRIPTIONS 를 한 번만 읽는다: 코호트 환자(subject 기준)의 t0 −90일 ~ 퇴원 사이 처방 중 전신 항생제(GSN J01, 없으면 약품명) 또는 승압제(ATC C01CA03/24/04/07 · H01BA01, 또는 약품명).
--      이전 입원의 행(hadm_is_cohort=0)은 '90일 내 정맥 항생제' 계산용, 승압제 행(is_vasopressor=1)은 승압제 플래그용 — 둘 다 파이썬(derive)이 처리하고 요법 계산에서는 자동 제외된다.
rx AS (SELECT * FROM (
          SELECT c.hospital, c.hadm_id AS cohort_hadm, c.t0, p.hadm_id, p.starttime, p.stoptime, p.drug, p.gsn, p.route, p.dose_val_rx, p.dose_unit_rx, p.doses_per_24_hrs,
                 CASE WHEN p.gsn IN ('C01CA03', 'C01CA24', 'C01CA04', 'C01CA07', 'H01BA01') OR (lower(p.drug) LIKE '%norepinephrine%' OR lower(p.drug) LIKE '%noradrenalin%' OR lower(p.drug) LIKE '%levophed%' OR lower(p.drug) LIKE '%epinephrine%' OR lower(p.drug) LIKE '%adrenalin%' OR lower(p.drug) LIKE '%dopamine%' OR lower(p.drug) LIKE '%dobutamine%' OR lower(p.drug) LIKE '%vasopressin%' OR lower(p.drug) LIKE '%pitressin%') THEN 1 ELSE 0 END AS is_vasopressor,
                 ROW_NUMBER() OVER (PARTITION BY c.hospital, c.hadm_id, p.hadm_id, p.pharmacy_id, p.starttime, p.drug ORDER BY p.src_batch_id DESC) AS rn
          FROM PRESCRIPTIONS p JOIN cohort0 c ON c.hospital = p.src_hospital_id AND c.subject_id = p.subject_id
          WHERE p.starttime IS NOT NULL AND date_diff('day', p.starttime, c.t0) <= 90 AND p.starttime <= c.dischtime
            AND ( (((p.gsn LIKE 'J01%')
           OR (p.gsn IS NULL AND (lower(p.drug) LIKE '%cef%' OR lower(p.drug) LIKE '%cillin%' OR lower(p.drug) LIKE '%penem%' OR lower(p.drug) LIKE '%vanco%' OR lower(p.drug) LIKE '%teico%' OR lower(p.drug) LIKE '%tazo%' OR lower(p.drug) LIKE '%sulbactam%' OR lower(p.drug) LIKE '%clavul%' OR lower(p.drug) LIKE '%mycin%' OR lower(p.drug) LIKE '%micin%' OR lower(p.drug) LIKE '%floxacin%' OR lower(p.drug) LIKE '%cycline%' OR lower(p.drug) LIKE '%metronidazole%' OR lower(p.drug) LIKE '%colistin%' OR lower(p.drug) LIKE '%polymyxin%' OR lower(p.drug) LIKE '%linezolid%' OR lower(p.drug) LIKE '%fosfomycin%' OR lower(p.drug) LIKE '%nitrofurantoin%' OR lower(p.drug) LIKE '%trimethoprim%' OR lower(p.drug) LIKE '%sulfamethoxazole%' OR lower(p.drug) LIKE '%bactrim%' OR lower(p.drug) LIKE '%cotrim%' OR lower(p.drug) LIKE '%septrin%' OR lower(p.drug) LIKE '%aztreonam%' OR lower(p.drug) LIKE '%tigecycline%' OR lower(p.drug) LIKE '%daptomycin%' OR lower(p.drug) LIKE '%rifampi%' OR lower(p.drug) LIKE '%clindamycin%' OR lower(p.drug) LIKE '%flomoxef%' OR lower(p.drug) LIKE '%arbekacin%')
            AND NOT (lower(p.drug) LIKE '%mitomycin%' OR lower(p.drug) LIKE '%bleomycin%' OR lower(p.drug) LIKE '%dactinomycin%' OR lower(p.drug) LIKE '%daunomycin%' OR lower(p.drug) LIKE '%doxorubicin%' OR lower(p.drug) LIKE '%idarubicin%' OR lower(p.drug) LIKE '%epirubicin%' OR lower(p.drug) LIKE '%rapamycin%' OR lower(p.drug) LIKE '%sirolimus%' OR lower(p.drug) LIKE '%tacrolimus%' OR lower(p.drug) LIKE '%nystatin%' OR lower(p.drug) LIKE '%amphotericin%' OR lower(p.drug) LIKE '%caspofungin%' OR lower(p.drug) LIKE '%micafungin%' OR lower(p.drug) LIKE '%anidulafungin%' OR lower(p.drug) LIKE '%voriconazole%' OR lower(p.drug) LIKE '%fluconazole%' OR lower(p.drug) LIKE '%itraconazole%' OR lower(p.drug) LIKE '%posaconazole%' OR lower(p.drug) LIKE '%acyclovir%' OR lower(p.drug) LIKE '%ganciclovir%' OR lower(p.drug) LIKE '%oseltamivir%' OR lower(p.drug) LIKE '%rifaximin%' OR lower(p.drug) LIKE '%neomycin%' OR lower(p.drug) LIKE '%bacitracin%' OR lower(p.drug) LIKE '%mupirocin%' OR lower(p.drug) LIKE '%fusidic%' OR lower(p.drug) LIKE '%gentamicin cream%' OR lower(p.drug) LIKE '%ointment%' OR lower(p.drug) LIKE '%oint%' OR lower(p.drug) LIKE '%cream%' OR lower(p.drug) LIKE '%eye%' OR lower(p.drug) LIKE '%ear%' OR lower(p.drug) LIKE '%ophth%' OR lower(p.drug) LIKE '%otic%' OR lower(p.drug) LIKE '%inhal%' OR lower(p.drug) LIKE '%nebul%' OR lower(p.drug) LIKE '%irrig%' OR lower(p.drug) LIKE '%bladder%' OR lower(p.drug) LIKE '%topical%' OR lower(p.drug) LIKE '%lock%')))
          AND (p.gsn IS NULL OR p.gsn NOT LIKE 'A07AA%') AND (p.route IS NULL OR NOT (upper(p.route) LIKE '%TOPICAL%' OR upper(p.route) LIKE '%TOP%' OR upper(p.route) LIKE '%OPHTH%' OR upper(p.route) LIKE '%EYE%' OR upper(p.route) LIKE '%OU%' OR upper(p.route) LIKE '%OD%' OR upper(p.route) LIKE '%OS%' OR upper(p.route) LIKE '%EAR%' OR upper(p.route) LIKE '%OTIC%' OR upper(p.route) LIKE '%INHAL%' OR upper(p.route) LIKE '%NEB%' OR upper(p.route) LIKE '%IRRIG%' OR upper(p.route) LIKE '%BLADDER%' OR p.route LIKE '%외용%' OR p.route LIKE '%점안%' OR p.route LIKE '%점이%' OR p.route LIKE '%흡입%' OR p.route LIKE '%방광%' OR p.route LIKE '%국소%' OR p.route LIKE '%도포%')))
                  OR p.gsn IN ('C01CA03', 'C01CA24', 'C01CA04', 'C01CA07', 'H01BA01') OR (lower(p.drug) LIKE '%norepinephrine%' OR lower(p.drug) LIKE '%noradrenalin%' OR lower(p.drug) LIKE '%levophed%' OR lower(p.drug) LIKE '%epinephrine%' OR lower(p.drug) LIKE '%adrenalin%' OR lower(p.drug) LIKE '%dopamine%' OR lower(p.drug) LIKE '%dobutamine%' OR lower(p.drug) LIKE '%vasopressin%' OR lower(p.drug) LIKE '%pitressin%') )) x WHERE rn = 1)
-- ===== 출력 2: antibiotics.csv (한 행 = 처방 1건). 성분명 · 계열 · AWaRe 는 atc_to_ingredient.csv 로 파이썬에서 붙인다. EMAR 투여 시각은 쓰지 않는다(001·005·009 시각 오염)
SELECT to_hex(md5(to_utf8(a.hospital || '|' || a.cohort_hadm))) AS hashed_id, a.hospital,
       CASE WHEN a.hadm_id = a.cohort_hadm THEN 1 ELSE 0 END AS hadm_is_cohort, a.is_vasopressor,
       a.drug AS drug_raw, a.gsn AS atc, a.route, a.dose_val_rx AS dose, a.dose_unit_rx AS dose_unit, a.doses_per_24_hrs AS doses_per_24h,
       date_diff('minute', a.t0, a.starttime) / 60.0 AS t_start,
       date_diff('minute', a.t0, a.stoptime)  / 60.0 AS t_stop,
       'prescriptions' AS source
FROM rx a;

-- ########## 쿼리 3 / 3 : cultures.csv ##########
WITH
-- [B1] 원천 중복 제거: 월 배치(src_batch_id)마다 같은 키가 다시 실리므로 키당 최신 배치 1행만 남긴다
adm AS (SELECT * FROM (
          SELECT subject_id, hadm_id, admittime, dischtime, deathtime, hospital_expire_flag, edregtime, admission_type, admission_location, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY src_batch_id DESC) AS rn
          FROM ADMISSIONS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202')) x WHERE rn = 1),
pat AS (SELECT * FROM (
          SELECT subject_id, sex, anchor_age, anchor_year, anchor_year_group, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, subject_id ORDER BY src_batch_id DESC) AS rn
          FROM PATIENTS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202')) x WHERE rn = 1),
icu AS (SELECT * FROM (
          SELECT subject_id, hadm_id, stay_id, intime, outtime, first_careunit, op_flag, src_hospital_id,
                 ROW_NUMBER() OVER (PARTITION BY src_hospital_id, stay_id ORDER BY src_batch_id DESC) AS rn
          FROM ICUSTAYS WHERE src_hospital_id IN ('001', '003', '004', '005', '006', '009', '202') AND intime IS NOT NULL) x WHERE rn = 1),
-- [B2] 전실 단위 stay → 연속 재실(episode) 1회로 병합: 이전 outtime 과 다음 intime 간격 ≤ 60분이면 같은 재실
icu_ord AS (SELECT i.*, LAG(outtime) OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY intime) AS prev_out FROM icu i),
icu_ep AS (SELECT i.*, SUM(CASE WHEN prev_out IS NULL OR date_diff('minute', prev_out, intime) > 60 THEN 1 ELSE 0 END)
                          OVER (PARTITION BY src_hospital_id, hadm_id ORDER BY intime ROWS UNBOUNDED PRECEDING) AS ep FROM icu_ord i),
episodes AS (SELECT src_hospital_id, subject_id, hadm_id, ep, MIN(stay_id) AS stay_id, MIN(intime) AS icu_in, MAX(outtime) AS icu_out,
                    MIN_BY(first_careunit, intime) AS first_careunit,
                    MAX(CASE WHEN CAST(op_flag AS varchar) IN ('1', 'Y', 'y', 'true', 'TRUE') THEN 1 ELSE 0 END) AS op_flag
             FROM icu_ep GROUP BY src_hospital_id, subject_id, hadm_id, ep),
-- [B3] 환자별 첫 ICU 재실 1개 → 그 입원 1건 (재입실·재입원 제외)
first_ep AS (SELECT * FROM (SELECT e.*, ROW_NUMBER() OVER (PARTITION BY src_hospital_id, subject_id ORDER BY icu_in) AS rn FROM episodes e) x WHERE rn = 1),
base AS (SELECT f.src_hospital_id AS hospital, f.subject_id, f.hadm_id, f.stay_id, f.icu_in, f.icu_out, f.first_careunit, f.op_flag,
                a.admittime, a.dischtime, a.deathtime, a.hospital_expire_flag, a.edregtime, a.admission_type, a.admission_location,
                CASE WHEN a.edregtime IS NOT NULL AND a.edregtime < a.admittime THEN a.edregtime ELSE a.admittime END AS t0,   -- 시간 0 = 병원 도착
                p.sex, p.anchor_age, p.anchor_year, p.anchor_year_group
         FROM first_ep f
         JOIN adm a ON a.src_hospital_id = f.src_hospital_id AND a.hadm_id = f.hadm_id
         JOIN pat p ON p.src_hospital_id = f.src_hospital_id AND p.subject_id = f.subject_id),
-- [B4] 입원 시 나이: 'N years' → N + (입원연도 − anchor_year); '90 years or older' → 90; 'N months'/'N days' → 0
aged AS (SELECT b.*, CASE WHEN anchor_age LIKE '%or older%' THEN 90
                          WHEN anchor_age LIKE '%year%' THEN CAST(regexp_extract(anchor_age, '^([0-9]+)', 1) AS integer) + (year(admittime) - CAST(anchor_year AS integer))
                          ELSE 0 END AS age FROM base b),
adult AS (SELECT * FROM aged WHERE age >= 18),
-- [B5] 진단 플래그 (DIAGNOSES_ICD 주·부상병 전부, 점 없는 코드, 접두사 매칭)
dx AS (SELECT DISTINCT d.src_hospital_id, d.hadm_id, d.icd_code FROM DIAGNOSES_ICD d JOIN adult s ON s.hospital = d.src_hospital_id AND s.hadm_id = d.hadm_id),
flags AS (SELECT src_hospital_id, hadm_id,
      MAX(CASE WHEN (icd_code IN ('J13', 'J14', 'J180', 'J181', 'J188', 'J189') OR icd_code LIKE 'J15%' OR icd_code LIKE 'J16%' OR icd_code LIKE 'J180%' OR icd_code LIKE 'J181%' OR icd_code LIKE 'J188%' OR icd_code LIKE 'J189%') THEN 1 ELSE 0 END) AS pna,   -- 폐렴 포함 코드
      MAX(CASE WHEN (icd_code LIKE 'J690%') THEN 1 ELSE 0 END) AS pna_asp,   -- 흡인성 → 제외
      MAX(CASE WHEN (icd_code LIKE 'J12%' OR icd_code LIKE 'J100%' OR icd_code LIKE 'J110%') THEN 1 ELSE 0 END) AS viral_cocode,   -- 바이러스·인플루엔자 폐렴 동반 (표시만)
      MAX(CASE WHEN (icd_code IN ('N10', 'N12') OR icd_code LIKE 'N10%' OR icd_code LIKE 'N12%' OR icd_code LIKE 'N390%') THEN 1 ELSE 0 END) AS uti,   -- 요로감염 포함 코드
      MAX(CASE WHEN (icd_code LIKE 'N300%' OR icd_code LIKE 'N309%') THEN 1 ELSE 0 END) AS cystitis_code,   -- 방광염 코드 동반 (표시만)
      MAX(CASE WHEN (icd_code LIKE 'T835%') THEN 1 ELSE 0 END) AS cauti,   -- 카테터 관련 → 제외
      MAX(CASE WHEN (icd_code LIKE 'A40%' OR icd_code LIKE 'A41%' OR icd_code LIKE 'R651%') THEN 1 ELSE 0 END) AS sepsis_by_code,   -- 패혈증 코드 (KCD: R65.1 만. R65.2/3 은 비감염성)
      MAX(CASE WHEN (icd_code LIKE 'E10%' OR icd_code LIKE 'E11%' OR icd_code LIKE 'E13%' OR icd_code LIKE 'E14%') THEN 1 ELSE 0 END) AS dm,
      MAX(CASE WHEN (icd_code LIKE 'N18%') THEN 1 ELSE 0 END) AS ckd,
      MAX(CASE WHEN (icd_code LIKE 'J44%') THEN 1 ELSE 0 END) AS copd,
      MAX(CASE WHEN (icd_code LIKE 'J47%') THEN 1 ELSE 0 END) AS bronchiectasis,
      MAX(CASE WHEN (icd_code LIKE 'I50%') THEN 1 ELSE 0 END) AS hf,
      MAX(CASE WHEN (icd_code LIKE 'K70%' OR icd_code LIKE 'K71%' OR icd_code LIKE 'K72%' OR icd_code LIKE 'K73%' OR icd_code LIKE 'K74%' OR icd_code LIKE 'K75%' OR icd_code LIKE 'K76%' OR icd_code LIKE 'K77%') THEN 1 ELSE 0 END) AS liver,   -- K70–K77
      MAX(CASE WHEN (icd_code LIKE 'C%') THEN 1 ELSE 0 END) AS cancer,
      MAX(CASE WHEN (icd_code LIKE 'D80%' OR icd_code LIKE 'D81%' OR icd_code LIKE 'D82%' OR icd_code LIKE 'D83%' OR icd_code LIKE 'D84%' OR icd_code LIKE 'D89%' OR icd_code LIKE 'B20%' OR icd_code LIKE 'B21%' OR icd_code LIKE 'B22%' OR icd_code LIKE 'B23%' OR icd_code LIKE 'B24%' OR icd_code LIKE 'Z94%') THEN 1 ELSE 0 END) AS immuno,   -- 면역결핍·HIV·이식
      MAX(CASE WHEN (icd_code LIKE 'O%' OR icd_code LIKE 'Z33%' OR icd_code LIKE 'Z34%') THEN 1 ELSE 0 END) AS pregnancy,
      MAX(CASE WHEN (icd_code LIKE 'N13%' OR icd_code LIKE 'N20%' OR icd_code LIKE 'N21%' OR icd_code LIKE 'N40%') THEN 1 ELSE 0 END) AS uro_obstruction,   -- 요로폐색·결석·전립선비대
      MAX(CASE WHEN (icd_code LIKE 'F10%') THEN 1 ELSE 0 END) AS alcohol
          FROM dx GROUP BY src_hospital_id, hadm_id),
-- [B6] 질환군: 폐렴(흡인성 제외) / 요로감염(카테터 관련 제외). 둘 다면 제외
sel AS (SELECT s.*, f.pna, f.pna_asp, f.viral_cocode, f.uti, f.cystitis_code, f.cauti, f.sepsis_by_code, f.dm, f.ckd, f.copd, f.bronchiectasis, f.hf, f.liver, f.cancer, f.immuno, f.pregnancy, f.uro_obstruction, f.alcohol,
               CASE WHEN f.pna = 1 AND f.pna_asp = 0 AND NOT (f.uti = 1 AND f.cauti = 0) THEN 'pneumonia'
                    WHEN f.uti = 1 AND f.cauti = 0 AND NOT (f.pna = 1 AND f.pna_asp = 0) THEN 'uti' END AS grp
        FROM adult s JOIN flags f ON f.src_hospital_id = s.hospital AND f.hadm_id = s.hadm_id),
cohort0 AS (SELECT * FROM sel WHERE grp IS NOT NULL),
-- [M1] MICROBIOLOGYEVENTS 를 한 번만 읽는다: 코호트 환자의 t0 −365일 ~ 퇴원 사이 검체(채취 = charttime, 보고 = storetime). 검체×균 단위로 접고(항생제 감수성 행 → is_mrsa 플래그로 압축)
--      −365일 ~ −48h 의 행은 '1년 내 MRSA · 녹농균 분리' 계산용(파이썬 derive). 의심 시각 짝짓기 · 카드에는 −48h 이후 행만 쓴다(파이썬이 거른다).
cult AS (SELECT c.hospital, c.hadm_id, c.t0, m.micro_specimen_id, m.charttime, MIN(m.storetime) AS storetime, m.spec_type_desc, m.test_name, m.org_name,
                MAX(CASE WHEN upper(m.org_name) LIKE '%MRSA%' OR upper(m.org_name) LIKE '%METHICILLIN%RESIST%'
                          OR (upper(m.org_name) LIKE '%AUREUS%' AND upper(m.ab_name) LIKE '%OXACILLIN%' AND upper(m.interpretation) = 'R') THEN 1 ELSE 0 END) AS is_mrsa,
                MAX(CASE WHEN upper(m.org_name) LIKE '%PSEUDOMONAS AERUGINOSA%' THEN 1 ELSE 0 END) AS is_pseudomonas
         FROM cohort0 c JOIN MICROBIOLOGYEVENTS m ON m.src_hospital_id = c.hospital AND m.subject_id = c.subject_id
         WHERE m.chartdate IS NOT NULL AND m.charttime IS NOT NULL
           AND date_diff('day', m.charttime, c.t0) <= 365 AND m.charttime <= c.dischtime
         GROUP BY c.hospital, c.hadm_id, c.t0, m.micro_specimen_id, m.charttime, m.spec_type_desc, m.test_name, m.org_name)
-- ===== 출력 3: cultures.csv. is_culture=0 = 선별·비배양 검체(직장 VRE/CRE, 비강 MRSA, 카테터 tip, PCR, 항원) → 의심 시각 짝짓기에서 제외
SELECT to_hex(md5(to_utf8(x.hospital || '|' || x.hadm_id))) AS hashed_id, x.hospital, x.micro_specimen_id,
       x.spec_type_desc AS spec_type, x.test_name,
       CASE WHEN regexp_like(upper(COALESCE(x.spec_type_desc, '') || ' ' || COALESCE(x.test_name, '')), '(^|[^A-Z])(CRE|VRE|MRSA|TIP|PCR)([^A-Z]|$)|RECTAL|NASAL|SCREEN|SURVEILLANCE|ANTIGEN|직장|비강|선별|항원') THEN 0 ELSE 1 END AS is_culture,
       date_diff('minute', x.t0, x.charttime) / 60.0 AS t_collect,
       date_diff('minute', x.t0, x.storetime) / 60.0 AS t_result,
       x.org_name AS organism, x.is_mrsa, x.is_pseudomonas
FROM cult x;
