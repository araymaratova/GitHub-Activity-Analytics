import requests
from datetime import datetime, timedelta
from pathlib import Path

RAW_DIR = Path("data/raw")


def build_url(ts: datetime) -> str:
    return f"https://data.gharchive.org/{ts:%Y-%m-%d}-{ts.hour}.json.gz"


def download_file(url: str, dest: Path, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True  
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                if r.status_code != 200:
                    print(f"  {r.status_code} for {url}")
                    return False
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            return True
        except requests.RequestException as err:
            print(f"  try {attempt}/{retries}: {err}")
    return False


def download_hours(start: datetime, n_files: int = 30) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for i in range(n_files):
        ts = start + timedelta(hours=i)
        dest = RAW_DIR / f"{ts:%Y-%m-%d}-{ts.hour}.json.gz"
        if download_file(build_url(ts), dest):
            ok += 1
        else:
            fail += 1
        if (i + 1) % 10 == 0:
            print(f"{i + 1}/{n_files} (success {ok}, error {fail})")
    print(f"success {ok}, error {fail}")


if __name__ == "__main__":
    download_hours(datetime(2026, 10, 25, 0), n_files=30)