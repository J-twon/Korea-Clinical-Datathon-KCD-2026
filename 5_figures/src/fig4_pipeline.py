import sys, html
import os
S = os.path.dirname(os.path.abspath(__file__))          # src/ (fig_defs.svg 가 있는 곳)
OUTD = os.path.dirname(S)                                # 5_figures/ (svg · png · pdf 출력)
DEFS = open(f"{S}/fig_defs.svg", encoding="utf-8").read().replace("</defs>",
 '<pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#185fa5" stroke-width="1.2" opacity="0.45"/></pattern></defs>')
INK, GREY, LINE = "#1f2937", "#6b7280", "#cbd5e1"
BLUE, BLUEF, GREEN, GREENF, ORANGE, ORANGEF, RED, REDF, PURPLE, PURPLEF = "#185fa5", "#eaf2fb", "#0f6e56", "#e6f4ef", "#ba7517", "#fdf3e0", "#b42318", "#fdecea", "#534ab7", "#efedfa"

T = {
"en": dict(
 title="From MIMIC-IV to a guideline-adherence judgment: cohort flow, rule windows, and the leak-free case card",
 font="Helvetica Neue, Arial, Noto Sans, Noto Sans CJK KR, sans-serif",
 A="A  Cohort construction (MIMIC-IV v3.1, numbers = admissions)",
 a1t="MIMIC-IV v3.1 (hosp + icu modules)", a1="364,627 patients · 546,028 admissions · 94,458 ICU stays",
 a2t="First ICU stay per patient · adults ≥ 18 y", a2="65,366 patients, one admission each (no readmissions)",
 a3t="Diagnosis codes, any position (ICD-9 / ICD-10)", a3l="Pneumonia  8,234", a3ls="ICD-10: J13–J16, J18.0/.1/.8/.9", a3ls2="ICD-9: 481–483, 485, 486", a3r="UTI  7,793", a3rs="ICD-10: N10, N12, N39.0", a3rs2="ICD-9: 590.1/.80/.9, 599.0",
 ex1="Excluded", ex1a="aspiration 815 · VAP 419 (pneumonia)", ex1b="catheter-related 330 (UTI)", ex1c="both pneumonia and UTI codes 1,029",
 a4t="After exclusions", a4="Pneumonia 6,056 · UTI 6,434",
 a5t="Suspicion of infection = culture ↔ antibiotic pairing", a5a="culture_first  (culture → antibiotic ≤ 72 h):  4,752 · 5,464", a5b="antibiotic_first  (antibiotic → culture ≤ 24 h):  1,009 · 628", a5c="with a suspicion time:  5,761 · 6,092",
 ex2="no pairing 295 · 342",
 a6t="Community-acquired: suspicion ≤ 48 h after hospital arrival", a6="Pneumonia 4,875 · UTI 4,523   (final cohort)",
 ex3="hospital-acquired, > 48 h: 886 · 1,569",
 a7t="Sepsis stratification — three labels (pneumonia · UTI)", a7r1="sepsis3 (mimic-code, primary)", a7v1="3,666 · 3,180", a7r2="simplified SOFA ≥ 2 (shared code, also for K-MIMIC)", a7v2="3,858 · 3,496", a7r3="ICD sepsis codes", a7v3="1,721 · 1,526",
 a7n1="agreement with sepsis3: SOFA 85% · 82% / codes 50% · 54%", a7n2="18% have no ICU data inside the SOFA window → flagged, not excluded",
 a8t="Case cards → LLM agents  (panel C)", a8="20 evaluation cases (5 × 4 groups) + 20 backup · hashed IDs · relative times",
 B="B  One patient's timeline and the rule windows (hours from hospital arrival, t0 = 0)",
 r1="Rule 1 · culture_first", r1a="culture", r1b="≤ 72 h", r1c="antibiotic", r1d="⇒ suspicion time = culture time",
 r2="Rule 2 · antibiotic_first", r2a="antibiotic", r2b="≤ 24 h", r2c="culture", r2d="⇒ suspicion time = antibiotic time",
 e0="Hospital arrival (t0 = 0)", e1="Culture collected (+3 h) → suspicion time", e2="First antibiotic ordered (+8 h) = t_first_antibiotic", e3="First dose given (+9.5 h; eMAR lag, median 1.1 h)", e4="ICU admission (+14 h)",
 axis="hours from arrival",
 b1="◂ Sepsis-3 window: suspicion −48 h … +24 h  (SOFA ≥ 2 inside → sepsis)",
 b2="Initial regimen: every systemic antibiotic started within 24 h of the first",
 b3="Vital signs and SOFA components exist only after ICU admission (ED vitals are not in this dataset)",
 cut="48 h cut-off", cut2="suspicion after 48 h = hospital-acquired → excluded",
 L="Availability rule for the case card: a value enters only if it was reported (storetime) before the first antibiotic",
 l1="Lab A: drawn +1.0 h, reported +1.8 h", l1r="in the card", l2="Lab B: drawn +6.5 h, reported +9.0 h", l2r="reported after the first antibiotic → not in the card",
 lcut="first antibiotic (+8 h)", lnote="If chart time were used instead: 13% of 'last values' and 21% of patients would carry results the clinician had not seen",
 C="C  Case card for the agent (hashed ID, all times relative to the first antibiotic = T+0)",
 c1="Age, sex, weight · ED visit · ICU type", c2="Vitals and labs: last value reported before T+0", c3="Cultures before T+0: specimen and time only, no results", c4="Empirical set: ingredient · class · AWaRe · route · dose · start T+h", c5="History: admission / IV antibiotics ≤ 90 d · MRSA / Pseudomonas ≤ 1 y", c6="Comorbidities from codes (DM, CKD, COPD, immunosuppression, …)",
 nt="Not in the card", n1="Discharge diagnoses", n2="In-hospital death", n3="Culture results after T+0", n4="SOFA score / sepsis label",
 jt="Judgment", j1="A1 syndrome & severity → A4 adherence vs KR / INTL guideline → A5 grounding check", j2="Clinicians rate 5 cases × 4 groups (1–5 and 4-level verdict)",
),
"ko": dict(
 title="MIMIC-IV에서 가이드라인 준수 판정까지: 코호트 흐름, 규칙 창, 누출 없는 사례 카드",
 font="Noto Sans CJK KR, Noto Sans KR, Apple SD Gothic Neo, sans-serif",
 A="A  코호트 구성 (MIMIC-IV v3.1, 숫자 = 입원 건수)",
 a1t="MIMIC-IV v3.1 (hosp + icu 모듈)", a1="환자 364,627 · 입원 546,028 · ICU stay 94,458",
 a2t="환자별 첫 ICU 입실 1회 · 성인 18세 이상", a2="65,366명, 환자당 입원 1건 (재입실 · 재입원 제외)",
 a3t="진단코드, 주 · 부상병 모두 (ICD-9 / ICD-10)", a3l="폐렴  8,234", a3ls="ICD-10: J13–J16, J18.0/.1/.8/.9", a3ls2="ICD-9: 481–483, 485, 486", a3r="요로감염  7,793", a3rs="ICD-10: N10, N12, N39.0", a3rs2="ICD-9: 590.1/.80/.9, 599.0",
 ex1="제외", ex1a="흡인성 815 · VAP 419 (폐렴)", ex1b="카테터 관련 330 (요로감염)", ex1c="폐렴 · 요로감염 코드 둘 다 1,029",
 a4t="제외 후", a4="폐렴 6,056 · 요로감염 6,434",
 a5t="감염 의심 시각 = 배양 ↔ 항생제 짝짓기", a5a="culture_first  (배양 → 72h 안 항생제):  4,752 · 5,464", a5b="antibiotic_first  (항생제 → 24h 안 배양):  1,009 · 628", a5c="의심 시각이 정해진 수:  5,761 · 6,092",
 ex2="짝 없음 295 · 342",
 a6t="지역사회 획득: 의심 시각이 병원 도착 후 48시간 이내", a6="폐렴 4,875 · 요로감염 4,523   (최종 코호트)",
 ex3="원내 감염, 48시간 초과: 886 · 1,569",
 a7t="패혈증 분류 — 라벨 세 가지 (폐렴 · 요로감염)", a7r1="sepsis3 (mimic-code 공식, 주 라벨)", a7v1="3,666 · 3,180", a7r2="간이 SOFA ≥ 2 (공용 코드, K-MIMIC에도 적용)", a7v2="3,858 · 3,496", a7r3="ICD 패혈증 코드", a7v3="1,721 · 1,526",
 a7n1="sepsis3와 일치율: SOFA 85% · 82% / 코드 50% · 54%", a7n2="18%는 SOFA 창 안에 ICU 기록이 없음 → 제외하지 않고 플래그로 표시",
 a8t="사례 카드 → LLM 에이전트  (패널 C)", a8="평가 사례 20건 (5 × 4집단) + 예비 20건 · 해시 ID · 상대 시간",
 B="B  한 환자의 타임라인과 규칙 창 (병원 도착 기준 시간, t0 = 0)",
 r1="규칙 1 · culture_first", r1a="배양", r1b="≤ 72h", r1c="항생제", r1d="⇒ 의심 시각 = 배양 시각",
 r2="규칙 2 · antibiotic_first", r2a="항생제", r2b="≤ 24h", r2c="배양", r2d="⇒ 의심 시각 = 항생제 시각",
 e0="병원 도착 (t0 = 0)", e1="배양 채취 (+3h) → 감염 의심 시각", e2="첫 항생제 처방 (+8h) = t_first_antibiotic", e3="첫 투여 (+9.5h; eMAR 지연 중앙값 1.1h)", e4="ICU 입실 (+14h)",
 axis="도착 후 시간 (h)",
 b1="◂ Sepsis-3 창: 의심 시각 −48h … +24h  (이 안에서 SOFA ≥ 2 → 패혈증)",
 b2="초기 요법: 첫 항생제부터 24h 안에 시작된 모든 전신 항생제",
 b3="활력징후 · SOFA 구성요소는 ICU 입실 후에만 있음 (응급실 vital은 이 데이터셋에 없음)",
 cut="48h 기준선", cut2="48h 이후 의심 = 원내 감염 → 제외",
 L="사례 카드 가용 규칙: 첫 항생제 전에 결과가 보고된(storetime) 값만 카드에 넣는다",
 l1="검사 A: 채취 +1.0h, 보고 +1.8h", l1r="카드에 포함", l2="검사 B: 채취 +6.5h, 보고 +9.0h", l2r="첫 항생제 뒤에 보고됨 → 카드에서 제외",
 lcut="첫 항생제 (+8h)", lnote="채취 시각으로 고르면 '마지막 값'의 13%, 환자의 21%에 의사가 아직 못 본 결과가 섞인다",
 C="C  에이전트에게 주는 사례 카드 (해시 ID, 모든 시각은 첫 항생제 = T+0 기준)",
 c1="나이 · 성별 · 체중 · 응급실 경유 · ICU 종류", c2="활력징후 · 검사: T+0 전에 보고된 마지막 값", c3="T+0 전 배양: 검체 종류와 시각만, 결과 없음", c4="경험적 요법: 성분 · 계열 · AWaRe · 경로 · 용량 · 시작 T+h", c5="과거력: 90일 내 입원 / IV 항생제 · 1년 내 MRSA / 녹농균", c6="기저질환 (코드): 당뇨, CKD, COPD, 면역저하 등",
 nt="카드에 넣지 않는 것", n1="퇴원 진단코드", n2="원내 사망", n3="T+0 이후 배양 결과", n4="SOFA 점수 / 패혈증 라벨",
 jt="판정", j1="A1 증후군 · 중증도 → A4 국내 / 해외 지침 준수 판정 → A5 근거 검증", j2="임상의 평가: 5건 × 4집단 (1–5점, 4단계 판정)",
),
}

def esc(s): return html.escape(s, quote=False)
def tx(x, y, s, size=11.5, fill=INK, w="normal", anchor="start", mono=False, extra=""):
    fam = ' font-family="DejaVu Sans Mono, Menlo, monospace"' if mono else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{w}" text-anchor="{anchor}"{fam}{extra}>{esc(s)}</text>'
def icon(name, x, y, w, h, color, sw=2.2, fill="none"): return f'<use href="#{name}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{color}" stroke-width="{sw}"/>'
def box(x, y, w, h, fill, stroke, r=8): return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
def arrow(x1, y1, x2, y2, color=GREY, m="ar", dash=""): return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="1.6" fill="none" marker-end="url(#{m})" color="{color}"{dash}/>'
def check(x, y, c=GREEN): return f'<path d="M{x-6} {y} l4 4 l8 -9" stroke="{c}" stroke-width="2.6" fill="none" stroke-linecap="round"/>'
def cross(x, y, c=RED): return f'<path d="M{x-5} {y-5} l10 10 M{x+5} {y-5} l-10 10" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>'
def xmark(x, y): return f'<circle cx="{x}" cy="{y}" r="7" fill="#fff" stroke="{RED}" stroke-width="1.4"/>' + cross(x, y)

def build(lang):
    t = T[lang]; o = []
    o.append(f'<rect width="1500" height="1000" fill="#fff"/>')
    o.append(tx(40, 42, t["title"], 18, INK, "bold"))
    # ---------------- Panel A ----------------
    o.append(tx(40, 84, t["A"], 14, INK, "bold"))
    X, W = 60, 390
    def abox(y, h, fill, stroke, ic, title, lines, icc=None, bold_last=False):
        o.append(box(X, y, W, h, fill, stroke)); o.append(icon(ic, X + 14, y + (h - 28) / 2, 30, 28, icc or stroke))
        o.append(tx(X + 56, y + 20, title, 12, INK, "bold"))
        for i, l in enumerate(lines):
            o.append(tx(X + 56, y + 38 + i * 15, l, 11, INK if (bold_last and i == len(lines) - 1) else GREY, "bold" if (bold_last and i == len(lines) - 1) else "normal"))
    def down(y1, y2, x=X + W / 2): o.append(arrow(x, y1, x, y2, GREY))
    y = 100
    abox(y, 54, "#f8fafc", BLUE, "i-db", t["a1t"], [t["a1"]]); down(y + 54, y + 76); y += 76
    abox(y, 54, BLUEF, BLUE, "i-bed", t["a2t"], [t["a2"]]); down(y + 54, y + 76); y += 76
    o.append(box(X, y, W, 92, BLUEF, BLUE)); o.append(icon("i-doc", X + 14, y + 32, 26, 30, BLUE))
    o.append(tx(X + 56, y + 20, t["a3t"], 12, INK, "bold"))
    for cx0, nk, k1, k2 in ((X + 56, "a3l", "a3ls", "a3ls2"), (X + 236, "a3r", "a3rs", "a3rs2")):
        o.append(tx(cx0, y + 42, t[nk], 12, INK, "bold")); o.append(tx(cx0, y + 60, t[k1], 9.5, GREY)); o.append(tx(cx0, y + 74, t[k2], 9.5, GREY))
    down(y + 92, y + 114); o.append(xmark(X + W / 2 + 14, y + 103))
    ex = X + W + 14; o.append(tx(ex, y + 84, t["ex1"], 11, RED, "bold"))
    for i, k in enumerate(("ex1a", "ex1b", "ex1c")): o.append(tx(ex, y + 100 + i * 14, t[k], 10, RED))
    y += 114
    abox(y, 46, "#f8fafc", GREY, "i-funnel", t["a4t"], [t["a4"]], bold_last=True); down(y + 46, y + 68); y += 68
    abox(y, 86, ORANGEF, ORANGE, "i-flask", t["a5t"], [t["a5a"], t["a5b"], t["a5c"]], bold_last=True)
    o.append(icon("i-pill", X + 22, y + 56, 20, 20, ORANGE))
    down(y + 86, y + 108); o.append(xmark(X + W / 2 + 14, y + 97)); o.append(tx(ex, y + 101, t["ex2"], 10, RED)); y += 108
    abox(y, 56, GREENF, GREEN, "i-clock", t["a6t"], [t["a6"]], bold_last=True)
    down(y + 56, y + 78); o.append(xmark(X + W / 2 + 14, y + 67)); o.append(tx(ex, y + 71, t["ex3"], 10, RED)); y += 78
    o.append(box(X, y, W, 140, PURPLEF, PURPLE)); o.append(icon("i-scale", X + 14, y + 14, 30, 28, PURPLE))
    o.append(tx(X + 56, y + 20, t["a7t"], 12, INK, "bold"))
    for i, (rk, vk) in enumerate((("a7r1", "a7v1"), ("a7r2", "a7v2"), ("a7r3", "a7v3"))):
        yy = y + 40 + i * 17; o.append(tx(X + 56, yy, t[rk], 10.5, INK if i == 0 else GREY, "bold" if i == 0 else "normal")); o.append(tx(X + W - 14, yy, t[vk], 11, INK, "bold", "end"))
    o.append(f'<line x1="{X + 56}" y1="{y + 98}" x2="{X + W - 14}" y2="{y + 98}" stroke="{LINE}"/>')
    o.append(tx(X + 56, y + 114, t["a7n1"], 10, PURPLE)); o.append(tx(X + 56, y + 129, t["a7n2"], 10, PURPLE))
    down(y + 140, y + 162); y += 162
    abox(y, 54, "#f8fafc", PURPLE, "i-json", t["a8t"], [t["a8"]]); A8MID = y + 27
    # ---------------- Panel B ----------------
    BX = 720; o.append(tx(BX, 84, t["B"], 14, INK, "bold"))
    # rule legend
    def rule(y, label, a, ai, mid, c, ci, concl):
        o.append(tx(BX + 10, y + 5, label, 11, INK, "bold")); x = BX + 190
        o.append(icon(ai, x, y - 12, 22, 22, ORANGE)); o.append(tx(x + 27, y + 5, a, 11, INK))
        x2 = x + 27 + (62 if lang == "en" and a == "antibiotic" else 45 if lang == "en" else 40)
        o.append(arrow(x2 + 4, y, x2 + 74, y, ORANGE, "arO")); o.append(tx(x2 + 39, y - 5, mid, 10, ORANGE, "bold", "middle"))
        o.append(icon(ci, x2 + 80, y - 12, 22, 22, ORANGE)); o.append(tx(x2 + 107, y + 5, c, 11, INK))
        o.append(tx(x2 + 107 + (62 if lang == "en" and c == "antibiotic" else 50 if lang == "en" else 42), y + 5, concl, 11, ORANGE, "bold"))
    o.append(box(BX, 96, 740, 60, "#fff", LINE, 6))
    rule(114, t["r1"], t["r1a"], "i-flask", t["r1b"], t["r1c"], "i-pill", t["r1d"])
    rule(140, t["r2"], t["r2a"], "i-pill", t["r2b"], t["r2c"], "i-flask", t["r2d"])
    # main axis: hours -12..60
    AX0, AX1, H0, H1, AY = BX + 40, BX + 720, -12, 60, 318
    xh = lambda h: AX0 + (h - H0) * (AX1 - AX0) / (H1 - H0)
    o.append(f'<line x1="{AX0}" y1="{AY}" x2="{AX1}" y2="{AY}" stroke="{INK}" stroke-width="1.4"/>')
    for h in range(-12, 61, 12):
        o.append(f'<line x1="{xh(h)}" y1="{AY}" x2="{xh(h)}" y2="{AY + 5}" stroke="{INK}"/>')
        if h != 48: o.append(tx(xh(h), AY + 17, f"{h:+d}" if h else "0", 9.5, GREY, anchor="middle"))
    o.append(tx(AX1, AY + 31, t["axis"], 9.5, GREY, anchor="end"))
    # events
    IY = 262
    events = [(0, "i-hosp", INK, "e0", 202, "end"), (3, "i-flask", ORANGE, "e1", 178, "start"), (8, "i-pill", GREEN, "e2", 202, "start"), (9.5, "i-pill", GREEN, "e3", 224, "start"), (14, "i-bed", BLUE, "e4", 246, "start")]
    for h, ic, col, key, ly, anc in events:
        x = xh(h); o.append(f'<line x1="{x}" y1="{IY + 26}" x2="{x}" y2="{AY}" stroke="{col}" stroke-width="1.2" stroke-dasharray="3 2"/>')
        fill = "#d1fae5" if key == "e3" else "none"
        o.append(icon(ic, x - 12 if key != "e3" else x - 2, IY if key != "e3" else IY + 2, 24 if key != "e3" else 20, 24 if key != "e3" else 20, col, fill=fill))
        lx = x - 16 if anc == "end" else x + 16
        o.append(f'<line x1="{x}" y1="{IY - 2}" x2="{x}" y2="{ly + 3}" stroke="{col}" stroke-width="0.8"/>')
        o.append(tx(lx, ly, t[key], 10.5, col if key != "e0" else INK, "bold" if key in ("e1", "e2") else "normal", anc))
    # bands
    def twidth(label): return sum(10.4 if ord(ch) > 0x2E80 else 5.9 for ch in label) + 8
    def band(y, x1, x2, fill, stroke, label, lcol):
        o.append(f'<rect x="{x1}" y="{y}" width="{x2 - x1}" height="22" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        o.append(f'<rect x="{x1 + 5}" y="{y + 4}" width="{twidth(label)}" height="15" rx="3" fill="#fff" opacity="0.88"/>')
        o.append(tx(x1 + 9, y + 15, label, 10, lcol, "bold"))
    band(338, AX0, xh(27), ORANGEF, ORANGE, t["b1"], ORANGE)
    band(368, xh(8), xh(32), GREENF, GREEN, t["b2"], GREEN)
    band(398, xh(14), AX1, "url(#hatch)", BLUE, t["b3"], BLUE)
    # 48h cutoff
    xc = xh(48); o.append(f'<line x1="{xc}" y1="232" x2="{xc}" y2="440" stroke="{RED}" stroke-width="1.4" stroke-dasharray="5 3"/>')
    o.append(tx(xc, 452, t["cut"], 10.5, RED, "bold", "middle")); o.append(tx(xc, 466, t["cut2"], 9.5, RED, anchor="middle"))
    # leak inset
    LY = 486; o.append(box(BX, LY, 740, 136, "#fff", LINE, 6)); o.append(tx(BX + 12, LY + 20, t["L"], 11, INK, "bold"))
    lx = lambda h: BX + 60 + h * 48
    o.append(f'<line x1="{lx(0)}" y1="{LY + 92}" x2="{lx(12)}" y2="{LY + 92}" stroke="{GREY}"/>')
    for h in range(0, 13, 2): o.append(tx(lx(h), LY + 105, f"+{h}h", 8.5, GREY, anchor="middle"))
    xa = lx(8); o.append(f'<line x1="{xa}" y1="{LY + 30}" x2="{xa}" y2="{LY + 92}" stroke="{RED}" stroke-width="1.4" stroke-dasharray="5 3"/>'); o.append(tx(xa + 5, LY + 40, t["lcut"], 9.5, RED, "bold"))
    for (h1, h2, yy, col, lab, res, ok) in ((1.0, 1.8, LY + 52, GREEN, t["l1"], t["l1r"], True), (6.5, 9.0, LY + 74, RED, t["l2"], t["l2r"], False)):
        o.append(f'<line x1="{lx(h1)}" y1="{yy}" x2="{lx(h2)}" y2="{yy}" stroke="{col}" stroke-width="5" stroke-linecap="round"/>')
        o.append(f'<circle cx="{lx(h1)}" cy="{yy}" r="4" fill="#fff" stroke="{col}" stroke-width="1.6"/><circle cx="{lx(h2)}" cy="{yy}" r="4" fill="{col}"/>')
        o.append(check(lx(h2) + 18, yy) if ok else cross(lx(h2) + 18, yy))
        if ok: o.append(tx(lx(h2) + 32, yy + 4, f"{lab} — {res}", 9.5, col))
        else: o.append(tx(lx(h1) - 14, yy - 2, lab, 9.5, col, "bold", "end")); o.append(tx(lx(h1) - 14, yy + 10, res, 9.5, col, anchor="end"))
    o.append(tx(BX + 12, LY + 127, t["lnote"], 9.5, GREY))
    # ---------------- Panel C ----------------
    CY = 666; o.append(tx(BX, CY, t["C"], 14, INK, "bold"))
    cx, cy, cw, ch = BX + 40, CY + 16, 420, 262
    o.append(box(cx, cy, cw, ch, "#fff", PURPLE)); o.append(icon("i-json", cx + 14, cy + 12, 26, 26, PURPLE)); o.append(tx(cx + 50, cy + 30, "case.json", 12, PURPLE, "bold", mono=True))
    items = (("i-person", "c1"), ("i-monitor", "c2"), ("i-flask", "c3"), ("i-pill", "c4"), ("i-log", "c5"), ("i-doc", "c6"))
    for i, (ic, k) in enumerate(items):
        yy = cy + 50 + i * 35; o.append(icon(ic, cx + 16, yy, 22, 22, PURPLE)); o.append(tx(cx + 50, yy + 15, t[k], 10.5, INK))
    nx, ny, nw, nh = cx + cw + 30, cy, 250, 118
    o.append(box(nx, ny, nw, nh, REDF, RED)); o.append(tx(nx + 14, ny + 22, t["nt"], 12, RED, "bold"))
    for i, k in enumerate(("n1", "n2", "n3", "n4")):
        yy = ny + 44 + i * 18; o.append(cross(nx + 20, yy - 4)); o.append(tx(nx + 34, yy, t[k], 10.5, RED))
    jx, jy, jw, jh = nx, ny + nh + 22, nw, 122
    o.append(box(jx, jy, jw, jh, PURPLEF, PURPLE)); o.append(icon("i-chip", jx + 14, jy + 12, 30, 26, PURPLE)); o.append(tx(jx + 54, jy + 30, t["jt"], 12, INK, "bold"))
    # wrap j1/j2 into lines manually
    def wrap(s, n):
        words = s.split(" "); lines = []; cur = ""
        for w_ in words:
            if len(cur) + len(w_) + 1 > n and cur: lines.append(cur); cur = w_
            else: cur = (cur + " " + w_).strip()
        if cur: lines.append(cur)
        return lines
    yy = jy + 52
    for l in wrap(t["j1"], 34 if lang == "en" else 26): o.append(tx(jx + 14, yy, l, 10, INK)); yy += 14
    yy += 4
    for l in wrap(t["j2"], 34 if lang == "en" else 26): o.append(tx(jx + 14, yy, l, 10, PURPLE)); yy += 14
    o.append(arrow(cx + cw, jy + jh / 2, jx - 2, jy + jh / 2, PURPLE, "arP"))
    # panel A → C link
    o.append(f'<path d="M{X + W + 2} {A8MID} L{cx - 4} {A8MID}" stroke="{PURPLE}" stroke-width="1.2" fill="none" stroke-dasharray="4 3" marker-end="url(#arP)"/>')
    body = "\n".join(o)
    svg = f'<svg viewBox="0 0 1500 1000" xmlns="http://www.w3.org/2000/svg" role="img" font-family="{t["font"]}" font-size="11.5">\n{DEFS}\n{body}\n</svg>'
    return svg

for lang in ("en", "ko"):
    svg = build(lang)
    open(f"{OUTD}/fig4_pipeline_{lang}.svg", "w", encoding="utf-8").write(svg)
    open(f"{OUTD}/fig4_pipeline_{lang}.preview.html", "w", encoding="utf-8").write(
        '<!doctype html><html><head><meta charset="utf-8"><style>@page{size:1500px 1000px;margin:0}body{margin:0;background:#fff}svg{display:block;width:1500px;height:1000px}</style></head><body>' + svg + '</body></html>')
print("svg written")
