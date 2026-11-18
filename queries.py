import sqlite3

import pandas as pd

from config import DB_PATH, REPORTS_DIR

QUERIES = {
    "q01_events_by_type": """
        SELECT t.type_name, COUNT(*) AS events
        FROM events e
        JOIN event_types t ON t.type_id = e.type_id
        GROUP BY t.type_name
        ORDER BY events DESC
    """,

    "q02_top_repos": """
        SELECT r.repo_name, COUNT(*) AS events
        FROM events e
        JOIN repos r ON r.repo_id = e.repo_id
        GROUP BY r.repo_id, r.repo_name
        ORDER BY events DESC, r.repo_name
        LIMIT 10
    """,

    "q03_top_users": """
        SELECT a.login, COUNT(*) AS events
        FROM events e
        JOIN actors a ON a.actor_id = e.actor_id
        WHERE a.login NOT LIKE '%[bot]'
        GROUP BY a.actor_id, a.login
        ORDER BY events DESC, a.login
        LIMIT 10
    """,

    "q04_events_by_hour": """
        SELECT substr(created_at, 1, 13) AS hour, COUNT(*) AS events
        FROM events
        GROUP BY hour
        ORDER BY hour
    """,

    "q05_repos_having": """
        SELECT r.repo_name,
               COUNT(*) AS events,
               COUNT(DISTINCT e.actor_id) AS users
        FROM events e
        JOIN repos r ON r.repo_id = e.repo_id
        GROUP BY r.repo_id, r.repo_name
        HAVING COUNT(DISTINCT e.actor_id) >= 20
        ORDER BY users DESC, r.repo_name
        LIMIT 20
    """,

    "q06_top3_per_language": """
        WITH repo_events AS (
            SELECT r.repo_name, l.language_name, COUNT(*) AS events
            FROM events e
            JOIN repos r ON r.repo_id = e.repo_id
            JOIN languages l ON l.language_id = r.language_id
            GROUP BY r.repo_id, r.repo_name, l.language_name
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY language_name ORDER BY events DESC, repo_name) AS rn
            FROM repo_events
        )
        SELECT language_name, rn, repo_name, events
        FROM ranked
        WHERE rn <= 3
        ORDER BY language_name, rn
    """,

    "q07_language_rank_pr": """
        SELECT l.language_name,
               COUNT(*) AS pr_events,
               RANK() OVER (ORDER BY COUNT(*) DESC) AS rnk
        FROM events e
        JOIN event_types t ON t.type_id = e.type_id
        JOIN repos r ON r.repo_id = e.repo_id
        JOIN languages l ON l.language_id = r.language_id
        WHERE t.type_name = 'PullRequestEvent'
        GROUP BY l.language_name
        ORDER BY rnk, l.language_name
        LIMIT 15
    """,

    "q08_moving_avg": """
        WITH hourly AS (
            SELECT substr(created_at, 1, 13) AS hour, COUNT(*) AS events
            FROM events
            GROUP BY hour
        )
        SELECT hour, events,
               ROUND(AVG(events) OVER (
                   ORDER BY hour ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS moving_avg_3h
        FROM hourly
        ORDER BY hour
    """,

    "q09_language_share": """
        WITH lang_events AS (
            SELECT l.language_name, COUNT(*) AS events
            FROM events e
            JOIN repos r ON r.repo_id = e.repo_id
            JOIN languages l ON l.language_id = r.language_id
            GROUP BY l.language_name
        )
        SELECT language_name, events,
               ROUND(100.0 * events / SUM(events) OVER (), 2) AS share_pct
        FROM lang_events
        ORDER BY events DESC
        LIMIT 15
    """,

    "q10_above_avg_users": """
        SELECT a.login, COUNT(*) AS events
        FROM events e
        JOIN actors a ON a.actor_id = e.actor_id
        WHERE a.login NOT LIKE '%[bot]'
        GROUP BY a.actor_id, a.login
        HAVING COUNT(*) > (
            SELECT AVG(cnt) FROM (
                SELECT COUNT(*) AS cnt
                FROM events e2
                JOIN actors a2 ON a2.actor_id = e2.actor_id
                WHERE a2.login NOT LIKE '%[bot]'
                GROUP BY e2.actor_id
            )
        )
        ORDER BY events DESC, a.login
        LIMIT 20
    """,

    "q11_language_trend": """
        WITH top_lang AS (
            SELECT r.language_id
            FROM events e
            JOIN repos r ON r.repo_id = e.repo_id
            WHERE r.language_id IS NOT NULL
            GROUP BY r.language_id
            ORDER BY COUNT(*) DESC
            LIMIT 5
        )
        SELECT substr(e.created_at, 1, 13) AS hour,
               l.language_name,
               COUNT(*) AS events
        FROM events e
        JOIN repos r ON r.repo_id = e.repo_id
        JOIN languages l ON l.language_id = r.language_id
        WHERE r.language_id IN (SELECT language_id FROM top_lang)
        GROUP BY hour, l.language_name
        ORDER BY hour, l.language_name
    """,

    "q12_language_coverage": """
        SELECT ROUND(100.0 * SUM(CASE WHEN r.language_id IS NOT NULL THEN 1 ELSE 0 END)
                     / COUNT(*), 2) AS pct_events_with_language,
               SUM(CASE WHEN r.language_id IS NOT NULL THEN 1 ELSE 0 END) AS events_with_language,
               COUNT(*) AS total_events
        FROM events e
        JOIN repos r ON r.repo_id = e.repo_id
    """,
}


def run_query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


def run_all() -> dict:
    results = {}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        for name, sql in QUERIES.items():
            df = run_query(conn, sql)
            df.to_csv(REPORTS_DIR / f"{name}.csv", index=False)
            results[name] = df
            print(f"\n {name} ({len(df)} строк)")
            print(df.head(10).to_string(index=False))
    finally:
        conn.close()
    return results


if __name__ == "__main__":
    try:
        run_all()
    except (sqlite3.Error, FileNotFoundError) as err:
        print("Ошибка:", err)