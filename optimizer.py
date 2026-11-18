import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import psutil

from config import CSV_PATH, PARQUET_DIR, PROCESSED_DIR, REPORTS_DIR

OPT_PARQUET = PROCESSED_DIR / "events_optimized.parquet"
CSV_DTYPES = {"type": "string", "action": "string", "actor_login": "string",
              "repo_name": "string", "language": "string"}


def mem_mb(df: pd.DataFrame) -> float:
    return df.memory_usage(deep=True).sum() / 1e6


def optimize_types(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("type", "action", "language"):
        out[col] = out[col].astype("category")
    out["created_at"] = pd.to_datetime(out["created_at"], utc=True)
    for col in ("event_id", "actor_id"):
        out[col] = pd.to_numeric(out[col], downcast="integer")
    out["repo_id"] = out["repo_id"].astype("Int64") 
    out["is_bot"] = out["is_bot"].astype("int8")
    return out


def peak_mb() -> float:
    info = psutil.Process().memory_info()
    if hasattr(info, "peak_wset"):
        return info.peak_wset / 1e6
    import resource
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (raw if sys.platform == "darwin" else raw * 1024) / 1e6


def bench_child(func_name: str) -> None:
    func = globals()[func_name]
    base = peak_mb()
    t0 = time.perf_counter()
    func()
    seconds = time.perf_counter() - t0
    print(json.dumps({"seconds": seconds, "peak_mb": peak_mb() - base}))


def bench_in_subprocess(func_name: str):
    proc = subprocess.run([sys.executable, __file__, "--bench", func_name],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:])
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    return res["seconds"], res["peak_mb"]


def read_csv_full():
    return pd.read_csv(CSV_PATH, dtype=CSV_DTYPES)


def read_csv_chunks(chunksize: int = 200_000):
    rows = bots = 0
    for chunk in pd.read_csv(CSV_PATH, chunksize=chunksize, dtype=CSV_DTYPES):
        rows += len(chunk)
        bots += int(chunk["is_bot"].sum())
    return rows, bots


def read_parquet_full():
    return pd.read_parquet(PARQUET_DIR)


def read_optimized_parquet():
    return pd.read_parquet(OPT_PARQUET)


def dir_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / 1e6
    return sum(f.stat().st_size for f in path.glob("*") if f.is_file()) / 1e6


def run_memory_report() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET_DIR)
    before = mem_mb(df)
    opt = optimize_types(df)
    after = mem_mb(opt)
    opt.to_parquet(OPT_PARQUET, index=False)

    rows = []
    for col in df.columns:
        rows.append({"column": col,
                     "dtype_before": str(df[col].dtype),
                     "dtype_after": str(opt[col].dtype),
                     "mb_before": round(df[col].memory_usage(deep=True) / 1e6, 1),
                     "mb_after": round(opt[col].memory_usage(deep=True) / 1e6, 1)})
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    print(f"\nИТОГО: до {before:.1f} МБ, после {after:.1f} МБ, "
          f"экономия {100 * (1 - after / before):.1f}%")
    return table


def run_format_comparison() -> pd.DataFrame:
    methods = [
        ("CSV целиком (baseline)", "read_csv_full", CSV_PATH),
        ("CSV chunksize=200000", "read_csv_chunks", CSV_PATH),
        ("Parquet (исходные типы)", "read_parquet_full", PARQUET_DIR),
        ("Parquet (оптимизированные типы)", "read_optimized_parquet", OPT_PARQUET),
    ]
    results = []
    for label, func_name, path in methods:
        seconds, peak = bench_in_subprocess(func_name)
        results.append((label, dir_size_mb(path), seconds, peak))

    table = pd.DataFrame(results, columns=["method", "size_mb", "read_seconds", "peak_mem_mb"])
    table = table.round(2)
    print(table.to_string(index=False))
    return table


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--bench":
        bench_child(sys.argv[2])
    else:
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            print("ПАМЯТЬ: ДО И ПОСЛЕ")
            mem_table = run_memory_report()
            mem_table.to_csv(REPORTS_DIR / "memory_before_after.csv", index=False)

            print("\nСРАВНЕНИЕ ФОРМАТОВ")
            fmt_table = run_format_comparison()
            fmt_table.to_csv(REPORTS_DIR / "csv_vs_parquet.csv", index=False)
        except (FileNotFoundError, RuntimeError) as err:
            print("Ошибка:", err)