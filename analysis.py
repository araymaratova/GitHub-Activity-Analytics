import json
import sqlite3
import subprocess
import sys
import time

import pandas as pd
import psutil

from config import CSV_PATH, DB_PATH, PARQUET_DIR, REPORTS_DIR

TOP_N = 10

SQL_TOP_REPOS = """
    SELECT r.repo_name, COUNT(*) AS events
    FROM events e
    JOIN repos r ON r.repo_id = e.repo_id
    GROUP BY r.repo_id, r.repo_name
    ORDER BY events DESC, r.repo_name
    LIMIT 10
"""


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["events", "repo_name"], ascending=[False, True])
    return out.head(TOP_N).reset_index(drop=True).astype({"events": "int64"})


def top_repos_from_counts(counts: pd.Series) -> pd.DataFrame:
    df = counts.rename("events").rename_axis("repo_name").reset_index()
    return normalize(df)


def approach_csv_full() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, usecols=["repo_id", "repo_name"],
                     dtype={"repo_name": "string"})
    df = df.dropna(subset=["repo_id"])
    return top_repos_from_counts(df.groupby("repo_name").size())


def approach_csv_chunks() -> pd.DataFrame:
    total = pd.Series(dtype="int64")
    for chunk in pd.read_csv(CSV_PATH, usecols=["repo_id", "repo_name"],
                             dtype={"repo_name": "string"}, chunksize=200_000):
        chunk = chunk.dropna(subset=["repo_id"])
        total = total.add(chunk.groupby("repo_name").size(), fill_value=0)
    return top_repos_from_counts(total.astype("int64"))


def approach_parquet() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET_DIR, columns=["repo_id", "repo_name"])
    df = df.dropna(subset=["repo_id"])
    return top_repos_from_counts(df.groupby("repo_name").size())


def approach_sqlite() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return normalize(pd.read_sql_query(SQL_TOP_REPOS, conn))
    finally:
        conn.close()


APPROACHES = {
    "baseline: CSV целиком (Pandas)": "approach_csv_full",
    "подход 1: CSV chunksize (Pandas)": "approach_csv_chunks",
    "подход 2: Parquet, нужные колонки (Pandas)": "approach_parquet",
    "подход 3: SQLite + SQL": "approach_sqlite",
}


def peak_mb() -> float:
    info = psutil.Process().memory_info()
    if hasattr(info, "peak_wset"):
        return info.peak_wset / 1e6
    import resource
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (raw if sys.platform == "darwin" else raw * 1024) / 1e6


def bench_child(func_name: str, out_path: str) -> None:
    func = globals()[func_name]
    base = peak_mb()
    t0 = time.perf_counter()
    result = func()
    seconds = time.perf_counter() - t0
    result.to_json(out_path, orient="records", force_ascii=False)
    print(json.dumps({"seconds": seconds, "peak_mb": peak_mb() - base}))


def bench_in_subprocess(func_name: str):
    out_path = REPORTS_DIR / f"result_{func_name}.json"
    proc = subprocess.run([sys.executable, __file__, "--bench", func_name, str(out_path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:])
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    result = pd.read_json(out_path, orient="records", dtype={"repo_name": "string"})
    return result, info["seconds"], info["peak_mb"]


def run_comparison() -> pd.DataFrame:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reference = None
    rows = []
    for label, func_name in APPROACHES.items():
        result, seconds, peak = bench_in_subprocess(func_name)
        result = normalize(result)
        if reference is None:
            reference = result
        try:
            pd.testing.assert_frame_equal(reference, result, check_dtype=False)
            same = "да"
        except AssertionError:
            same = "НЕТ"
        rows.append((label, round(seconds, 2), round(peak, 1), same))
        print(f"{label}: {seconds:.2f} с, пик +{peak:.0f} МБ, совпадает с baseline: {same}")

    table = pd.DataFrame(rows, columns=["approach", "seconds", "peak_mem_mb", "matches_baseline"])
    table.to_csv(REPORTS_DIR / "approaches_comparison.csv", index=False)
    return table


def run_sql_vs_pandas() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        t0 = time.perf_counter()
        sql_df = normalize(pd.read_sql_query(SQL_TOP_REPOS, conn))
        t_sql = time.perf_counter() - t0
        events = pd.read_sql_query(
            "SELECT e.repo_id, r.repo_name FROM events e "
            "JOIN repos r ON r.repo_id = e.repo_id", conn)
    finally:
        conn.close()

    t0 = time.perf_counter()
    pandas_df = top_repos_from_counts(events.groupby("repo_name").size())
    t_pandas = time.perf_counter() - t0

    pd.testing.assert_frame_equal(sql_df, pandas_df, check_dtype=False)
    table = pd.DataFrame([("SQL (GROUP BY в SQLite)", round(t_sql, 3)),
                          ("Pandas (groupby, данные уже в памяти)", round(t_pandas, 3))],
                         columns=["method", "seconds"])
    print(table.to_string(index=False))
    print("Результаты SQL и Pandas совпадают (assert_frame_equal пройден)")
    table.to_csv(REPORTS_DIR / "sql_vs_pandas.csv", index=False)
    return table


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--bench":
        bench_child(sys.argv[2], sys.argv[3])
    else:
        try:
            print("СРАВНЕНИЕ ПОДХОДОВ (baseline + 3)")
            run_comparison()
            print("\nSQL vs PANDAS")
            run_sql_vs_pandas()
        except (FileNotFoundError, RuntimeError, sqlite3.Error, AssertionError) as err:
            print("Ошибка:", err)