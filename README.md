# RAG 기반 AI 에이전트를 활용한 중환자실 폐렴 · 요로감염 초기 항생제 치료의 국내외 지침 준수 평가 (K-MIMIC · MIMIC-IV)
Korea Clinical Datathon 2026 (10/16–17, 평창, KHDP) · 전체 정리 · 2026-10-17 11:00 갱신


> **데이터 안내 (공개 저장소).** 이 저장소에는 코드 · 실행 안내서 · 집계 결과 · 합성 데모 데이터만 있다. MIMIC-IV 환자 단위 자료(추출 CSV · 사례 카드 · 판정 jsonl · 노트북 출력)는 PhysioNet 자격자만 접근할 수 있어 포함하지 않았고, K-MIMIC 자료와 수치는 KHDP 반출 절차 이후에 공개한다. 지침 PDF 와 그 추출 텍스트(`4_guideline/pdf`, `text`)는 저작권 때문에 빼었으며, 각 지침은 발행 기관에서 받아 `pdftotext -layout` 으로 같은 파일명을 만들면 코드가 그대로 돈다. RAG 평가 시트는 평가자 개인정보가 있어 비공개.

## 0. 지금 상태 (한눈에)

| 트랙 | 상태 | 다음 할 일 |
|---|---|---|
| MIMIC-IV (로컬) | **완료** — 코호트 · 패혈증 라벨 · 사례 카드 9,398건 · 해외 지침(M03 · M07) 규칙 판정 · AWaRe 표 | 앱의 일괄 판정(20건)으로 규칙 vs LLM+RAG 일치율 |
| K-MIMIC (KHDP 플랫폼) | **추출 중** — 003 완료(khdp.ai pod 경유, 약 3시간 소요), 나머지는 `run_extract.py` 로 에이전트 없이 실행 | 003 으로 ②~⑥ 먼저 끝내고, 시간 되는 만큼 005 → 202 → 006 → 004 → 009 추가. 집계만 반출 |
| 가이드라인 · 판정 | 국내(K02 · K04) · 해외(M03 · M07) 규칙표 코드화 완료, RAG 평가 2종 완료 | 임상의 불일치 심사 |
| 앱 (khdp.ai) | **v3 게시 완료(running)** — `abx-guideline-agent`, 운영 주소 khdp.ai/apps/runtime/abx-guideline-agent/. 규칙 판정 + BM25 근거 검색 + LLM 판정 붙여넣기 + 대시보드(원본 집계 분리) | 누락 파일 5종(cards_all · eval20 · 전건 판정 · 민감도 2종)을 앱에 연결 → 20건 표본 탭 · 전건 색인 |

핵심 결정(바뀌지 않는 것): 두 트랙은 **교차 판정하지 않는다**(K-MIMIC ↔ 국내 지침, MIMIC ↔ 해외 지침). 두 데이터를 같은 자로 재는 유일한 공통 잣대는 **WHO AWaRe**. 패혈증 라벨은 데이터마다 다르게 두고(MIMIC = sepsis3, K-MIMIC = 진단코드) 맞추지 않는다. K-MIMIC 은 기관별로 보고하고, MIMIC 은 한 기관(BIDMC)이다.

---

## 1. 연구 설계 (확정)

**질문.** ICU 에 입실한 성인 지역사회획득 폐렴 · 요로감염 환자의 초기(경험적) 항생제 요법이 지침에 맞았는가. RAG 를 단 AI 에이전트가 이를 판정하고 근거를 설명할 수 있는가.

**두 트랙.**

| | K-MIMIC | MIMIC-IV v3.1 |
|---|---|---|
| 기관 | 001 · 003 · 004 · 005 · 006 · 009 (202 는 별도) | BIDMC 1곳 |
| 판정 기준 | K02 국내 CAP 2026 · K04 국내 UTI 2026 | M03 ATS/IDSA CAP 2019 · M07 IDSA cUTI 2025 |
| 패혈증 라벨 | 진단코드 A40 · A41 · R65.1 | mimic-code sepsis3 (BigQuery 공식 표) |
| 공통 잣대 | WHO AWaRe (W01 · W02) — Access / Watch / Reserve 비율 | 같음 |

**판정 구조(3층).** RAG = 지식층(지침 PDF 7종, BGE-M3 청크) · 규칙 = 판정층(`rule_judge_kr.py`, 지침 표를 코드로 옮긴 것) · LLM = 설명 · 보고층. 규칙 판정값과 LLM+RAG 판정값을 같은 20건에서 비교하고, 불일치는 임상의가 심사한다. "RAG 가 왜 필요한가"의 답: 규칙은 판정을, RAG 는 근거 문장과 예외(정당한 이탈) 설명을 맡는다.

**코호트 정의(두 데이터 공통).**
1. 환자별 첫 ICU 재실(연속 재실 1회, K-MIMIC 은 간격 ≤ 60분 병합)의 입원 1건. 재입실 · 재입원 제외. 성인 ≥ 18세.
2. 폐렴: J13 · J14 · J15x · J16x · J18.0/.1/.8/.9 (MIMIC ICD-9: 481–483 · 485 · 486). 흡인성(J69.0 / 507.0) · VAP 제외, 바이러스 · 인플루엔자만은 미포함(동반 시 표시).
3. 요로감염: N10 · N12 · N39.0 (ICD-9: 590.1 · 590.80 · 590.9 · 599.0). 카테터 관련(T83.5 / 996.64) 제외, 방광염만은 미포함.
4. 둘 다 있으면 제외.
5. 감염 의심 시각: `culture_first`(배양 → 72h 안 전신 항생제 ⇒ 배양 시각) / `antibiotic_first`(항생제 → 24h 안 배양 ⇒ 항생제 시각) / 가장 이른 것.
6. 지역사회 획득 = 의심 시각 ≤ 병원 도착(t0 = min(응급실 등록, 입원)) + 48h.
7. 초기 요법 = 의심 시각 이후 첫 항생제부터 +24h 안에 시작한 전신 항생제 성분 집합.
8. 사례 카드 = 첫 항생제 처방 시각(T+0) 이전에 **보고된** 값만 담은 JSON(활력징후 · 검사 · 배양 검체명 · 과거력 · 기저질환 · 요법). 퇴원 진단 · 사망 · T+0 이후 결과 · SOFA 는 뺀다(정보 누출 방지).

**판정값(8종).** 준수(추천) · 준수(대안) · 비준수(누락) · 비준수(과잉) · 비준수(다른 약제) · 정당한 이탈 · 해당 없음 · 판정 불가. 준수율 = (추천 + 대안) / (전체 − 해당 없음 − 판정 불가), 하한선은 판정 불가를 비준수로 센 값. 2제 중 1제만 맞으면 50% 가 아니라 집합 비교로 "누락 / 과잉 / 다른 약제" 중 하나. 지침에 없는 변수(중증도 미상 등)는 가능한 모든 행을 평가해 결론이 같으면 채택, 다르면 판정 불가.

---

## 2. 폴더 구조

```
datathon2026/
├─ README.md                 ← 이 문서
├─ 1_plan/                   계획서 PDF(최종) · 팀 브리프
├─ 2_mimic/                  MIMIC-IV 트랙 (완료)
│   ├─ code/                 extract_mimic_cohort.py(추출, 표준 라이브러리, 약 7분) · build_notebook.py(노트북 생성+실행) · rename_columns.py · analyze_kmimic_cohort.py(공용 집계)
│   ├─ data/                 cohort · antibiotics · cultures · vitals_labs · vasopressors · ventilation · id_map · sepsis3_mimic_code … (환자 단위, 자격자만)
│   ├─ notebooks/            mimic_pna_uti.ipynb (실행 결과 포함)
│   ├─ results/              summary.md · funnel.csv · group_summary.json · eval_sample.csv · cards/(20건) · cohort_with_sofa.csv
│   ├─ docs/bigquery_sepsis3.sql   sepsis3 표를 BigQuery 에서 뽑은 쿼리
│   ├─ mimic_final_cards.zip cards_all.jsonl(9,398) · cards_eval20.jsonl · labels.csv · card_schema.md
│   └─ README.md             패키지 설명(컬럼 정의 · 재실행법)
├─ 3_kmimic/                 K-MIMIC 트랙 — 플랫폼에 올릴 키트
│   ├─ KMIMIC_EXTRACTION.md  ★ 추출 · 판정 실행 안내(확정 조건 · 실행 순서 · QC · 함정)
│   ├─ REQUEST_TO_KHDP_AI.md khdp.ai(pod 연결) 에게 키트를 그대로 실행시키는 지시문 — 로직 재작성 금지 · 기관별 체크포인트 · 보고 형식
│   ├─ kmimic_extract.sql    쿼리 3개(cohort / antibiotics / cultures), 각각 단독 실행
│   ├─ run_extract.py        pod 터미널에서 쿼리 3개를 데이터셋마다 실행해 CSV 를 바로 쓰는 스크립트(run_sql() 만 연결 방식으로 채움)
│   ├─ analyze_kmimic_cohort.py   derive(의심 시각 · 초기 요법) / summarize(단계 n · 요법 상위 · 계열 비율)
│   ├─ make_cards_min.py     최소 사례 카드 생성(활력 · 검사 없음)
│   ├─ rule_judge_kr.py      국내 지침 규칙 판정기(4_guideline/rule_judge 와 같은 파일)
│   ├─ atc_to_ingredient.csv ATC → 성분 · 계열 · AWaRe (65행)
│   ├─ aware_table.py + aware_2025.csv   WHO AWaRe 비율 표(두 데이터 공통; W02 2025 분류, 경로 구분)
│   ├─ test_data/            합성 환자 3명 — 키트 동작 확인용
│   └─ khdp_requests/        khdp.ai 에 보냈던 질문 · 요청문 5개(기록)
├─ 4_guideline/              가이드라인 · 판정 트랙
│   ├─ pdf/                  K02 K04 M03 M04 M07 W01 W02 (RAG 취합본, " - 복사본" 제거)
│   ├─ text/                 cap_kr.txt · uti_kr.txt · sepsis_kr.txt (국내 지침 텍스트 추출본; 표 3 · 4 · 5 가 규칙표 출처) · cap_intl.txt (M03 추출본) · cuti_intl.txt (M07 은 이미지 PDF 라 표 1.1 을 옮겨 적음)
│   ├─ rule_judge/           rule_judge_kr.py(국내) · rule_judge_intl.py(해외) + MIMIC 판정 결과: summary_intl_*.txt · all_verdicts_intl_*.jsonl · eval20_verdicts_intl.jsonl (본 결과). *_kr-on-mimic_TEST.* 는 국내 규칙을 MIMIC 에 돌려 본 코드 시험이지 결과가 아님
│   ├─ rag_match/            build_queries.py(카드 → 검색 질의 · LLM 판정 프롬프트) · compare_verdicts.py(규칙 vs LLM 비교) · queries_eval20.jsonl · mock_llm_verdicts.jsonl
│   ├─ text/aware_2025.txt   WHO AWaRe 2025 목록 텍스트(W02 추출본, 분류 대조에 사용)
│   │   └─ demo/             시연용 합성 카드 8건 + 질의 · 프롬프트 + 기대 판정 (실환자 아님, 어디서든 사용 가능)
│   └─ rag_eval/             RAG_eval_HARI.xlsx · RAG_eval_QWEN.xlsx (비공개) (21문항 RAG 평가 결과, 모델 2종)
├─ 5_figures/                fig4_pipeline_{ko,en} · fig5_judgment_{ko,en} (svg · png · pdf) — 현재 설계. fig1–3 은 이전 계획서용
│   └─ src/                  fig4_pipeline.py · fig5_judgment.py · fig_defs.svg (헤드리스 크롬으로 png/pdf)
├─ 6_app/                    khdp.ai 앱 abx-guideline-agent (MIMIC × 해외 지침 RAG 에이전트) — 게시 심사 요청됨
│   ├─ APP_REQUEST_khdp_ai.md  Chat 에 붙인 제작 요청문(입력 파일 · 화면 3개 · 제약 · 완료 기준)
│   ├─ SYSTEM_PROMPT_judge.md  앱 내부 LLM 프롬프트(자리 4개: 카드 · 검색 구절 · 지침 세트 · 규칙 판정)
│   └─ upload/               드라이브 projects/abx-guideline-agent/ 에 올린 묶음(53 MB): cards/(MIMIC 카드 9,398 + 전건 규칙 판정 + eval20 + 라벨 + 합성 8건) · guidelines/(PDF 7 + 텍스트 5) · code/(판정기 · 질의 · 비교 · AWaRe) · results/(집계)
└─ archive/                  이전 계획서 3종 · 초기 탐색 PDF 4종 · BigQuery 원본 export · 구버전 스크립트
```
상위 폴더(`hosp/`, `icu/`, CHANGELOG · LICENSE · SHA256SUMS)는 PhysioNet 원본이라 손대지 않았다.

---

## 3. MIMIC-IV 트랙 (완료)

**단계별 n**

| 단계 | 폐렴 | 요로감염 |
|---|---:|---:|
| 환자별 첫 ICU 입실 · 성인 | 65,366 | 65,366 |
| 질환 코드 있음 | 8,234 | 7,793 |
| 제외 코드 뺀 뒤 (흡인성 · VAP / 카테터) | 7,085 | 7,463 |
| 폐렴 · 요로감염 겹침 제외 | 6,056 | 6,434 |
| 전신 항생제 있음 / 배양 있음 | 5,984 / 5,877 | 6,328 / 6,283 |
| 감염 의심 시각 있음 (culture_first / antibiotic_first) | 5,761 (4,752 / 1,009) | 6,092 (5,464 / 628) |
| **48h 이내 = 최종 코호트** | **4,875** | **4,523** |
| 패혈증: sepsis3 / 간이 SOFA / 진단코드 | 3,666 / 3,858 / 1,721 | 3,180 / 3,496 / 1,526 |

- 패혈증 주 라벨은 sepsis3(mimic-code 공식 표, BigQuery `physionet-data.mimiciv_3_1_derived.sepsis3`). 간이 SOFA 와 85% / 82% 일치, 진단코드와 50% / 54% 일치. SOFA 창이 ICU 와 안 겹치는 18% 는 빼지 않고 플래그(`sofa_window_covers_icu`).
- 초기 요법 상위(sepsis3 양성): 폐렴 vancomycin 67% · cefepime 38% · azithromycin 31%, 요법 1위 cefepime + vancomycin; 요로감염 vancomycin 44% · ceftriaxone 37%, 요법 1위 ceftriaxone 단독. AWaRe 는 Watch 가 75–85%.
- EMAR 실제 투여는 처방보다 중앙값 1.1h 늦음. 처방 시각 이전에 "보고"된 값만 카드에 넣는 규칙(storetime)을 적용하면 환자 21% 에서 값이 하나 이상 빠진다 — 적용함.
- 사례 카드 9,398건(`mimic_final_cards.zip`), 임상의 평가 표본 20건(폐렴 · 요로감염 × sepsis3 유무, 5건씩).
- **WHO AWaRe 분포(2025 분류, `2_mimic/results/aware_table.md`)**: 성분 건수 기준 폐렴 Access 14.1% / Watch 84.9% / Reserve 1.0%, 요로감염 20.2% / 78.3% / 1.5%. 환자 기준으로 Watch 를 하나라도 쓴 비율 폐렴 94.4% · 요로감염 88.7%, Access 만 쓴 비율 5.4% · 10.9%. sepsis3 양성에서 Watch 가 조금 더 높고(요로감염 79.8% vs 73.5%), 시기별로는 2020–2022 폐렴에서 Access 가 18.3% 로 가장 높다. Watch 의 주인은 vancomycin(폐렴 환자 63%, 요로감염 40%).
- **해외 지침 규칙 판정(본 결과, `4_guideline/rule_judge/summary_intl_*.txt`)**

| | 폐렴 × M03 (ATS/IDSA 2019 표 4) | 요로감염 × M07 (IDSA cUTI 2025 표 1.1) |
|---|---|---|
| 주 분석 (ICU 입실 = 중증) | 준수율 **12.5%** (594/4,740; 판정 불가 0) · 누락 9.2% · 과잉 13.0% · 다른 약제 65.3% | 준수율 **39.4%** (1,677/4,254; 판정 불가 94) · 과잉 49.8% · 다른 약제 10.8% |
| 민감도 strict (카드 값으로만 중증도) | 13.3% (판정 불가 629) | 동일 |
| 민감도 M07 Remark 허용 (패혈증에서 anti-MRSA 추가 인정) | — | 56.3% (판정 불가 432) |
| 비준수 상위 | cefepime + vancomycin 383 · pip/tazo + vancomycin 273 · azithromycin + cefepime + vancomycin 170 (표준 β-lactam + macrolide/FQ 조합이 아님) | pip/tazo + vancomycin 219 · cefepime + vancomycin 195 · ceftriaxone + vancomycin 120 (+ vancomycin 과잉) |

  미국 ICU 의 경험적 anti-MRSA · 항녹농균 투여가 지침 표준 요법과 어긋나는 것이 주 원인. 근사 두 가지를 밝힌다: 지침의 "호흡기 검체에서 MRSA/녹농균 분리 이력" 은 카드의 "1년 내 분리(검체 불문)" 로, "지역에서 검증된 위험인자" 는 판단할 수 없어 중증 + 최근 입원·정맥항생제에서만 범위 추가를 허용했다. 국내 규칙표를 MIMIC 에 돌린 파일(`*_kr-on-mimic_TEST.*`)은 코드 시험이지 결과가 아니다.

다시 돌리기: `cd 2_mimic/code && python3 extract_mimic_cohort.py --mimic ../../.. --out ../data && python3 build_notebook.py` (sepsis3 표는 `docs/bigquery_sepsis3.sql` 결과를 `data/sepsis3_mimic_code.csv` 로).

---

## 4. K-MIMIC 트랙 (진행 중)

**현재(10/17 오전).** 플랫폼은 기관별 데이터셋(`kmimic-emr-001 … -202`)이고 khdp.ai 가 pod 에서 DuckDB 로 CSV 를 읽어 실행한다. 003 의 CSV 3개는 나왔지만 에이전트 경유라 약 3시간이 걸렸다(병목은 SQL 이 아니라 LLM 이 결과를 중계하는 구조). 그래서 나머지 기관은 `run_extract.py`(연결 함수 하나만 채우면 쿼리 3개를 기관마다 돌려 CSV 로 바로 저장)로 에이전트 없이 돌린다. 발표에는 003(+ 끝난 기관)만 넣고 "같은 코드로 확장"으로 적는다.

**K-MIMIC 집계는 플랫폼 반출 절차를 거친 뒤 공개한다.** (이 저장소에는 K-MIMIC 수치가 없다.)

**왜 다시 뽑는가.** (1) 의심 시각 짝짓기에 EMAR 투여 시각을 썼는데 001 · 005 · 009 의 EMAR 시각이 오염돼(0093~6280년) 짝이 깨짐 → 처방 시각으로. (2) 직장 VRE/CRE · 비강 MRSA 같은 선별 검사가 배양으로 들어감 → 제외. (3) SOFA 항목이 없어 전부 비는 컬럼이 생김 → 빼고 진단코드 라벨 + 승압제 플래그로. (4) 항생제가 4개 기관 미완.

**이제 할 일.** `3_kmimic/KMIMIC_EXTRACTION.md` 의 ①~⑤: SQL 3개를 기관별 데이터셋(`kmimic-emr-001 … -202`)마다 실행 → 기관별 CSV 이어 붙이기 → derive → 카드 → 국내 규칙 판정 → 집계. `K-MIMIC-MORTAL`(SNUH 사망 subset)은 쓰지 않고 `SYN-ICU`(합성)는 문법 확인용. 로직은 합성 표로 검증했다(ICU 병합, 최신 배치, 나이 파싱, 제외 규칙, 약품명 보완, 선별 검체). 플랫폼에서 돌릴 때 손볼 수 있는 것은 SQL 방언(파일 머리의 치환표)과 기계환기 ITEMID 뿐이다.

**반출.** 집계 텍스트만(`summary_kr_*.txt`, 단계 n · 요법 상위 · 기관별 판정 분포). 환자 단위 CSV · 카드 · 판정 파일은 플랫폼 안에 둔다.

---

## 5. 가이드라인 · 판정 트랙

- **국내 규칙표(완료).** `rule_judge_kr.py` 가 K02 표 3(중증도: 주기준 기계환기 · 승압제, 부기준 9개 중 3개) · 표 4(입원 비중증 / 중증 / 녹농균 위험 / MRSA 위험 행) · K04 표 5(상 · 하부 요로감염, 패혈증 유무)를 코드로 옮긴 것. 옵션 `--icu-severe`(ICU 입실 = 중증), `--class-equiv`(teicoplanin ≈ vancomycin, cefotaxime ≈ ceftriaxone, clarithromycin ≈ azithromycin). 20건 시험 판정 완료.
- **해외 규칙표(완료).** `rule_judge_intl.py` 가 M03 표 4(입원 비중증 / 중증 × MRSA · 녹농균 분리 이력 × 최근 입원 + 정맥항생제)와 표 1(중증 기준, 국내 표 3 과 동일), M07 표 1.1(패혈증 / 비패혈증 정맥 / 비패혈증 경구 × Preferred · Alternative)을 코드로 옮긴 것. 판정값 · 옵션은 국내 판정기와 같고 `--sepsis-broad-ok`(M07 Remark 허용)가 추가. M07 은 이미지 PDF 라 `text/cuti_intl.txt` 로 옮겨 적었으니 RAG 팀 · 임상의가 원문과 한 번 대조할 것.
- **RAG(지식층, RAG 팀).** 지침 PDF 7종(K02 · K04 · M03 · M04 · M07 · W01 · W02)을 1,000자(겹침 200자) 청크로 잘라 BGE-M3(1024차원)로 임베딩, FAISS 전수 검색, 소스 그룹별 top-3 × 3그룹 = 9청크를 LLM 에 전달. 한국어 질문은 영어 번역 질의를 더해 두 번 검색. 청크 수 K-MIMIC 95 / MIMIC 226 / WHO 1,964(M07 은 OCR). 생성 모델 2종 비교: HARI-q3-8b(서울대병원 한국어 의료 LLM, Qwen3-8B 기반)와 Qwen3.5-9B, temperature 0.2.
  검증은 21문항(7 PDF × 3)을 임상의 3명이 5기준(정확성 · 관련성 · 완전성 · 근거 충실성 · 임상적 유용성, 각 1–5점)으로 독립 채점한 것(`rag_eval/`, 315점 × 모델 2종, 전부 입력 완료).

  | 모델 | 정확성 | 관련성 | 완전성 | 근거 충실성 | 유용성 | 전체 평균 |
  |---|---|---|---|---|---|---|
  | HARI-q3-8b | 3.57 | 3.94 | 3.52 | 3.49 | 3.52 | **3.61** |
  | Qwen3.5-9B | 3.30 | 3.92 | 3.27 | 3.14 | 3.03 | **3.33** |

  관련성은 높고 근거 충실성(인용 위치 정확성)이 가장 낮다. 이것은 "문서를 찾아 답하는 능력"의 평가이지 환자 판정의 평가가 아니다. 환자 판정의 평가는 아래 규칙 vs RAG 비교가 맡는다.
- **규칙 vs RAG 비교.** `rag_match/build_queries.py` 가 카드 20건을 검색 질의 + 판정 프롬프트(8종 판정값 JSON)로 바꿔 둠. RAG 팀이 LLM 판정을 `llm_verdicts.jsonl` 로 내면 `compare_verdicts.py` 로 일치율 · 혼동표 · 불일치 목록이 나온다. 불일치는 임상의 심사.

---

## 5-2. 앱 (khdp.ai, `6_app/`)

매뉴얼의 방식대로 드라이브에 파일을 올리고 요구사항 한 번으로 에이전트가 앱을 만들었다(v1 → 데이터 소스 고정 요청(FIX_REQUEST_2) → **v3 게시 완료**). Apps 런타임에서 LLM 을 직접 부를 수 없어 판정은 규칙 엔진, 근거는 BM25 검색(40줄 청크, 질환별 코퍼스 고정 · 교차 차단, 표 4 · 표 1.1 앵커 청크 1순위), LLM 판정은 "프롬프트 복사 → Chat → JSON 붙여넣기 → 규칙과 비교" 로 구현됐다. FastAPI + 순수 JS, API 8개(/api/judge, /api/judge-all, /api/dashboard, /api/question …). 검증: 준수율 12.5% / 39.4%, AWaRe Access 14.1% 가 집계 파일과 일치, 교차 검색 없음, "severe CAP MRSA vancomycin" → Table 4 1순위. **아직 연결 안 된 파일**: cards_all.jsonl(9,398), cards_eval20.jsonl(20), all_verdicts_intl_icusevere.jsonl, summary_intl_strict · broadok, results/kr/ — 드라이브 upload/ 에는 있으므로 경로를 지정해 연결 요청(v4). 화면 3개: ① 사례 판정(카드 선택 → 규칙 판정 → 지침 구절 검색(파일 · 줄 번호) → LLM 설명 JSON, 규칙과 일치하면 초록 · 다르면 주황, 일괄 판정과 일치율 표) ② 결과 대시보드(판정 분포 · AWaRe · 단계별 n 을 집계 파일에서 읽어 표시) ③ 지침 질의(인용 필수 QA). 설계 원칙: 판정은 규칙 코드, LLM 은 설명과 인용만; 출력은 판정값 8종 JSON 고정; 표 4 · 표 1.1 앵커 청크 항상 포함. 개발 주소 khdp.ai/apps/runtime/dev/abx-guideline-agent/, 게시 심사 요청 상태.

---

## 6. 결과 제시 계획

| 번호 | 내용 | 출처 |
|---|---|---|
| 표 1 | 코호트 특성(나이 · 성별 · 기저질환 · 패혈증 · 사망) — MIMIC / K-MIMIC 기관별 | 2_mimic/results/summary.md, K-MIMIC summary_cohort.txt |
| 표 2 | 단계별 n (두 데이터 나란히) | funnel.csv, derive 출력 |
| 표 3 | 초기 요법 상위 5 · 성분 수 · 계열(anti-MRSA · 항녹농균 · glycopeptide) · AWaRe 비율 | summarize 출력, aware_table.py (MIMIC: 2_mimic/results/aware_table.md 완료) |
| 표 4 | 판정 분포 · 준수율(K-MIMIC × 국내, MIMIC × 해외) + 민감도(strict / 배양 짝 성립만 / M07 Remark) | summary_kr_*.txt (K-MIMIC, 플랫폼), 4_guideline/rule_judge/summary_intl_*.txt (MIMIC, 완료) |
| 표 5 | 규칙 판정 vs LLM+RAG 판정 일치(20건), RAG 품질 평가(21문항) | 앱 화면 1 일괄 판정(compare_verdicts.py), rag_eval/ |
| 그림 6 | 앱 화면 캡처(사례 판정 · 대시보드) | 6_app, khdp.ai |
| 그림 4 | 데이터 파이프라인(국 · 영) | 5_figures/fig4_pipeline_* |
| 그림 5 | 판정 워크플로우(국 · 영) | 5_figures/fig5_judgment_* |

---

## 7. 규정

- PhysioNet DUA: MIMIC 환자 단위 자료(카드 포함)는 자격자 외 공유 금지, 외부 LLM API 전송 금지. 팀에는 집계 · 코드만.
- KHDP: 가명 데이터 국외 이전 불가. 환자 단위 CSV 는 플랫폼 밖으로 나가지 않고, 집계 · 코드 · 평가 결과만 반출 절차로.
- 카드는 해시 ID · 상대 시간만. 퇴원 진단 · 사망 · T+0 이후 결과 없음.

---

## 8. 남은 일 (우선순위)

1. **K-MIMIC**: 003 CSV 로 ②~⑥(derive → 카드 → 국내 판정 → 집계 → AWaRe) 먼저 끝내 summary 5종 확보. 남는 시간에 `run_extract.py` 로 005 → 202 → 006 → 004 → 009.
2. **앱 v4**: 누락 파일 5종 연결(cards/cards_all.jsonl, cards/cards_eval20.jsonl, cards/all_verdicts_intl_icusevere.jsonl, results/summary_intl_strict.txt, results/summary_intl_icu_severe_broadok.txt) → eval20 탭 · 전건 색인 · 민감도 비교. 그다음 eval20 20건에 LLM 판정 붙여넣기 → 일치율 표(표 5), 화면 캡처(그림 6).
3. 임상의: 앱이 낸 불일치 사례 심사.
4. 표 1–5 · 그림 4–6 조립, 발표 자료.

---

## 9. 기록

- 10/16: MIMIC 추출 · 노트북 · sepsis3 결합 · 카드 · 국내 규칙 판정 · 그림 4/5. khdp.ai 로 K-MIMIC 코호트 1차(14,957).
- 10/17 새벽: khdp.ai 결과 검토(EMAR 시각 오염 · 선별 검체 · SOFA 부재), 키트(3_kmimic) 정비, 교차 판정 폐기, AWaRe 공통 잣대 확정.
- 10/17: 해외 규칙표 `rule_judge_intl.py` 작성(M03 표 4 · 표 1, M07 표 1.1), MIMIC 카드 9,398건 판정(폐렴 12.5% · 요로감염 39.4%).
- 10/17 낮: 앱 v3 게시(운영 running). 데이터 소스 화면별 고정, LLM 붙여넣기 워크플로, 대시보드 원본 집계 분리.
- 10/17 오전: AWaRe 표(MIMIC) · WHO 2025 분류 대조, 합성 데모 카드 8건, `run_extract.py`(에이전트 우회), K-MIMIC 003 추출 완료(khdp.ai, 3시간), khdp.ai 앱 `abx-guideline-agent` 제작 · 게시 심사 요청, 가이드라인 아이콘.
- 10/17: 폴더를 `datathon2026/` 로 통합(이전 경로: `mimic_pna_uti 2/` → `2_mimic/`, `kmimic_kit/` → `3_kmimic/`, `rule_judge/` · `rag_match/` · `가이드라인 모음집/` → `4_guideline/`, `figures/` → `5_figures/`). K-MIMIC 을 직접 추출하기로 하고 SQL 을 쿼리 3개로 다시 씀(합성 표로 검증). `RUN_ON_PLATFORM.md` 는 `KMIMIC_EXTRACTION.md` 로 대체.
