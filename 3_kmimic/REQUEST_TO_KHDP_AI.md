[실행 요청 — 첨부 파일을 그대로 실행. 로직 재작성 금지]

★ 빠른 경로(권장): 에이전트가 행을 중계하지 않게 한다.
   "run_extract.py 의 run_sql(sql, dataset) 함수만, 네가 SQL 을 실행할 때 쓰는 연결 방식으로 채워 줘. 다른 줄은 고치지 마. 채운 뒤 실행 명령을 알려 줘."
   → 사람이 pod 터미널에서 `python3 run_extract.py --test --hospitals=005` 로 연결 확인 후 `python3 run_extract.py --hospitals=005,006,004,202,009 --out=DATA/raw` 실행.
   아래 1단계는 이 경로가 안 될 때만 에이전트에게 시킨다.

이 폴더의 파일을 workspace 에 두고 아래 순서대로 실행해 주세요. 새 SQL 이나 새 변수를 만들지 말고, 설명서(KMIMIC_EXTRACTION.md)의 명령을 그대로 씁니다.
파일: kmimic_extract.sql(쿼리 3개), analyze_kmimic_cohort.py, make_cards_min.py, rule_judge_kr.py, aware_table.py, aware_2025.csv, atc_to_ingredient.csv, test_data/(합성 3명), KMIMIC_EXTRACTION.md(설명서, 읽기만).

0. 동작 확인 (실데이터 전에, 1분)
   설명서 "먼저 동작 확인" 의 명령 3줄을 test_data 로 실행. 오류 없이 cards.jsonl · verdicts.jsonl 이 나오면 다음으로.

1. SQL → 기관별 CSV (데이터셋마다 반복)
   순서: kmimic-emr-003 → 004 → 005 → 006 → 009 → 001 → 202. (K-MIMIC-MORTAL · SYN-ICU 는 사용하지 않음)
   데이터셋 하나에 연결 → kmimic_extract.sql 의 쿼리 1 실행 → DATA/raw/cohort_<기관>.csv 저장 → 쿼리 2 → antibiotics_<기관>.csv → 쿼리 3 → cultures_<기관>.csv.
   - 쿼리 하나가 끝날 때마다 바로 저장하고 행 수를 적어 둘 것(중간에 끊겨도 이어 가게). 이미 있는 파일은 건너뜀.
   - SQL 을 고쳐야 하면 문법만: 함수 이름(date_diff · MIN_BY · regexp_* · md5), 식별자 따옴표("group"), 테이블 접두어("kmimic-emr-003".ADMISSIONS). WHERE 조건 · CASE · 시간 창(60분 · 48h · 72h · 24h) · 코드 목록 · 제외 규칙은 바꾸지 말 것. 고친 줄은 원문과 함께 보고.
   - 너무 무거우면 공통 블록(B1~B6)의 cohort0 를 임시 테이블로 만든 뒤 세 쿼리가 그것을 읽게 해도 됨(결과 컬럼은 동일해야 함). 한 기관이 끝내 안 되면 건너뛰고 다음 기관으로, 사유 보고.

2. 이어 붙이기 + id_map 분리
   설명서 ① 끝의 파이썬 명령 그대로 → DATA/cohort.csv, antibiotics.csv, cultures.csv, id_map.csv.

3. 파이썬 ②~⑤ (설명서의 명령 그대로, 화면 출력을 파일로 저장)
   ② derive      → DATA/cohort_derived.csv, 화면 출력 → DATA/summary_derive.txt
   ③ cards       → DATA/cards_main.jsonl (--abx-only-suspicion), DATA/cards_202.jsonl (--hospitals=202). 화면의 "미매핑" 줄 → DATA/summary_cards.txt
   ④ judge       → DATA/summary_kr_main.txt, DATA/summary_kr_202.txt (--icu-severe --class-equiv)
                    민감도 2종 추가: ③ 에서 --abx-only-suspicion 을 뺀 카드로 ④ → summary_kr_main_paired.txt / ④ 에서 --icu-severe 를 뺀 것 → summary_kr_main_strict.txt
   ⑤ summarize   → DATA/summary_cohort.txt
   ⑥ aware_table → DATA/summary_aware_main.txt (--by=hospital), DATA/summary_aware_202.txt

4. 보고 (단계마다 짧게, 표로)
   - 1단계: 기관별 cohort / antibiotics / cultures 행 수, 실행 시간, 고친 SQL 줄, 건너뛴 기관과 사유.
   - 3단계: summary_derive.txt 의 "단계별 n" 표(기관별), 카드 수와 미매핑 상위 15개, summary_kr_*.txt 전문, summary_cohort.txt 전문, summary_aware_*.txt 전문.
   - 첫 기관(003)이 끝나면 다음 기관으로 가기 전에 1단계 보고를 먼저 보낼 것.

하지 말 것: 새 SQL 작성, 변수 추가, SOFA · vitals · EMAR 추출, 집계 방식 변경, 환자 단위 파일(CSV · jsonl)의 내용을 보고에 붙이기, 결과 해석.
