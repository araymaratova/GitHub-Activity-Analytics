from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
PARQUET_DIR = PROCESSED_DIR / "parquet_raw"
CSV_PATH = PROCESSED_DIR / "events_raw.csv"
CACHE_DIR = BASE_DIR / "data" / "cache"
DB_PATH = BASE_DIR / "data" / "github.db"
REPORTS_DIR = BASE_DIR / "reports"

N_FILES = 30        
CHUNK_SIZE = 200_000 