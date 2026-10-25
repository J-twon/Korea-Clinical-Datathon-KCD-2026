#!/usr/bin/env python3
"""WHO AWaRe 비율 표 — 사례 카드(JSONL)의 초기 요법 성분을 WHO AWaRe 2025 분류(aware_2025.csv)로 나눠 집계한다. 표준 라이브러리만.
실행: python3 aware_table.py cards.jsonl [--by=hospital | --by=admission_era] [--labels=labels.csv --label-col=sepsis3] [--map=aware_2025.csv]
  --by        카드 필드로 층화 (K-MIMIC: hospital)
  --labels    case_id(hashed_id) 로 붙이는 라벨 CSV 와 그 컬럼으로 층화 (MIMIC: sepsis3)
출력(markdown): 집단별 환자 수, 성분 건수 기준 Access/Watch/Reserve %, 환자 기준 Access만 % · Watch 포함 % · Reserve 포함 %, Watch · Reserve 상위 성분.
WHO 목표: 국가 전체 항생제 사용량의 70% 이상이 Access(WHO 13차 총괄사업계획 2023 목표 · 2024 UN 정치선언 2030 목표, 국가 단위 소비량 지표). 여기서는 ICU 초기 경험적 요법의 성분 건수 기준이라 참고치로만 쓴다.
"""
import csv, json, sys, os
from collections import Counter, defaultdict

args = [a for a in sys.argv[1:] if not a.startswith("--")]; opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
CARDS = args[0]; BY = opts.get("by"); LABELS = opts.get("labels"); LABEL_COL = opts.get("label-col", "sepsis3")
MAP = opts.get("map", os.path.join(os.path.dirname(os.path.abspath(__file__)), "aware_2025.csv"))
ORAL = {"PO", "ORAL", "NG", "PO/NG"}

amap = {}
for r in csv.DictReader(open(MAP, encoding="utf-8")):
    amap[(r["ingredient"], r.get("route", "") or "")] = r["aware"]
def classify(ing, route):
    """경로에 따라 분류가 다른 성분(fosfomycin · minocycline)은 route 열이 oral/iv 인 행을 쓴다. 표에 없으면 카드의 aware 값, 그것도 없으면 unclassified"""
    rt = "oral" if (route or "").upper() in ORAL else "iv"
    return amap.get((ing, rt)) or amap.get((ing, "")) or None

labels = {}
if LABELS:
    for r in csv.DictReader(open(LABELS, encoding="utf-8-sig")): labels[r.get("hashed_id") or r.get("case_id")] = r.get(LABEL_COL, "")

strata = defaultdict(lambda: {"n": 0, "n_with_regimen": 0, "entries": Counter(), "pt": Counter(), "agents": defaultdict(Counter), "unclassified": Counter()})
for line in open(CARDS, encoding="utf-8"):
    c = json.loads(line); g = c["cohort_group"]
    key = (g, str(c.get(BY, "")) if BY else (labels.get(c["case_id"], "?") if LABELS else "전체"))
    s = strata[key]; s["n"] += 1
    R = {}
    for e in c["empirical_regimen"]:
        cat = classify(e["ingredient"], e.get("route")) or e.get("aware") or "unclassified"
        R[e["ingredient"]] = cat
    if not R: continue
    s["n_with_regimen"] += 1
    for ing, cat in R.items():
        s["entries"][cat] += 1; s["agents"][cat][ing] += 1
        if cat == "unclassified": s["unclassified"][ing] += 1
    cats = set(R.values())
    s["pt"]["access_only"] += cats <= {"access"}; s["pt"]["any_watch"] += "watch" in cats; s["pt"]["any_reserve"] += "reserve" in cats

def pct(a, b): return f"{100 * a / b:.1f}" if b else "-"
hdr = ["집단", BY or (LABEL_COL if LABELS else ""), "환자 n", "요법 있음", "성분 건수", "Access %", "Watch %", "Reserve %", "환자: Access만 %", "환자: Watch 포함 %", "환자: Reserve 포함 %", "Watch 상위 3", "Reserve 상위 3"]
print("| " + " | ".join(h for h in hdr if h) + " |"); print("|" + "---|" * len([h for h in hdr if h]))
for (g, k) in sorted(strata, key=lambda x: (x[0], str(x[1]))):
    s = strata[(g, k)]; tot = sum(s["entries"].values()); n = s["n_with_regimen"]
    row = [g, k, f"{s['n']:,}", f"{n:,}", f"{tot:,}", pct(s["entries"]["access"], tot), pct(s["entries"]["watch"], tot), pct(s["entries"]["reserve"], tot),
           pct(s["pt"]["access_only"], n), pct(s["pt"]["any_watch"], n), pct(s["pt"]["any_reserve"], n),
           ", ".join(f"{a} {pct(v, n)}%" for a, v in s["agents"]["watch"].most_common(3)), ", ".join(f"{a} {pct(v, n)}%" for a, v in s["agents"]["reserve"].most_common(3)) or "-"]
    if not (BY or LABELS): row.pop(1)
    print("| " + " | ".join(row) + " |")
unc = Counter()
for s in strata.values(): unc.update(s["unclassified"])
if unc: print("\n분류 없음(aware_2025.csv 에 추가 필요):", dict(unc.most_common()))
print("\n(성분 건수 = 환자별 초기 요법의 성분 수 합. 환자 기준 % 의 분모 = 요법 있는 환자. 분류 = WHO AWaRe 2025, fosfomycin · minocycline 은 경구/정맥으로 구분)")
