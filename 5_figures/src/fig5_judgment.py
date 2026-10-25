import html
import os
S = os.path.dirname(os.path.abspath(__file__))          # src/ (fig_defs.svg 가 있는 곳)
OUTD = os.path.dirname(S)                                # 5_figures/ (svg · png · pdf 출력)
DEFS = open(f"{S}/fig_defs.svg", encoding="utf-8").read()
INK, GREY, LINE = "#1f2937", "#6b7280", "#cbd5e1"
BLUE, BLUEF, GREEN, GREENF, ORANGE, ORANGEF, RED, REDF, PURPLE, PURPLEF, GREYF = "#185fa5", "#eaf2fb", "#0f6e56", "#e6f4ef", "#ba7517", "#fdf3e0", "#b42318", "#fdecea", "#534ab7", "#efedfa", "#f1f5f9"
T = {
"ko": dict(font="Noto Sans CJK KR, Noto Sans KR, sans-serif",
 title="가이드라인 준수 판정 워크플로 — 규칙이 판정하고, RAG는 근거와 예외를 맡는다",
 A="A  환자 1명 × 지침 1개 × 항목(선택 · 용량 · 시기)마다 판정한다",
 s1t="① 사례 카드", s1=["T+0(첫 항생제) 이전 값만", "요법 R = 24h 안 시작 성분 집합", "위험인자 · 기저질환 · 중증도 재료"],
 s2t="② 조건 계산 (코드)", s2=["입원 = ICU (전원 해당)", "중증: 환기 · 승압제 · 소기준 ≥3", "MRSA 위험: 1년 내 분리", "녹농균 위험: 90일 입원 + 정주 항생제", "각 조건 = 참 / 거짓 / 모름"],
 s3t="③ 해당 행 찾기 (규칙표)", s3=["국내(K) · 해외(M) 각각 조회", "행 없음 → 해당 없음", "'모름' 조건 → 후보 행 전부 평가", "결론 같으면 채택, 다르면 판정 불가"],
 s4t="④ 요법 비교 (성분 집합)", s4=["R vs 추천 S / 대안 A", "아래 B의 분기표", "용량 · 경로 · 시기는 별도 항목"],
 s5t="⑤ 집계", s5=["준수율 = (준수 추천 + 준수 대안)", "    ÷ (전체 − 해당 없음 − 판정 불가)", "하한선: 판정 불가 = 비준수로 계산", "집단 × 지침별로 보고"],
 b1t="표본 20건 (+무작위 100건)", b2t="LLM + RAG 판정", b2=["같은 카드 + 검색된 청크 5개", "같은 8가지 판정값을 JSON으로"],
 b3t="규칙 판정과 비교", b3=["일치율", "불일치 유형: LLM 오류 /", "규칙표 밖 조건 / 자료 부족"],
 b4t="임상의 판정 (불일치만)", b4=["정당한 이탈 확정", "보고서 2종 블라인드 채점"],
 B="B  요법 비교 분기표 — 판정은 환자 단위 · 이분법이다 (예: 중증 CAP, MRSA · 녹농균 위험 없음 → S = ceftriaxone + azithromycin, A = levofloxacin)",
 rows=[("R = S", "준수 (추천)", "ceftriaxone + azithromycin", GREEN, GREENF),
       ("R = A", "준수 (대안)", "levofloxacin 단독 · 알레르기 정보가 없어 증빙 없이 인정, 비율은 따로 보고", GREEN, GREENF),
       ("R ⊃ S (추천 + 추가 약제)", "추가 약제가 다른 위험 행으로 설명되면 준수, 아니면 비준수 (과잉)", "+ vancomycin: MRSA 분리력 있으면 준수, 없으면 과잉", ORANGE, ORANGEF),
       ("R ⊂ S (추천 중 일부만)", "비준수 (누락) — 50%가 아니다", "ceftriaxone 단독 (azithromycin 누락). 보조 지표로 구성요소 일치율만 따로", RED, REDF),
       ("R ∩ S = ∅", "비준수 (다른 약제)", "cefepime + vancomycin (위험인자 없음)", RED, REDF),
       ("R 없음 · 수술 예방 cefazolin 단독 · 바이러스 동반", "해당 없음 (분모 제외, 수만 보고)", "cefazolin 단독 310명", GREY, GREYF),
       ("조건에 '모름'이 있고 후보 행 결론이 다름", "판정 불가 (분모 제외, 하한선에서는 비준수)", "vital 없어 중증도 미확정 (약 29%)", GREY, GREYF),
       ("비준수인데 카드에 사유가 있음", "정당한 이탈 (임상의 · LLM이 근거 제시한 것만)", "녹농균 분리력으로 cefepime 선택", PURPLE, PURPLEF)],
 C="C  미리 정해 둔 처리 규칙",
 crow=[("카드 변수가 지침에 없다 (젖산, CRP 등)", "판정에 안 쓴다. 보고서의 맥락으로만 준다"),
       ("지침 조건이 카드에 없다 (알레르기, 영상 다엽 침윤)", "'모름'으로 둔다. 대안 요법은 증빙 없이 준수(대안)로 인정"),
       ("항생제 2개 중 1개만 지침에 있다", "환자 단위 비준수(누락). 약제 단위 50%로 세지 않는다"),
       ("추천보다 넓게 썼다", "위험인자가 카드에 있으면 준수, 없으면 비준수(과잉)"),
       ("국내 · 해외 지침 결론이 다르다", "각각 판정해 둘 다 보고. 규칙표의 relation(common / conflict)"),
       ("용량 · 경로 · 시기", "선택과 분리해 따로 집계. mg/kg 약제는 체중 없으면 판정 불가"),
       ("지침이 다루지 않는 환자 (예방적 투여, 바이러스 폐렴 동반)", "해당 없음. 수를 보고하고 분모에서 뺀다"),
       ("판정 불가가 많다", "분모에서 빼되, 비준수로 본 하한선 준수율을 같이 낸다"),
       ("LLM 판정이 규칙과 다르다", "표본에서만 비교. 준수율은 규칙으로만 계산한다")],
 F="준수율(선택) = (준수 추천 + 준수 대안) ÷ (전체 − 해당 없음 − 판정 불가)   ·   함께 보고: 해당 없음 n, 판정 불가 n, 비준수 유형별 n, 대안 비율, 하한선"),
"en": dict(font="Helvetica Neue, Arial, Noto Sans, Noto Sans CJK KR, sans-serif",
 title="Guideline-adherence judgment workflow — rules decide; RAG supplies evidence and handles exceptions",
 A="A  One verdict per patient × guideline × item (selection · dose · timing)",
 s1t="① Case card", s1=["only values reported before T+0", "regimen R = agents started within 24 h", "risk factors, comorbidities, severity inputs"],
 s2t="② Compute conditions (code)", s2=["inpatient = ICU (all)", "severe: ventilation · vasopressor · ≥3 minor criteria", "MRSA risk: isolate ≤ 1 y", "Pseudomonas risk: admission + IV abx ≤ 90 d", "each condition = true / false / unknown"],
 s3t="③ Find the matching row (rule table)", s3=["look up KR and INTL separately", "no row → not applicable", "'unknown' → evaluate every candidate row", "same conclusion → adopt; differs → undeterminable"],
 s4t="④ Compare regimen (sets)", s4=["R vs recommended S / alternative A", "decision table in panel B", "dose · route · timing are separate items"],
 s5t="⑤ Aggregate", s5=["adherence = (recommended + alternative)", "    ÷ (all − not applicable − undeterminable)", "lower bound: undeterminable counted as non-adherent", "report by group × guideline"],
 b1t="Sample of 20 (+100 random)", b2t="LLM + RAG verdict", b2=["same card + 5 retrieved chunks", "same 8 verdict values as JSON"],
 b3t="Compare with rule verdict", b3=["agreement rate", "disagreement types: LLM error /", "condition outside the table / missing data"],
 b4t="Clinicians (disagreements only)", b4=["confirm justified deviations", "blind rating of both report types"],
 B="B  Regimen decision table — per patient, binary (example: severe CAP, no MRSA/Pseudomonas risk → S = ceftriaxone + azithromycin, A = levofloxacin)",
 rows=[("R = S", "Adherent (recommended)", "ceftriaxone + azithromycin", GREEN, GREENF),
       ("R = A", "Adherent (alternative)", "levofloxacin alone · allergy data absent, so accepted without proof; share reported separately", GREEN, GREENF),
       ("R ⊃ S (recommended + extra agent)", "adherent if the extra agent is explained by another risk row, else non-adherent (excess)", "+ vancomycin: adherent with MRSA history, excess without", ORANGE, ORANGEF),
       ("R ⊂ S (only part of the recommendation)", "Non-adherent (missing component) — not 50%", "ceftriaxone alone (azithromycin missing). Component overlap only as a secondary metric", RED, REDF),
       ("R ∩ S = ∅", "Non-adherent (different agents)", "cefepime + vancomycin without risk factors", RED, REDF),
       ("no R · surgical cefazolin only · viral co-infection", "Not applicable (out of denominator, counted)", "cefazolin alone: 310 patients", GREY, GREYF),
       ("an 'unknown' condition and candidate rows disagree", "Undeterminable (out of denominator; non-adherent in the lower bound)", "no vitals → severity unresolved (≈ 29%)", GREY, GREYF),
       ("non-adherent but the card holds a reason", "Justified deviation (only with evidence cited by clinician / LLM)", "cefepime chosen for prior Pseudomonas isolate", PURPLE, PURPLEF)],
 C="C  Pre-specified handling rules",
 crow=[("card variable absent from the guideline (lactate, CRP …)", "not used in the verdict; context for the report only"),
       ("guideline condition absent from the card (allergy, multilobar imaging)", "treated as 'unknown'; alternatives accepted as adherent without proof"),
       ("two antibiotics given, only one in the guideline", "patient-level non-adherent (missing); never counted as 50%"),
       ("broader than recommended", "adherent if the risk factor is in the card, else non-adherent (excess)"),
       ("KR and INTL guidelines disagree", "judge each, report both; rule-table relation (common / conflict)"),
       ("dose · route · timing", "separate items; mg/kg drugs undeterminable without weight"),
       ("patients the guideline does not cover (prophylaxis, viral pneumonia)", "not applicable; counted and removed from the denominator"),
       ("many undeterminable cases", "removed from the denominator, plus a lower-bound rate counting them as non-adherent"),
       ("LLM verdict differs from the rule", "compared on the sample only; the adherence rate comes from rules alone")],
 F="Adherence (selection) = (recommended + alternative) ÷ (all − not applicable − undeterminable)   ·   also report: n not applicable, n undeterminable, non-adherence subtypes, alternative share, lower bound"),
}
def esc(s): return html.escape(s, quote=False)
def tx(x, y, s, size=11, fill=INK, w="normal", anchor="start"): return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{w}" text-anchor="{anchor}">{esc(s)}</text>'
def icon(name, x, y, w, h, color): return f'<use href="#{name}" x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="2.2"/>'
def box(x, y, w, h, fill, stroke, r=8): return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
def arrow(x1, y1, x2, y2, color=GREY, m="ar", dash=False):
    d = ' stroke-dasharray="5 3"' if dash else ""
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="1.6" fill="none" marker-end="url(#{m})" color="{color}"{d}/>'
def chip(x, y, label, col, fill, size=10.5):
    w = sum(10.5 if ord(ch) > 0x2E80 else 6.1 for ch in label) * (size / 10.5) + 18
    return f'<rect x="{x}" y="{y - 13}" width="{w}" height="19" rx="9.5" fill="{fill}" stroke="{col}" stroke-width="1.2"/>' + tx(x + 9, y + 1, label, size, col, "bold"), w

def build(lang):
    t = T[lang]; o = [f'<rect width="1500" height="1010" fill="#fff"/>', tx(40, 40, t["title"], 18, INK, "bold")]
    # ---- A: main flow ----
    o.append(tx(40, 78, t["A"], 13.5, INK, "bold"))
    xs = [40, 330, 620, 910, 1200]; W, H, Y = 260, 118, 92
    icons = ["i-json", "i-gear", "i-table", "i-scale", "i-log"]; fills = ["#f8fafc", BLUEF, BLUEF, ORANGEF, GREENF]; strokes = [PURPLE, BLUE, BLUE, ORANGE, GREEN]
    for i, (x, ic, fl, st) in enumerate(zip(xs, icons, fills, strokes)):
        o.append(box(x, Y, W, H, fl, st)); o.append(icon(ic, x + 12, Y + 12, 24, 24, st)); o.append(tx(x + 44, Y + 29, t[f"s{i+1}t"], 12, INK, "bold"))
        for j, l in enumerate(t[f"s{i+1}"]): o.append(tx(x + 14, Y + 50 + j * 14, l, 9.8, GREY if j else INK))
        if i < 4: o.append(arrow(x + W + 3, Y + H / 2, xs[i + 1] - 3, Y + H / 2, GREY))
    # branch row
    BY = 250; bx = [330, 620, 910, 1200]
    o.append(box(bx[0], BY, W, 66, "#fff", PURPLE)); o.append(icon("i-person", bx[0] + 12, BY + 21, 22, 24, PURPLE)); o.append(tx(bx[0] + 44, BY + 39, t["b1t"], 11.5, INK, "bold"))
    for k, (x, key) in enumerate(zip(bx[1:], ("b2", "b3", "b4"))):
        o.append(box(x, BY, W, 66, PURPLEF, PURPLE)); o.append(tx(x + 14, BY + 22, t[key + "t"], 11.5, INK, "bold"))
        for j, l in enumerate(t[key]): o.append(tx(x + 14, BY + 38 + j * 12, l, 9.3, PURPLE))
    for x1, x2 in zip(bx[:-1], bx[1:]): o.append(arrow(x1 + W + 3, BY + 33, x2 - 3, BY + 33, PURPLE, "arP"))
    o.append(f'<path d="M{xs[0] + W / 2} {Y + H} L{xs[0] + W / 2} {BY + 33} L{bx[0] - 3} {BY + 33}" stroke="{PURPLE}" stroke-width="1.4" fill="none" stroke-dasharray="5 3" marker-end="url(#arP)"/>')
    o.append(f'<path d="M{xs[3] + W / 2} {Y + H} L{xs[3] + W / 2} {BY - 3}" stroke="{ORANGE}" stroke-width="1.4" fill="none" stroke-dasharray="5 3" marker-end="url(#arO)"/>')
    # ---- B: decision table ----
    By = 350; o.append(tx(40, By, t["B"], 13.5, INK, "bold"))
    cols = (40, 440, 700); rowh = 58
    for i, (cond, verdict, ex, col, fill) in enumerate(t["rows"]):
        y = By + 22 + i * rowh
        o.append(f'<rect x="40" y="{y}" width="1420" height="{rowh - 6}" rx="6" fill="{fill if i % 2 == 0 else "#fff"}" opacity="0.55"/>')
        o.append(icon("i-pill", 52, y + 20, 20, 20, col)); o.append(tx(80, y + 26, cond, 11, INK, "bold"))
        c1, w1 = chip(cols[1], y + 26, verdict, col, fill); o.append(c1)
        o.append(tx(cols[1], y + 48, ("예: " if lang == "ko" else "e.g. ") + ex, 9.8, GREY))
    # ---- C: handling rules (right of B? no: below) -> place C on the right side by shrinking B? keep B full width; C below B in two columns
    Cy = By + 22 + len(t["rows"]) * rowh + 8
    o.append(tx(40, Cy, t["C"], 13.5, INK, "bold"))
    half = len(t["crow"]) - len(t["crow"]) // 2
    for i, (sit, act) in enumerate(t["crow"]):
        cx = 40 if i < half else 760; yy = Cy + 20 + (i if i < half else i - half) * 17
        o.append(tx(cx, yy, "• " + sit, 9.8, INK, "bold")); o.append(tx(cx + 350 if lang == "ko" else cx + 330, yy, "→ " + act, 9.8, GREY))
    Fy = Cy + 20 + half * 17 + 6
    o.append(box(40, Fy, 1420, 30, GREENF, GREEN, 6)); o.append(tx(54, Fy + 20, t["F"], 10.8, GREEN, "bold"))
    body = "\n".join(o)
    return f'<svg viewBox="0 0 1500 1010" xmlns="http://www.w3.org/2000/svg" role="img" font-family="{t["font"]}" font-size="11">\n{DEFS}\n{body}\n</svg>'
for lang in ("ko", "en"):
    svg = build(lang)
    open(f"{OUTD}/fig5_judgment_{lang}.svg", "w", encoding="utf-8").write(svg)
    open(f"{OUTD}/fig5_judgment_{lang}.preview.html", "w", encoding="utf-8").write('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:1500px 1010px;margin:0}body{margin:0;background:#fff}svg{display:block;width:1500px;height:1010px}</style></head><body>' + svg + '</body></html>')
print("ok")
