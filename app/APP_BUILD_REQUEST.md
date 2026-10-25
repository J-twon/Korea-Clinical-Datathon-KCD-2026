# 앱 제작 요청문 (khdp.ai Apps · MIMIC 트랙 · 해외 지침 RAG 에이전트)

드라이브 `projects/abx-guideline-agent/` 에 cards/ guidelines/ code/ results/ 와 SYSTEM_PROMPT_judge.md 를 올린 뒤 아래를 Chat 에 보낸다. 앱의 판정 · 검색 · 비교 로직은 이 저장소의 코드를 그대로 쓴다.

---
내 드라이브 projects/abx-guideline-agent/ 의 파일로 "ICU 초기 항생제 지침 준수 판정 에이전트" 웹 앱을 만들어 주세요. 앱 이름 abx-guideline-agent. 판정 로직과 프롬프트는 제공된 파일을 그대로 쓰고 새로 만들지 마세요.

[입력 파일]
- cards/cards_all.jsonl : MIMIC-IV 환자 카드 9,398건(1줄 = 1환자 JSON, 필드 설명은 cards/card_schema.md). cards/all_verdicts_intl_icusevere.jsonl : 전건의 규칙 판정(case_id 로 연결). cards/labels.csv : 층화용 라벨(sepsis3 등, LLM 에는 주지 말 것).
- cards/cards_eval20.jsonl + cards/eval20_verdicts_intl.jsonl : 임상의 평가 표본 20건. cards/demo_cards.jsonl : 시연용 합성 8건(빠른 데모용). 필드는 cohort_group(pneumonia/uti), empirical_regimen[{ingredient, route, dose, ordered}], history{…}, vasopressor{any}, respiratory_support{invasive_ventilation}, vitals_before_t0, labs_before_t0, cultures_before_t0, age, sex.
- cards/demo_rule_verdicts_intl.jsonl : 규칙 판정기의 기대 판정(해외 지침). cards/demo_queries.jsonl : 카드별 검색 질의.
- guidelines/pdf/*.pdf : 지침 원본 PDF 7개(K02 K04 M03 M04 M07 W01 W02; M07 은 이미지 PDF). guidelines/*.txt : 지침 원문 텍스트 5개 (cap_intl.txt = ATS/IDSA CAP 2019, cuti_intl.txt = IDSA cUTI 2025, aware_2025.txt = WHO AWaRe 2025, cap_kr.txt · uti_kr.txt = 국내 지침).
- code/rule_judge_intl.py, code/rule_judge_kr.py : 규칙 판정기(표준 라이브러리만). 함수 judge_cap(card), judge_uti(card) 를 import 해서 호출. 옵션은 모듈 변수 ICU_IMPLIES_SEVERE=True 로.
- code/build_queries.py : 카드 → 검색 질의 · 프롬프트. code/aware_table.py + aware_2025.csv : AWaRe 집계. code/compare_verdicts.py : 규칙 vs LLM 일치율.
- results/*.txt, *.md : MIMIC-IV 전체(9,398명) 집계 결과(환자 단위 아님).
- SYSTEM_PROMPT_judge.md : LLM 에 넣을 프롬프트. {card} {chunks} {guideline_set} {rule_verdict} 네 자리만 채워서 그대로 사용.

[화면 1 · 사례 판정]
1. 왼쪽에서 카드를 고른다: 기본은 cards_all.jsonl (case_id 검색 · 집단(폐렴/요로감염) · 규칙 판정값 필터 · '무작위 1건'), 탭으로 eval20 과 demo 도 선택 가능. 카드 내용을 보기 좋게 표시(요법 · 과거력 · 승압제 · 배양 · 활력징후).
2. "판정" 버튼 → 세 단계를 순서대로 실행하고 각 단계 결과를 보여 준다.
   ① 규칙 판정: rule_judge_intl.judge_cap/judge_uti 호출 결과(verdict, reason, row, candidates).
   ② 지침 검색: SYSTEM_PROMPT_judge.md 의 "검색(RAG) 단계 지시"대로 guidelines/ 를 40줄 청크로 나눠 demo_queries.jsonl 의 질의로 상위 9청크를 뽑고(폐렴은 cap_intl.txt 470~520행, 요로감염은 cuti_intl.txt 표 부분을 항상 포함), file · line_start · line_end · text 를 표시.
   ③ LLM 판정: 프롬프트에 카드 · 청크 · 규칙 판정 결과를 채워 플랫폼 LLM 호출, JSON 을 파싱해 판정값 · 이유 · 인용 구절(파일 · 줄) · 누락/추가 약제 · AWaRe 를 카드 형태로 표시. 규칙 판정과 같으면 초록, 다르면 주황으로 표시하고 disagreement_note 를 보여 준다.
3. 하단에 "일괄 판정" 버튼(기본 eval20 20건, 숫자 입력 시 cards_all 에서 무작위 N건) → llm_verdicts.jsonl 로 저장하고 compare_verdicts.py 결과(일치율 · 혼동표 · 불일치 목록)를 표로 표시.

[화면 2 · 결과 대시보드]
results/summary_intl_icu_severe.txt 의 판정 분포 · 준수율을 집단별 막대로, results/aware_table.md 의 Access/Watch/Reserve 비율을 누적 막대로, results/summary.md 의 단계별 n 표를 표로 보여 준다. 숫자는 파일에서 읽고 하드코딩하지 않는다.

[화면 3 · 지침 질의]
자유 질문 입력 → 같은 검색기로 guidelines/ 에서 상위 5청크 → "제공된 구절만으로 답하고 문장 끝에 [file:line] 을 붙여라"는 프롬프트로 LLM 답변. 구절에 없으면 "지침에서 찾지 못함"이라고 답하게 한다.

[제약]
- 판정 로직을 다시 구현하거나 바꾸지 말 것. 규칙 판정기는 import 만.
- LLM 호출은 temperature 0.2, JSON 만 받도록 하고 파싱 실패 시 1회 재시도 후 "판정 불가(형식 오류)"로 표시.
- 환자 카드 내용은 앱 로그에 남기지 말 것. 결과 저장은 내 드라이브 projects/abx-guideline-agent/runs/ 에 case_id · verdict · 시간만.
- 실행 코드와 앱은 내 드라이브 projects/abx-guideline-agent/app/ 에 저장하고 Apps 개발 자리에 올린 뒤 주소를 알려 줄 것.

[완료 기준]
eval20 20건이 화면 1 에서 모두 오류 없이 판정되고, 일괄 판정의 일치율 표가 나오며, 화면 2 의 숫자가 results/ 파일과 일치한다. 완료 후 한 줄씩 보고: 사용한 LLM 모델명, 검색 방식(임베딩/BM25), 8건 중 규칙 판정과 일치한 건수.
---

## 프롬프트를 이렇게 짠 이유 (팀 설명용)
- 역할을 셋으로 나눠 LLM 에는 "설명과 인용"만 맡긴다. 판정은 규칙 코드가 내고, LLM 은 그 판정을 참고하되 베끼지 못하게 하고 다르면 이유를 쓰게 한다 → 일치율 자체가 평가 지표가 된다.
- 검색 구절에 파일 · 줄 번호를 강제한다 → 임상의 평가에서 가장 낮았던 "근거 충실성"을 화면에서 바로 확인할 수 있다.
- 출력을 JSON 8값으로 고정한다 → 사람 평가 · 집계 · 비교 코드가 그대로 돌아간다.
- 앵커 청크(표 4 · 표 1.1)를 항상 포함한다 → 검색이 흔들려도 권고 행은 빠지지 않는다.
- 실데이터는 플랫폼 안에서만 다룬다. 카드는 해시 ID · 상대 시간뿐이고, 결과 로그에는 case_id 와 판정값만 남긴다.
