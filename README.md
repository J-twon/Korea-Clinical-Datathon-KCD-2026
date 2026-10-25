# A Guideline-Informed AI Agent for Empiric Antibiotic Decision Support in the ICU

Korea Clinical Datathon 2026 · Team 5 · MIMIC-IV (US) and K-MIMIC (Korea)

We ask whether the **first empiric antibiotic regimen** given to adult ICU patients with community-acquired **pneumonia** or **urinary tract infection** follows national guidelines, and whether an AI agent with retrieval-augmented generation (RAG) can make and explain that judgement. The pipeline turns each admission into a leakage-free **case card**, judges it with a **rule engine** transcribed from the guideline tables, and lets an **LLM + RAG layer** explain the judgement with cited guideline passages. Clinicians evaluated the RAG and adjudicate disagreements.

<p align="center"><img src="5_figures/fig4_pipeline_en.png" width="820" alt="Data pipeline"></p>

## Design in one table

| | K-MIMIC (Korea, 7 hospitals) | MIMIC-IV v3.1 (BIDMC, US) |
|---|---|---|
| Guidelines (judgement) | KDCA/KSAT CAP 2025 (K02) · UTI 2025 (K04) | ATS/IDSA CAP 2019 (M03) · IDSA cUTI 2025 (M07) |
| Common yardstick | WHO AWaRe 2025 (W01, W02) | same |
| Sepsis label (stratification only) | ICD sepsis codes | Sepsis-3 (mimic-code) |
| Where it runs | inside the KHDP platform; only aggregates leave | locally by a credentialed user |

No cross-judgement: Korean data are judged against Korean guidelines and US data against US guidelines, because recommendations encode local resistance epidemiology.

**Cohort.** First ICU stay per patient, adults, pneumonia (J13–J16, J18.0/.1/.8/.9) or UTI (N10, N12, N39.0) codes; aspiration/VAP and catheter-associated infections excluded. Suspected infection = culture→antibiotic within 72 h or antibiotic→culture within 24 h; community-acquired = suspicion within 48 h of hospital arrival. Empiric regimen = all systemic antibiotics started within 24 h of the first antibiotic.

**Case card.** Hashed ID, times relative to the first antibiotic order (T+0), and only values *reported* before T+0 (vitals, labs, specimen types, history, comorbidities, regimen). Discharge diagnoses, death, culture results and the sepsis label are withheld so that the rule engine, the LLM and the clinicians see the same information.

**Judgement.** Set comparison of the regimen against the guideline row that matches the card (severity, MRSA/Pseudomonas risk, sepsis, route): `준수(추천)` recommended · `준수(대안)` alternative · `비준수(누락)` missing agent · `비준수(과잉)` unexplained extra agent · `비준수(다른 약제)` different agents · `정당한 이탈` justified deviation · `해당 없음` not applicable · `판정 불가` undeterminable. Unknown conditions are resolved by evaluating every candidate row; if the rows disagree the case is undeterminable, never guessed.

<p align="center"><img src="5_figures/fig5_judgment_en.png" width="820" alt="Judgement workflow"></p>

## Results (MIMIC-IV, 9,398 admissions)

| | Pneumonia (n = 4,875) | UTI (n = 4,523) |
|---|---|---|
| Sepsis-3 positive | 3,666 (75%) | 3,180 (70%) |
| Adherence to US guidelines (ICU admission treated as severe) | **12.5%** | **39.4%** |
| Sensitivity: severity from card values only | 13.3% | — |
| Sensitivity: anti-MRSA add-on allowed in sepsis (IDSA remark) | — | 56.3% |
| Most frequent non-adherent regimens | cefepime + vancomycin · pip/tazo + vancomycin | pip/tazo + vancomycin · cefepime + vancomycin |
| WHO AWaRe, share of regimen components (Access / Watch / Reserve) | 14.1 / 84.9 / 1.0 % | 20.2 / 78.3 / 1.5 % |

Non-adherence is dominated by empiric anti-MRSA and anti-pseudomonal coverage added to the standard β-lactam ± macrolide regimen. Full tables: [`2_mimic/results/summary.md`](2_mimic/results/summary.md), [`aware_table.md`](2_mimic/results/aware_table.md), [`4_guideline/rule_judge/`](4_guideline/rule_judge/).

**RAG (7 guideline PDFs, BGE-M3 + FAISS, top-9 chunks).** Two local generators compared on 21 guideline questions with identical retrieval. The Korean medical model HARI-q3-8B beat Qwen3.5-9B on every automatic metric (cosine 0.747 vs 0.711, BERTScore 0.884 vs 0.879) and in clinician scoring (3 raters × 5 criteria, 1–5): mean 3.61 vs 3.33, with groundedness (citation accuracy) the weakest criterion for both.

**Agent.** Three functions: adherence report, guideline-based recommendation, similar-case prescriptions. Deployed as a khdp.ai app (`6_app/`): rule judgement, BM25 guideline retrieval with file/line citations, dashboard from the aggregate files, and an LLM judgement loop that compares the model's 8-value JSON verdict with the rule engine.

## Repository

```
1_plan/        study plan and team brief (PDF)
2_mimic/       MIMIC-IV extraction (stdlib Python, ~7 min), notebook builder, aggregate results
3_kmimic/      K-MIMIC kit for the KHDP platform: 3 standalone SQL queries, derive → cards → judge → AWaRe, run guide
4_guideline/   rule engines (rule_judge_kr.py, rule_judge_intl.py), RAG query builder, verdict comparison, synthetic demo cards
5_figures/     pipeline and judgement figures (ko/en, SVG/PNG/PDF) and their generators
6_app/         khdp.ai app request prompt, in-app LLM prompt, data-source spec
docs/          presentation deck, detailed Korean project notes
```

Run order (MIMIC): `2_mimic/code/extract_mimic_cohort.py --mimic <mimic-iv-3.1 dir> --out 2_mimic/data` → `build_notebook.py` → `4_guideline/rule_judge/rule_judge_intl.py --icu-severe cards.jsonl verdicts.jsonl` → `3_kmimic/aware_table.py cards.jsonl`. Run order (K-MIMIC): see [`3_kmimic/KMIMIC_EXTRACTION.md`](3_kmimic/KMIMIC_EXTRACTION.md). Everything is standard-library Python; the smoke test in `3_kmimic/test_data/` (3 synthetic patients) and the 8 synthetic cards in `4_guideline/rag_match/demo/` run without any real data.

## Data and licensing

- **No patient-level data are in this repository.** MIMIC-IV derivatives (extracted CSVs, case cards, verdict files, notebook outputs) are available only to PhysioNet-credentialed users; K-MIMIC data never leave the KHDP platform, and K-MIMIC aggregates will be added after the platform's export review.
- **Guideline PDFs and their text extracts are not redistributed.** Obtain them from the issuers (KDCA/KSAT, ATS/IDSA, IDSA, WHO) and run `pdftotext -layout` to the file names expected in `4_guideline/text/`; the rule engines cite table and line positions of those files.
- Clinician evaluation sheets are private. Scores are reported in aggregate only.
- The WHO AWaRe mapping in `3_kmimic/aware_2025.csv` follows the 2025 WHO list, with route-dependent entries for fosfomycin and minocycline.

## Team

Minso Kim, Soyoung Park, Taewon Jung (data), Jisu Ha, Seungmin Lee, Woojin Kim (clinical evaluation). Korea Clinical Datathon 2026, Pyeongchang, 16–17 October 2026.
