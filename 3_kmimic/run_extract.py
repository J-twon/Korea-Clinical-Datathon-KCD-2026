#!/usr/bin/env python3
"""K-MIMIC 추출을 에이전트 없이 직접 실행 — pod 터미널에서:
    python3 run_extract.py --hospitals=005,006,004,202,009 --out=DATA/raw [--prefix] [--test]
kmimic_extract.sql 의 쿼리 3개를 데이터셋(기관)마다 실행해 CSV 로 바로 저장한다. LLM 이 행을 중계하지 않으므로 엔진 속도만 든다.
이미 있는 파일은 건너뛰므로 끊기면 같은 명령으로 다시 돌리면 이어진다.

연결은 아래 run_sql() 하나만 플랫폼 방식으로 채우면 된다. khdp.ai 에게는 이렇게만 부탁한다:
  "run_extract.py 의 run_sql(sql, dataset) 함수만, 네가 SQL 을 실행할 때 쓰는 연결 방식으로 채워 줘. 다른 줄은 고치지 마. 그리고 실행 명령을 알려 줘."
옵션:
  --prefix   테이블 이름 앞에 데이터셋 접두어가 필요한 환경이면 ADMISSIONS → "kmimic-emr-003".ADMISSIONS 로 자동 치환
  --test     각 쿼리 끝에 LIMIT 5 를 붙여 연결 · 문법만 확인 (파일은 *_test.csv)
  --dataset=kmimic-emr-{h}   데이터셋 이름 틀 (기본값). {h} 자리에 기관 코드가 들어간다
"""
import csv, os, re, sys, time

# ============================ ★ 여기만 채운다 ★ ============================
def run_sql(sql, dataset):
    """SQL 문자열을 데이터셋 dataset 에서 실행해 (컬럼 이름 리스트, 행의 반복자) 를 돌려준다."""
    # 예 1) Trino/Presto 파이썬 클라이언트
    # import trino
    # conn = trino.dbapi.connect(host="HOST", port=443, user="USER", http_scheme="https", catalog="CATALOG", schema=dataset)
    # cur = conn.cursor(); cur.execute(sql); return [d[0] for d in cur.description], cur.fetchall()
    # 예 2) SQLAlchemy 엔진 / 커넥션 문자열
    # import sqlalchemy as sa
    # eng = sa.create_engine("trino://USER@HOST:443/CATALOG/" + dataset)
    # with eng.connect() as c: r = c.execute(sa.text(sql)); return list(r.keys()), r.fetchall()
    # 예 3) 플랫폼 SDK (khdp.ai 가 내부적으로 쓰는 것)
    # from some_khdp_sdk import query
    # res = query(sql, dataset=dataset); return res.columns, res.rows
    raise NotImplementedError("run_sql() 을 플랫폼의 SQL 실행 방식으로 채우세요 (위 예시 중 하나).")
# ===========================================================================

TABLES = ("ADMISSIONS", "PATIENTS", "ICUSTAYS", "DIAGNOSES_ICD", "PRESCRIPTIONS", "MICROBIOLOGYEVENTS", "PROCEDUREEVENTS")

def load_queries(path):
    sql = open(path, encoding="utf-8").read()
    parts = re.split(r"-- ########## 쿼리 \d / 3 : (\w+)\.csv ##########", sql)
    q = {parts[i]: parts[i + 1].strip().rstrip(";").strip() for i in range(1, len(parts), 2)}
    assert set(q) == {"cohort", "antibiotics", "cultures"}, list(q)
    return q

def prepare(sql, dataset, prefix, test):
    if prefix:
        sql = re.sub(r"\b(FROM|JOIN)\s+(" + "|".join(TABLES) + r")\b", lambda m: f'{m.group(1)} "{dataset}".{m.group(2)}', sql)
    if test: sql = sql + "\nLIMIT 5"
    return sql

def main():
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    flags = {a for a in sys.argv[1:] if a.startswith("--") and "=" not in a}
    hospitals = opts.get("hospitals", "003,004,005,006,009,001,202").split(",")
    out = opts.get("out", "DATA/raw"); os.makedirs(out, exist_ok=True)
    tmpl = opts.get("dataset", "kmimic-emr-{h}"); prefix = "--prefix" in flags; test = "--test" in flags
    queries = load_queries(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kmimic_extract.sql"))
    log = open(os.path.join(out, "run_extract.log"), "a", encoding="utf-8")
    def say(m):
        line = time.strftime("%H:%M:%S ") + m; print(line, flush=True); log.write(line + "\n"); log.flush()
    for h in hospitals:
        ds = tmpl.format(h=h)
        for name in ("cohort", "antibiotics", "cultures"):
            fn = os.path.join(out, f"{name}_{h}{'_test' if test else ''}.csv")
            if os.path.exists(fn) and os.path.getsize(fn) > 0 and not test: say(f"[{h}] {name}: 이미 있음 → 건너뜀"); continue
            t = time.time(); say(f"[{h}] {name}: 실행 ({ds})")
            try:
                cols, rows = run_sql(prepare(queries[name], ds, prefix, test), ds)
            except Exception as e:
                say(f"[{h}] {name}: 실패 — {type(e).__name__}: {str(e)[:300]}"); continue
            n = 0; part = fn + ".part"
            with open(part, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(cols)
                for r in rows: w.writerow(list(r)); n += 1
            os.replace(part, fn); say(f"[{h}] {name}: {n:,}행 저장 → {fn} ({time.time() - t:,.0f}초)")
    say("끝. 다음: KMIMIC_EXTRACTION.md ① 의 이어 붙이기 명령 → ② derive …")

if __name__ == "__main__":
    main()
