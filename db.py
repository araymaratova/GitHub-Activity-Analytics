import json
import sqlite3
import time

import pandas as pd

from config import BASE_DIR, CACHE_DIR, DB_PATH, PARQUET_DIR

SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"
CACHE_FILE = CACHE_DIR / "repo_languages.json"

INDEXES = [
    "CREATE INDEX idx_events_type ON events(type_id)",
    "CREATE INDEX idx_events_actor ON events(actor_id)",
    "CREATE INDEX idx_events_repo ON events(repo_id)",
    "CREATE INDEX idx_events_created ON events(created_at)",
    "CREATE INDEX idx_repos_language ON repos(language_id)",
]


def load_language_cache() -> dict:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except FileNotFoundError:
        print("Кэш языков не найден, языки будут только из событий")
        return {}
    return {name: v["language"] for name, v in cache.items() if v.get("language")}


def to_records(df: pd.DataFrame) -> list:
    clean = df.astype(object).where(df.notna(), None)
    return clean.values.tolist()


def collect_names(files: list, column: str) -> list:
    names = set()
    for f in files:
        names.update(pd.read_parquet(f, columns=[column])[column].dropna().unique())
    return sorted(names)


def insert_lookup(conn, table: str, id_col: str, name_col: str, names: list) -> dict:
    conn.executemany(f"INSERT OR IGNORE INTO {table}({name_col}) VALUES (?)",
                     [(n,) for n in names])
    conn.commit()
    return dict(conn.execute(f"SELECT {name_col}, {id_col} FROM {table}"))


def load_chunk(conn, df: pd.DataFrame, cache: dict, type_map: dict, lang_map: dict) -> None:
    df["repo_id"] = df["repo_id"].astype("Int64")

    actors = (df[["actor_id", "actor_login"]]
              .dropna(subset=["actor_id"]).drop_duplicates("actor_id"))
    conn.executemany("INSERT OR IGNORE INTO actors(actor_id, login) VALUES (?, ?)",
                     to_records(actors))

    repos = (df[["repo_id", "repo_name", "language"]]
             .dropna(subset=["repo_id"]).drop_duplicates("repo_id"))
    lang_name = repos["repo_name"].map(cache).fillna(repos["language"])
    repos = repos.assign(language_id=lang_name.map(lang_map).astype("Int64"))
    conn.executemany(
        """INSERT INTO repos(repo_id, repo_name, language_id) VALUES (?, ?, ?)
           ON CONFLICT(repo_id) DO UPDATE SET
               repo_name = excluded.repo_name,
               language_id = COALESCE(repos.language_id, excluded.language_id)""",
        to_records(repos[["repo_id", "repo_name", "language_id"]]))

    events = df.assign(type_id=df["type"].map(type_map))[
        ["event_id", "type_id", "action", "actor_id", "repo_id", "created_at"]]
    conn.executemany(
        "INSERT OR IGNORE INTO events(event_id, type_id, action, actor_id, repo_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)", to_records(events))


def build_db() -> dict:
    files = sorted(PARQUET_DIR.glob("part_*.parquet"))
    if not files:
        raise FileNotFoundError(f"Нет Parquet-файлов в {PARQUET_DIR}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    cache = load_language_cache()
    type_map = insert_lookup(conn, "event_types", "type_id", "type_name",
                             collect_names(files, "type"))
    lang_names = sorted(set(cache.values()) | set(collect_names(files, "language")))
    lang_map = insert_lookup(conn, "languages", "language_id", "language_name", lang_names)

    t0 = time.perf_counter()
    for i, f in enumerate(files, 1):
        load_chunk(conn, pd.read_parquet(f), cache, type_map, lang_map)
        conn.commit()
        print(f"Загружен кусок {i}/{len(files)}")

    for stmt in INDEXES:
        conn.execute(stmt)
    conn.execute("ANALYZE")
    conn.commit()

    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("event_types", "languages", "actors", "repos", "events")}
    conn.close()
    counts["db_size_mb"] = round(DB_PATH.stat().st_size / 1e6, 1)
    counts["seconds"] = round(time.perf_counter() - t0, 1)
    return counts


if __name__ == "__main__":
    try:
        print(build_db())
    except (FileNotFoundError, sqlite3.Error) as err:
        print("Ошибка:", err)