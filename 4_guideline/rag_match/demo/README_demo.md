# 에이전트 시연용 합성 카드 8건 (실환자 아님 → 어떤 LLM · 화면에도 자유롭게 사용)

| 파일 | 내용 |
|---|---|
| demo_cards.jsonl | 카드 8건 (폐렴 5 · 요로감염 3). K-MIMIC 최소 카드와 같은 형식(활력 · 검사 없음) |
| demo_queries.jsonl | 카드별 조건 요약(features) · 지침별 검색 질의(K02/M03/W01 또는 K04/M07/W01) · LLM 판정 프롬프트(prompt) |
| demo_rule_verdicts_kr.jsonl | 국내 규칙 판정기의 기대 판정 (`--icu-severe --class-equiv`) |

기대 판정: demo01 준수(추천) · demo02 비준수(과잉, teicoplanin 추가) · demo03 준수(대안, 녹농균 위험 pip/tazo + levofloxacin) · demo04 비준수(누락, MRSA · 녹농균 이력인데 azithromycin 없음) · demo05 준수(추천) · demo06 비준수(과잉, 패혈증 meropenem + vancomycin) · demo07 준수(추천, 경구 ciprofloxacin) · demo08 해당 없음(cefazolin 단독).

## 에이전트 돌리는 법
1. 카드 하나당: `queries` 의 질의로 RAG 검색 → 상위 청크를 `prompt` 의 `<<여기에 검색 결과 상위 5개를 넣는다>>` 자리에 넣어 LLM 호출.
2. LLM 은 프롬프트가 정한 JSON(판정값 8종 중 하나 + 근거 구절 + 설명)으로 답한다. 한 줄씩 `llm_verdicts.jsonl` 에 저장 (`case_id`, `verdict` 필수).
3. 비교: `python3 ../compare_verdicts.py llm_verdicts.jsonl demo_rule_verdicts_kr.jsonl` → 일치율 · 혼동표 · 불일치 목록.
실데이터(K-MIMIC 카드)는 플랫폼 안에서 같은 순서로, MIMIC 20건은 로컬에서 `eval20_verdicts_intl.jsonl` 과 비교한다.
