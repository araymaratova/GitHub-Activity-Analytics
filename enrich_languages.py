import json
import os
import time

import pandas as pd
import requests

from config import PARQUET_DIR, CACHE_DIR

CACHE_FILE = CACHE_DIR / "repo_languages.json"
TOP_N = 3000
API_URL = "https://api.github.com/repos/{name}"

from pathlib import Path

def read_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    try:
        return Path("token.txt").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError("Нет токена")

def load_cache() -> dict:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Кэш поврежден")
        return {}


def save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def top_repos(n: int = TOP_N) -> list:
    df = pd.read_parquet(PARQUET_DIR, columns=["repo_name"])
    return df["repo_name"].value_counts().head(n).index.tolist()


def fetch_language(name: str, headers: dict):
    try:
        r = requests.get(API_URL.format(name=name), headers=headers, timeout=20)
    except requests.RequestException:
        return None, "error"
    if r.status_code == 200:
        return r.json().get("language"), "ok"
    if r.status_code == 404:
        return None, "not_found"
    if r.status_code in (403, 429):
        return None, "rate_limit"
    return None, "error"


def enrich(n: int = TOP_N) -> dict:
    token = read_token()
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json"}

    cache = load_cache()
    repos = top_repos(n)
    todo = [r for r in repos if r not in cache]
    print(f"В топе {len(repos)}, уже в кэше {len(repos) - len(todo)}, осталось {len(todo)}")

    for i, name in enumerate(todo, 1):
        lang, status = fetch_language(name, headers)
        if status == "rate_limit":
            print("Достигнут лимит API.")
            break
        if status == "error":
            continue 
        cache[name] = {"language": lang, "status": status}
        if i % 100 == 0:
            save_cache(cache)
            print(f"{i}/{len(todo)}")
        time.sleep(0.05)

    save_cache(cache)
    with_lang = sum(1 for v in cache.values() if v["language"])
    return {"in_cache": len(cache), "with_language": with_lang}


if __name__ == "__main__":
    try:
        print(enrich())
    except RuntimeError as err:
        print("Error:", err)