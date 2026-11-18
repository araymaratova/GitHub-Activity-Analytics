import gzip
import json
import time
from pathlib import Path

import pandas as pd

from config import (RAW_DIR, PROCESSED_DIR, PARQUET_DIR,
                    CSV_PATH, CHUNK_SIZE, N_FILES)

COLUMNS = [
    "event_id", "type", "action", "created_at",
    "actor_id", "actor_login", "is_bot",
    "repo_id", "repo_name", "language",
]


def extract_language(event: dict):
    payload = event.get("payload") or {}
    forkee = payload.get("forkee") or {}
    if forkee.get("language"):
        return forkee["language"]
    pr = payload.get("pull_request") or {}
    for side in ("base", "head"):
        repo = (pr.get(side) or {}).get("repo") or {}
        if repo.get("language"):
            return repo["language"]
    return None


def parse_event(event: dict) -> dict:
    actor = event.get("actor") or {}
    repo = event.get("repo") or {}
    payload = event.get("payload") or {}
    login = actor.get("login") or ""
    return {
        "event_id": int(event["id"]),
        "type": event.get("type"),
        "action": payload.get("action"),
        "created_at": event.get("created_at"),
        "actor_id": actor.get("id"),
        "actor_login": login,
        "is_bot": int(login.endswith("[bot]")),
        "repo_id": repo.get("id"),
        "repo_name": repo.get("name"),
        "language": extract_language(event),
    }


def parse_file(path: Path, stats: dict):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                yield parse_event(json.loads(line))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                stats["bad_lines"] += 1


def write_chunk(rows: list, chunk_no: int) -> None:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(CSV_PATH, mode="a", header=(chunk_no == 0), index=False)
    df.to_parquet(PARQUET_DIR / f"part_{chunk_no:04d}.parquet", index=False)


def process_all() -> dict:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    CSV_PATH.unlink(missing_ok=True)
    for old in PARQUET_DIR.glob("*.parquet"):
        old.unlink()

    files = sorted(RAW_DIR.glob("*.json.gz"),
                   key=lambda p: tuple(int(x) for x in p.name.split(".")[0].split("-")))
    files = files[:N_FILES]
    if not files:
        raise FileNotFoundError(f"Нет файлов в {RAW_DIR}")

    stats = {"files": len(files), "first": files[0].name, "last": files[-1].name,
             "rows": 0, "bad_lines": 0, "chunks": 0}
    buffer = []
    t0 = time.perf_counter()

    for i, path in enumerate(files, 1):
        for row in parse_file(path, stats):
            buffer.append(row)
            if len(buffer) >= CHUNK_SIZE:
                write_chunk(buffer, stats["chunks"])
                stats["rows"] += len(buffer)
                stats["chunks"] += 1
                buffer = []
        print(f"Файл {i}/{len(files)}: {path.name}")

    if buffer:
        write_chunk(buffer, stats["chunks"])
        stats["rows"] += len(buffer)
        stats["chunks"] += 1

    stats["seconds"] = round(time.perf_counter() - t0, 1)
    return stats


if __name__ == "__main__":
    try:
        print(process_all())
    except FileNotFoundError as err:
        print("Ошибка:", err)