abx-guideline-agent 수정 요청 2 — 데이터 소스를 화면별로 고정하고, LLM 없는 런타임에 맞게 판정 화면을 바꿔 주세요. 아래 표가 유일한 기준입니다. 표에 없는 파일은 쓰지 않고, 표의 파일을 다른 것으로 대체하지 마세요. 경로는 모두 MyDrive/projects/abx-guideline-agent/ 기준입니다.

[데이터 소스 표]
| 화면 | 용도 | 파일 | 비고 |
|---|---|---|---|
| 1 사례 판정 | 카드 목록(기본) | cards/cards_all.jsonl (9,398건) | case_id 검색 · 집단 필터 · "무작위 1건". 전부 메모리에 올리지 말고 색인(case_id, cohort_group, 규칙 판정값)만 먼저 만들 것 |
| 1 사례 판정 | 카드 목록(탭) | cards/cards_eval20.jsonl (20건) · cards/demo_cards.jsonl (8건) | eval20 이 발표용 표본. demo 는 시연용 |
| 1 사례 판정 | 규칙 판정(해외) | 실행: code/rule_judge_intl.py 의 judge_cap / judge_uti (ICU_IMPLIES_SEVERE=True) | 미리 계산된 값이 필요하면 cards/all_verdicts_intl_icusevere.jsonl (전건), cards/eval20_verdicts_intl.jsonl, cards/demo_rule_verdicts_intl.jsonl 을 case_id 로 조인 |
| 1 사례 판정 | 규칙 판정(국내) | code/rule_judge_kr.py (ICU_IMPLIES_SEVERE=True, CLASS_EQUIV=True) | KR 세트일 때만. demo 의 기대값은 cards/demo_rule_verdicts_kr.jsonl |
| 1 사례 판정 | 지침 검색 질의 | code/build_queries.py 의 queries(card) | demo_queries.jsonl 은 8건에만 있으므로 쓰지 말고 함수를 호출해 모든 카드에 질의를 만들 것 |
| 1 · 3 검색 코퍼스 | 해외(INTL) 세트 | guidelines/cap_intl.txt (폐렴 전용) · guidelines/cuti_intl.txt (요로감염 전용) · guidelines/aware_2025.txt (공통) | 폐렴 카드는 cap_intl + aware 만, 요로감염 카드는 cuti_intl + aware 만 검색. 교차 금지 |
| 1 · 3 검색 코퍼스 | 국내(KR) 세트 | guidelines/cap_kr.txt (폐렴) · guidelines/uti_kr.txt (요로감염) · guidelines/aware_2025.txt | 같은 규칙. sepsis_kr.txt 는 쓰지 않음 |
| 1 사례 판정 | 앵커 청크 | 폐렴: cap_intl.txt 470–520행(Table 4), cap_kr.txt 392–457행(표 4) · 요로감염: cuti_intl.txt 의 "Table 1.1" 블록, uti_kr.txt 333–360행(표 5) | 검색 점수와 무관하게 항상 1순위로 표시 |
| 2 대시보드 | MIMIC 전체 결과(INTL) | results/summary_intl_icu_severe.txt (주 분석) · results/summary_intl_strict.txt · results/summary_intl_icu_severe_broadok.txt (민감도) | 판정값 8종 분포 · 준수율 · 시기별 · 판정값별 상위 요법. 9,398건 집계이며 화면 1 의 8건 · 20건 결과로 덮어쓰지 말 것 |
| 2 대시보드 | AWaRe | results/aware_table.md | 집단별 · sepsis3 별 · 시기별 표 3개를 그대로 표로, Access/Watch/Reserve 는 누적 막대 |
| 2 대시보드 | 코호트 · 단계별 n | results/summary.md 의 "단계별 n" 표와 "집단별 요약(sepsis3)" 표 | |
| 2 대시보드 | K-MIMIC(KR 세트) | results/kr/ 폴더의 summary_kr_*.txt, summary_cohort.txt, summary_aware_*.txt | 아직 없음. 폴더가 비어 있으면 "K-MIMIC 집계 대기" 로 표시하고, 파일이 올라오면 같은 파서로 읽을 것 |
| 2 대시보드 | 실시간 판정 패널(별도 작은 패널) | 화면 1 에서 일괄 판정한 결과(eval20 또는 demo) | 전체 집계와 분리해 "표본 n건" 으로 표기 |

[판정 화면 — LLM 이 없을 때의 동작]
Apps 런타임에 LLM 이 없으므로 화면 1 은 다음 세 칸으로 구성합니다.
1. 규칙 판정 칸: verdict · reason · row · candidates. 성분별 AWaRe(code/aware_2025.csv) 를 색 태그로.
2. 근거 칸: 앵커 청크 + BM25 상위 청크(세트 · 질환에 맞는 문서만). 각 청크에 file · line_start–line_end 표시, 카드의 성분명과 권고 약제명을 본문에서 하이라이트.
3. LLM 판정 붙여넣기 칸: "프롬프트 복사" 버튼이 SYSTEM_PROMPT_judge.md 에 카드 · 청크 · 규칙 판정을 채운 완성 프롬프트를 클립보드로 복사. 사용자가 khdp.ai Chat 에서 받은 JSON 을 붙여 넣으면 verdict 를 파싱해 규칙 판정과 비교(같으면 초록 · 다르면 주황, disagreement_note 표시)하고 runs/llm_verdicts.jsonl 에 case_id · verdict · 시간만 저장. 일괄 비교 표는 code/compare_verdicts.py 로.
플랫폼 LLM 을 앱에서 호출할 수 있는 방법이 생기면 3번 칸을 자동 호출로 바꾸되, 프롬프트 파일과 JSON 스키마는 그대로 둡니다.

[화면 3 지침 질의 — LLM 없을 때]
세트(INTL/KR) 와 질환(폐렴/요로감염/공통) 선택 → 해당 문서만 BM25 → 상위 5청크를 file · 줄 번호 · 본문으로 표시, 질의어 하이라이트. 답 문장 생성은 하지 않고 "근거 구절" 로만 보여 줍니다. 결과가 없으면 "지침에서 찾지 못함".

[검증 후 보고할 것]
- 화면 1: cards_all 에서 무작위 1건, eval20 20건 일괄 판정이 INTL/KR 모두 동작. 폐렴 카드의 근거 칸에 cuti/uti 문서가 섞이지 않을 것(반대도).
- 화면 2: 준수율 숫자가 results/summary_intl_icu_severe.txt 와 같을 것(폐렴 12.5%, 요로감염 39.4%). AWaRe 폐렴 Access 14.1%.
- 화면 3: "severe CAP MRSA vancomycin" 질의가 cap_intl.txt Table 4 줄을 1순위로 돌려줄 것.
- 사용한 파일 목록과 쓰지 않은 파일 목록을 표로.
