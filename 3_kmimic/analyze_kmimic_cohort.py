"""K-MIMIC 폐렴/요로감염 코호트 — CSV 분석 코드 (표준 라이브러리만 사용, 추가 설치 불필요)

두 가지로 쓴다.
  (A) khdp.ai가 cohort.csv(t_infection_suspected, t_first_antibiotic 포함)와 antibiotics.csv를 줬을 때:
        python analyze_kmimic_cohort.py summarize --cohort cohort.csv --abx antibiotics.csv
  (B) 원자료만 있을 때(입원별 기본 정보 + 항생제 이벤트 + 배양 이벤트) culture_first / antibiotic_first 규칙으로 t_infection_suspected를 직접 계산:
        python analyze_kmimic_cohort.py derive --cohort admissions.csv --abx antibiotics.csv --cultures cultures.csv --out cohort_derived.csv
      → cohort_derived.csv를 만들고 바로 요약까지 출력한다.

시간 컬럼은 전부 "입원 시각 = 0 기준 상대 시간(시간 단위)" 숫자여야 한다. 컬럼 이름이 다르면 아래 COL만 고친다.
"""
import argparse, csv, os, re, sys
from collections import Counter, defaultdict

COL = dict(
    id="hashed_id", hosp="hospital", group="group",            # cohort / admissions
    t_infection_suspected="t_infection_suspected", rule="suspicion_rule", t_first_antibiotic="t_first_antibiotic", sepsis="sepsis", death="death_inhosp", t_icu_in="t_icu_in",
    drug="ingredient", drug_raw="drug_raw", route="route",       # antibiotics
    t_start="t_start", t_first_administration="t_first_administration",
    spec="spec_type", t_collect="t_collect",                      # cultures
)
CULTURE_WINDOW_H = 72      # culture_first: 배양 → 72h 안 항생제
ABX_WINDOW_H = 24          # antibiotic_first: 항생제 → 24h 안 배양
CA_LIMIT_H = 48            # 지역사회 획득: t_infection_suspected ≤ 입원 + 48h
REGIMEN_WINDOW_H = 24      # 초기 요법: t_first_antibiotic ~ +24h 안에 시작된 성분
SYSTEMIC_ROUTES = None
CLASS_OF = {"glycopeptide(vanco+teico)": {"vancomycin", "teicoplanin"}, "anti_MRSA 전체": {"vancomycin", "teicoplanin", "linezolid", "daptomycin", "ceftaroline", "arbekacin"},
            "antipseudomonal": {"piperacillin/tazobactam", "cefepime", "ceftazidime", "meropenem", "imipenem", "doripenem", "aztreonam", "ciprofloxacin", "levofloxacin", "amikacin", "cefoperazone/sulbactam"},
            "carbapenem": {"meropenem", "imipenem", "ertapenem", "doripenem"}, "3rd_ceph": {"ceftriaxone", "cefotaxime", "ceftazidime", "cefpodoxime", "cefoperazone/sulbactam"},
            "macrolide": {"azithromycin", "clarithromycin", "erythromycin"}, "fluoroquinolone": {"ciprofloxacin", "levofloxacin", "moxifloxacin"}}     # 예: {"IV", "PO", "IM"}; None이면 antibiotics.csv가 이미 전신 항생제만 담고 있다고 본다


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def abx_time(r):
    """항생제 시각: 실제 투여 시각이 있으면 그것, 없으면 처방 시작."""
    return num(r.get(COL["t_first_administration"])) if num(r.get(COL["t_first_administration"])) is not None else num(r.get(COL["t_start"]))


NORMALIZE = {"piperacillin and beta-lactamase inhibitor": "piperacillin/tazobactam", "sulfamethoxazole and trimethoprim": "trimethoprim/sulfamethoxazole",
             "trimethoprim and sulfamethoxazole": "trimethoprim/sulfamethoxazole", "amoxicillin and beta-lactamase inhibitor": "amoxicillin/clavulanate",
             "ampicillin and beta-lactamase inhibitor": "ampicillin/sulbactam", "imipenem and cilastatin": "imipenem", "cefoperazone and beta-lactamase inhibitor": "cefoperazone/sulbactam",
             "ceftazidime and beta-lactamase inhibitor": "ceftazidime/avibactam", "ceftolozane and beta-lactamase inhibitor": "ceftolozane/tazobactam",
             "benzylpenicillin": "penicillin", "cefalexin": "cephalexin", "colistimethate": "colistin"}
ATC_MAP = None
def load_atc():
    """antibiotics.csv 에 ingredient 가 없고 atc 만 있을 때(K-MIMIC): 같은 폴더의 atc_to_ingredient.csv 로 성분명을 붙인다."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atc_to_ingredient.csv")
    return {r["atc"]: r["ingredient"] for r in csv.DictReader(open(p, encoding="utf-8"))} if os.path.exists(p) else {}
def abx_name(r):
    global ATC_MAP
    if ATC_MAP is None: ATC_MAP = load_atc()
    known = set(ATC_MAP.values()) | set(NORMALIZE.values())
    x = (r.get(COL["drug"]) or "").strip().lower()
    if not x and (r.get("atc") or r.get("gsn")): x = ATC_MAP.get((r.get("atc") or r.get("gsn"))[:7], "")
    if not x:                                                     # ATC 없음 → 약품명에서 아는 성분을 찾는다 (예: 'Tazoperan 4.5g inj(Piperacillin/Tazobactam)')
        raw = (r.get(COL["drug_raw"]) or "").strip().lower()
        x = NORMALIZE.get(raw) or next((v for k, v in NORMALIZE.items() if k in raw), None) or next((k for k in known if k in raw), None) or raw
    return NORMALIZE.get(x, x)


def is_regimen_row(r):
    """새 SQL(처방 한 번 읽기)의 antibiotics.csv 에는 이전 입원 행(hadm_is_cohort=0)과 승압제 행(is_vasopressor=1)이 섞여 있다 → 요법 · 짝짓기에서는 뺀다. 옛 형식(컬럼 없음)은 전부 통과"""
    return r.get("hadm_is_cohort", "1") not in ("0", "0.0") and r.get("is_vasopressor", "0") not in ("1", "1.0")
PRIOR_IV_H, PRIOR_MICRO_H = 90 * 24, 365 * 24
def is_iv_like(r):
    rt = (r.get(COL["route"]) or "").upper(); d = (r.get(COL["drug_raw"]) or "").lower()
    return "IV" in rt or "정맥" in rt or "주사" in rt or "inj" in d
def history_flags(cohort, abx, cultures):
    """cohort.csv 에 없거나 비어 있는 플래그를 antibiotics/cultures 에서 계산: prior_iv_abx_90d, vasopressor, t_vaso_start, prior_mrsa_1y, prior_pseudomonas_1y"""
    A = defaultdict(list); C = defaultdict(list)
    for r in abx: A[r[COL["id"]]].append(r)
    for r in cultures: C[r[COL["id"]]].append(r)
    for o in cohort:
        i = o[COL["id"]]; rows = A.get(i, []); cul = C.get(i, [])
        if o.get("prior_iv_abx_90d", "") == "":
            o["prior_iv_abx_90d"] = int(any(r.get("hadm_is_cohort", "1") in ("0", "0.0") and r.get("is_vasopressor", "0") not in ("1", "1.0") and num(r.get(COL["t_start"])) is not None
                                              and -PRIOR_IV_H <= num(r[COL["t_start"]]) < 0 and is_iv_like(r) for r in rows))
        if o.get("vasopressor", "") == "":
            vs = [num(r.get(COL["t_start"])) for r in rows if r.get("is_vasopressor", "0") in ("1", "1.0") and r.get("hadm_is_cohort", "1") not in ("0", "0.0") and num(r.get(COL["t_start"])) is not None]
            o["vasopressor"] = int(bool(vs)); o["t_vaso_start"] = min(vs) if vs else ""
        for flag, col in (("prior_mrsa_1y", "is_mrsa"), ("prior_pseudomonas_1y", "is_pseudomonas")):
            if o.get(flag, "") == "":
                o[flag] = int(any(r.get(col, "0") in ("1", "1.0") and num(r.get(COL["t_collect"])) is not None and -PRIOR_MICRO_H <= num(r[COL["t_collect"]]) < 0 for r in cul))
    return cohort
def index_abx(abx):
    by = defaultdict(list)
    for r in abx:
        if not is_regimen_row(r): continue
        if SYSTEMIC_ROUTES and r.get(COL["route"]) not in SYSTEMIC_ROUTES:
            continue
        t = abx_time(r)
        if t is not None:
            by[r[COL["id"]]].append((t, abx_name(r)))
    return by


def regimen(events, t_first_antibiotic):
    names = sorted({n for t, n in events if t_first_antibiotic <= t <= t_first_antibiotic + REGIMEN_WINDOW_H and n})
    return " + ".join(names), len(names)


def derive(cohort, abx, cultures):
    A = index_abx(abx)
    SCREEN = re.compile(r"(^|[^a-z])(cre|vre|mrsa|tip|pcr)([^a-z]|$)|rectal|nasal|screen|surveillance|antigen|직장|비강|선별|항원")   # 선별·비배양 검체 (secretion 의 cre 같은 부분일치 방지)
    C = defaultdict(set); dropped = 0
    for r in cultures:
        t = num(r.get(COL["t_collect"]))
        txt = (str(r.get(COL["spec"], "")) + " " + str(r.get("test_name", ""))).lower()
        if r.get("is_culture") in ("0", "0.0", "false") or SCREEN.search(txt): dropped += 1; continue
        if t < -CA_LIMIT_H: continue                                   # 과거력용 행(−365일 ~ −48h)은 짝짓기에 쓰지 않는다
        if t is not None:
            C[r[COL["id"]]].add(t)
    print(f"선별·비배양 검체로 제외한 행: {dropped:,}")
    out = []
    for r in cohort:
        i = r[COL["id"]]; ev = A.get(i, []); a_list = sorted({t for t, _ in ev}); c_list = sorted(C.get(i, ()))
        best = None
        for a in a_list:
            for c in c_list:
                if c <= a <= c + CULTURE_WINDOW_H:
                    cand = (c, "culture_first")
                elif a < c <= a + ABX_WINDOW_H:
                    cand = (a, "antibiotic_first")
                else:
                    continue
                if best is None or cand[0] < best[0]:
                    best = cand
        o = dict(r)
        o["has_antibiotic"] = int(bool(a_list)); o["has_culture"] = int(bool(c_list))
        o[COL["t_infection_suspected"]] = best[0] if best else ""; o[COL["rule"]] = best[1] if best else ""
        o["community_acquired"] = int(best is not None and best[0] <= CA_LIMIT_H)
        o[COL["t_first_antibiotic"]] = ""; o["initial_regimen"] = ""; o["n_initial_antibiotics"] = ""
        if best:
            later = [a for a in a_list if a >= best[0]]
            if later:
                t_first_antibiotic = min(later); o[COL["t_first_antibiotic"]] = t_first_antibiotic
                o["initial_regimen"], o["n_initial_antibiotics"] = regimen(ev, t_first_antibiotic)
        out.append(o)
    return history_flags(out, abx, cultures)


def steps(rows):
    s = {"코드 선정 후": len(rows)}
    if rows and "has_antibiotic" in rows[0]:
        s["항생제 기록 있음"] = sum(int(r["has_antibiotic"]) for r in rows)
        s["배양 있음"] = sum(int(r["has_culture"]) for r in rows)
    sus = [r for r in rows if num(r.get(COL["t_infection_suspected"])) is not None]
    s["의심 시각 있음"] = len(sus)
    if rows and COL["rule"] in rows[0]:
        s["  culture_first (배양→항생제)"] = sum(r[COL["rule"]] == "culture_first" for r in sus)
        s["  antibiotic_first (항생제→배양)"] = sum(r[COL["rule"]] == "antibiotic_first" for r in sus)
    ca = [r for r in sus if num(r[COL["t_infection_suspected"]]) <= CA_LIMIT_H]
    s["48h 이내 (지역사회 획득)"] = len(ca)
    if rows and COL["sepsis"] in rows[0]:
        s["  패혈증 있음"] = sum(r.get(COL["sepsis"]) == "1" for r in ca)
        s["  패혈증 없음"] = sum(r.get(COL["sepsis"]) != "1" for r in ca)
    return s


def median(v):
    v = sorted(x for x in v if x is not None); n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def summarize(cohort, abx):
    if cohort and "initial_regimen" not in cohort[0]:     # (A) 경로: 요법을 여기서 만든다
        A = index_abx(abx)
        for r in cohort:
            t_first_antibiotic = num(r.get(COL["t_first_antibiotic"]))
            r["initial_regimen"], r["n_initial_antibiotics"] = regimen(A.get(r[COL["id"]], []), t_first_antibiotic) if t_first_antibiotic is not None else ("", "")

    print("\n=== 단계별 n ===")
    tables = {"전체": steps(cohort)}
    for h in sorted({r.get(COL["hosp"], "") for r in cohort}):
        if h:
            tables[h] = steps([r for r in cohort if r.get(COL["hosp"]) == h])
    labels = list(tables["전체"])
    print(f"{'단계':28}" + "".join(f"{k:>10}" for k in tables))
    for lab in labels:
        print(f"{lab:28}" + "".join(f"{t.get(lab, ''):>10}" for t in tables.values()))

    final = [r for r in cohort if num(r.get(COL["t_infection_suspected"])) is not None and num(r[COL["t_infection_suspected"]]) <= CA_LIMIT_H]
    groups = defaultdict(list)
    for r in final:
        key = r.get(COL["group"], "")
        if COL["sepsis"] in r:
            key += " / 패혈증 " + ("있음" if r[COL["sepsis"]] == "1" else "없음")
        groups[key].append(r)
    for g, d in sorted(groups.items()):
        n = len(d)
        print(f"\n=== {g}  n={n} ===")
        if COL["death"] in d[0]:
            print(f"원내 사망 {100 * sum(r[COL['death']] == '1' for r in d) / n:.1f}%")
        m = median([num(r.get(COL["t_first_antibiotic"])) for r in d])
        line = f"입원→첫 항생제 중앙값 {m:.1f} h" if m is not None else "입원→첫 항생제: 값 없음"
        if COL["t_icu_in"] in d[0]:
            pre = [num(r[COL["t_infection_suspected"]]) < num(r[COL["t_icu_in"]]) for r in d if num(r.get(COL["t_icu_in"])) is not None]
            if pre:
                line += f" · 의심 시각이 ICU 입실 전 {100 * sum(pre) / len(pre):.0f}%"
        print(line)
        print("성분 수:", dict(sorted(Counter(str(r["n_initial_antibiotics"]) for r in d if r["n_initial_antibiotics"] != "").items())))
        ing = Counter(x for r in d if r["initial_regimen"] for x in r["initial_regimen"].split(" + "))
        print("성분 상위 5 (%):", {k: round(100 * v / n, 1) for k, v in ing.most_common(5)})
        reg = Counter(r["initial_regimen"] for r in d if r["initial_regimen"])
        print("요법 상위 5 (%):", {k: round(100 * v / n, 1) for k, v in reg.most_common(5)})
        # 계열 묶음 (환자 단위): 한국 데이터는 teicoplanin 비중이 커서 glycopeptide 를 묶어 본다
        cls = {k: sum(1 for r in d if any(i in v for i in r["initial_regimen"].split(" + "))) for k, v in CLASS_OF.items()}
        print("계열 포함 환자 % :", {k: round(100 * c / n, 1) for k, c in cls.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["derive", "summarize"])
    ap.add_argument("--cohort", required=True); ap.add_argument("--abx", required=True)
    ap.add_argument("--cultures"); ap.add_argument("--out", default="cohort_derived.csv")
    a = ap.parse_args()
    cohort, abx = read(a.cohort), read(a.abx)
    if a.mode == "derive":
        if not a.cultures:
            sys.exit("derive에는 --cultures 가 필요하다")
        cohort = derive(cohort, abx, read(a.cultures))
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(cohort[0].keys())); w.writeheader(); w.writerows(cohort)
        print("saved", a.out)
    summarize(cohort, abx)
